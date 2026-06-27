"""Shared serializers: turn Resolve native objects into plain, JSON-safe dicts.

The Resolve scripting objects are opaque native handles. The MCP only ever
hands the agent plain dicts and lists, so every tool funnels its objects through
these helpers. Each is defensive: a missing or unsupported call yields ``None``
rather than raising, because the surface varies across clip kinds and pages.
"""
from __future__ import annotations

from typing import Any, Callable


def safe(fn: Callable, *args, default: Any = None) -> Any:
    """Call ``fn(*args)`` and swallow any failure, returning ``default``.

    Used everywhere a Resolve getter may be absent for a given object kind
    (e.g. audio clips have no resolution) so serialization never crashes.
    """
    try:
        value = fn(*args)
    except Exception:
        return default
    return default if value is None else value


def clip_to_dict(mpi, full: bool = False) -> dict:
    """Serialize a MediaPoolItem. ``full`` includes the entire clip-property map."""
    props = safe(mpi.GetClipProperty, default={}) or {}
    out = {
        "name": safe(mpi.GetName),
        "type": props.get("Type"),
        "format": props.get("Format"),
        "duration": props.get("Duration"),
        "frames": props.get("Frames"),
        "fps": props.get("FPS"),
        "resolution": props.get("Resolution"),
        "path": props.get("File Path"),
        "flags": safe(mpi.GetFlagList, default=[]),
        "clip_color": safe(mpi.GetClipColor),
        "unique_id": safe(mpi.GetUniqueId),
    }
    if full:
        out["properties"] = props
    return out


def item_to_dict(ti) -> dict:
    """Serialize a TimelineItem (a clip placed on the timeline)."""
    track = safe(ti.GetTrackTypeAndIndex, default=[None, None]) or [None, None]
    track_type = track[0] if isinstance(track, (list, tuple)) and len(track) > 0 else None
    track_index = track[1] if isinstance(track, (list, tuple)) and len(track) > 1 else None
    return {
        "name": safe(ti.GetName),
        "start": safe(ti.GetStart),
        "end": safe(ti.GetEnd),
        "duration": safe(ti.GetDuration),
        "enabled": safe(ti.GetClipEnabled),
        "left_offset": safe(ti.GetLeftOffset),
        "right_offset": safe(ti.GetRightOffset),
        "track_type": track_type,
        "track_index": track_index,
        "clip_color": safe(ti.GetClipColor),
        "unique_id": safe(ti.GetUniqueId),
    }


def timeline_to_dict(tl) -> dict:
    """Serialize a Timeline (counts, range and timecode, not its contents)."""
    return {
        "name": safe(tl.GetName),
        "start_frame": safe(tl.GetStartFrame),
        "end_frame": safe(tl.GetEndFrame),
        "start_timecode": safe(tl.GetStartTimecode),
        "current_timecode": safe(tl.GetCurrentTimecode),
        "video_tracks": safe(tl.GetTrackCount, "video"),
        "audio_tracks": safe(tl.GetTrackCount, "audio"),
        "subtitle_tracks": safe(tl.GetTrackCount, "subtitle"),
        "unique_id": safe(tl.GetUniqueId),
    }


def markers_to_list(markers: dict) -> list:
    """Flatten a Resolve marker dict ``{frame: {info}}`` into a sorted list."""
    if not markers:
        return []
    out = []
    for frame, info in markers.items():
        row = {"frame": frame}
        if isinstance(info, dict):
            row.update(info)
        out.append(row)
    out.sort(key=lambda r: r.get("frame", 0))
    return out
