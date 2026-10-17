"""Perception: let the agent see and hear the timeline.

This is the heart of Resolve MCP. Rather than edit blind against metadata, the
agent exports the real frame at the playhead and looks at it, and reads a clip's
audio waveform so it can cut on sound as well as on sight.
"""
from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
import time
from array import array as _array
from pathlib import Path

from mcp.server.fastmcp import Image

from ..connection import ResolveError, get_media_pool, get_project, get_timeline
from .. import serialize

_SCRATCH = Path(tempfile.gettempdir()) / "resolve-mcp"


def render_current_frame() -> Image:
    """See the edit. Export the frame at the playhead and return it as an image.

    Use this to look at what the timeline actually shows before and after an
    edit, rather than reasoning from metadata alone. The current timeline
    must be open and a frame visible at the playhead.
    """
    project = get_project()
    get_timeline()

    _SCRATCH.mkdir(parents=True, exist_ok=True)
    target = _SCRATCH / f"frame_{int(time.time() * 1000)}.png"

    ok = project.ExportCurrentFrameAsStill(str(target))

    path = target
    if not path.exists():
        stills = sorted(_SCRATCH.glob("frame_*.*"), key=lambda p: p.stat().st_mtime)
        path = stills[-1] if stills else target

    if not ok or not path.exists():
        raise ResolveError(
            "Could not export the current frame. Open a timeline and make "
            "sure a frame is visible at the playhead (the Color or Edit page)."
        )

    return Image(data=path.read_bytes(), format=path.suffix.lstrip(".") or "png")


def _find_clip_path(clip_name: str):
    """Return the on-disk file path of a media-pool clip by name, or None."""
    pool = get_media_pool()
    root = pool.GetRootFolder()
    stack = [root] if root else []
    while stack:
        folder = stack.pop()
        for clip in folder.GetClipList() or []:
            if serialize.safe(clip.GetName) == clip_name:
                return serialize.safe(clip.GetClipProperty, "File Path") or None
        stack.extend(folder.GetSubFolderList() or [])
    return None


def analyze_audio(
    clip_name: str | None = None,
    file_path: str | None = None,
    max_seconds: float = 90.0,
) -> dict:
    """Hear a clip: analyse its audio waveform so you can cut on sound.

    Resolve MCP sees the frame with render_current_frame; this is the matching ear.
    Pass a media-pool clip name (its file is read from disk) or a direct
    ``file_path`` such as a music track. Reads at most ``max_seconds`` from the
    head. Requires ffmpeg on PATH.

    Returns a dict with: ``duration``; ``loudness_db`` (mean and max); an
    estimated ``tempo_bpm`` with ``beat_seconds`` and a ``beat_grid`` of beat
    times; ``onset_peaks`` (times of audible hits); ``silences`` (quiet
    stretches as start/end); and a downsampled ``envelope`` of level over time.
    Use the beat grid or onset peaks to cut on the beat or on a hit, and the
    silences to find natural gaps, exactly the way the rendered frame lets you
    cut on what you see.
    """
    path = file_path or (None if clip_name is None else _find_clip_path(clip_name))
    if clip_name is not None and not path:
        raise ResolveError(
            f"No clip named '{clip_name}' with a readable file path in the Media Pool."
        )
    if not path:
        raise ResolveError("Give a clip_name in the media pool or a file_path to analyse.")
    if not os.path.exists(path):
        raise ResolveError(f"Audio source not found on disk: {path}")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ResolveError("ffmpeg is required for audio analysis but is not on PATH.")

    sr = 22050
    proc = subprocess.run(
        [ffmpeg, "-nostdin", "-v", "error", "-t", str(float(max_seconds)),
         "-i", path, "-ac", "1", "-ar", str(sr), "-f", "f32le", "pipe:1"],
        capture_output=True,
    )
    if not proc.stdout:
        raise ResolveError(
            f"ffmpeg returned no audio for {path}. Does the source carry an audio stream?"
        )
    samples = _array("f")
    samples.frombytes(proc.stdout)
    n = len(samples)
    dur = n / sr

    hop = 256
    nframes = max(1, (n - hop) // hop)
    rms = [0.0] * nframes
    for i in range(nframes):
        base = i * hop
        acc = 0.0
        for j in range(base, base + hop):
            v = samples[j]
            acc += v * v
        rms[i] = math.sqrt(acc / hop)
    fps = sr / hop

    eps = 1e-9
    db = [20.0 * math.log10(r + eps) for r in rms]

    # onset envelope: positive frame-to-frame energy change, mean-subtracted
    onset = [0.0] * nframes
    for i in range(1, nframes):
        d = rms[i] - rms[i - 1]
        onset[i] = d if d > 0 else 0.0
    mean_on = (sum(onset) / nframes) if nframes else 0.0
    onc = [x - mean_on if x > mean_on else 0.0 for x in onset]

    # tempo by autocorrelation of the onset envelope over 60-180 BPM
    lo = max(1, int(fps * 60 / 180))
    hi = min(int(fps * 60 / 60), nframes - 1)
    best_lag, best_val = 0, -1.0
    for lag in range(lo, hi + 1):
        acc = 0.0
        for i in range(nframes - lag):
            acc += onc[i] * onc[i + lag]
        if acc > best_val:
            best_val, best_lag = acc, lag
    bpm = (60.0 * fps / best_lag) if best_lag else None
    beat = (best_lag / fps) if best_lag else None

    # silent stretches below threshold for at least min_sil seconds
    sil_thresh, min_sil = -45.0, 0.3
    silences, run_start = [], None
    for i in range(nframes):
        t = i / fps
        if db[i] < sil_thresh:
            if run_start is None:
                run_start = t
        else:
            if run_start is not None and (t - run_start) >= min_sil:
                silences.append({"start": round(run_start, 2), "end": round(t, 2)})
            run_start = None
    if run_start is not None and (dur - run_start) >= min_sil:
        silences.append({"start": round(run_start, 2), "end": round(dur, 2)})

    # onset peaks: local maxima of the onset envelope, thinned to ~0.12s spacing
    peak_thresh = (max(onc) * 0.4) if onc else 0.0
    peaks = []
    for i in range(1, nframes - 1):
        if onc[i] > peak_thresh and onc[i] >= onc[i - 1] and onc[i] > onc[i + 1]:
            t = i / fps
            if not peaks or t - peaks[-1] >= 0.12:
                peaks.append(round(t, 2))
    peaks = peaks[:80]

    # downsample the dB envelope to ~120 points for a compact return
    step = max(1, nframes // 120)
    envelope = [{"t": round(i / fps, 2), "db": round(db[i], 1)} for i in range(0, nframes, step)]

    beat_grid = []
    if beat:
        t = 0.0
        while t <= dur and len(beat_grid) < 128:
            beat_grid.append(round(t, 3))
            t += beat

    return {
        "source": path,
        "duration": round(dur, 2),
        "sample_rate": sr,
        "loudness_db": {"mean": round(sum(db) / nframes, 1), "max": round(max(db), 1)},
        "tempo_bpm": round(bpm, 1) if bpm else None,
        "beat_seconds": round(beat, 3) if beat else None,
        "beat_grid": beat_grid,
        "onset_peaks": peaks,
        "silences": silences,
        "envelope": envelope,
        "note": "Level over time in dB. Cut on beat_grid or onset_peaks for sound; silences are natural gaps.",
    }


def register(mcp) -> None:
    for fn in (render_current_frame, analyze_audio):
        mcp.tool()(fn)
