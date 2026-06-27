"""Fairlight and audio: insert audio, transcription, voice isolation, captions, sync."""
from __future__ import annotations

from ..connection import (
    ResolveError,
    get_media_pool,
    get_project,
    get_resolve,
    get_timeline,
)
from ..gate import confirm_required
from .. import serialize


# Map a small friendly language set onto the resolve.AUTO_CAPTION_* enum names.
_CAPTION_LANGS = {
    "auto": "AUTO_CAPTION_AUTO",
    "english": "AUTO_CAPTION_ENGLISH",
    "spanish": "AUTO_CAPTION_SPANISH",
    "french": "AUTO_CAPTION_FRENCH",
    "german": "AUTO_CAPTION_GERMAN",
}

# Map a friendly sync mode onto the resolve.AUDIO_SYNC_* enum names.
_SYNC_MODES = {
    "waveform": "AUDIO_SYNC_WAVEFORM",
    "timecode": "AUDIO_SYNC_TIMECODE",
}


def _enum(resolve, name: str):
    """Read a resolve.* enum attribute by name, raising if it is missing.

    The auto-caption and audio-sync settings dicts are keyed by enum values
    taken off the resolve handle (resolve.SUBTITLE_LANGUAGE, resolve.AUDIO_SYNC_MODE
    and so on), not plain strings. This guards against an absent enum on an
    older build rather than letting an AttributeError escape.
    """
    value = getattr(resolve, name, None)
    if value is None:
        raise ResolveError(
            f"This Resolve build does not expose resolve.{name}; the operation "
            "is unavailable here."
        )
    return value


def _walk_clips(folder):
    """Yield every MediaPoolItem in a folder and all nested subfolders."""
    for clip in folder.GetClipList() or []:
        yield clip
    for sub in folder.GetSubFolderList() or []:
        yield from _walk_clips(sub)


def _find_clip(name: str):
    """Find the first MediaPoolItem in the media pool whose name matches ``name``.

    Returns the native item or None. Walks the root folder recursively.
    """
    pool = get_media_pool()
    root = pool.GetRootFolder()
    if root is None:
        raise ResolveError("Could not reach the root folder of the Media Pool.")
    for clip in _walk_clips(root):
        if serialize.safe(clip.GetName) == name:
            return clip
    return None


def insert_audio_at_playhead(
    media_path: str,
    start_offset_samples: int = 0,
    duration_samples: int = 0,
) -> dict:
    """Insert an audio file at the playhead on the selected Fairlight track.

    Precondition: Resolve must be on the Fairlight page with an audio track
    selected; the call targets that selected track at the current playhead.
    ``media_path`` is an absolute path to the audio file. ``start_offset_samples``
    trims the head of the source, ``duration_samples`` caps how much is inserted
    (0 means from the offset to the end of the source). Additive, runs immediately.

    Returns ``{"status": "done"|"failed", "media_path": ..., ...}``. A "failed"
    status usually means the page is not Fairlight or no audio track is selected.
    """
    project = get_project()
    ok = project.InsertAudioToCurrentTrackAtPlayhead(
        media_path, int(start_offset_samples), int(duration_samples)
    )
    return {
        "status": "done" if ok else "failed",
        "media_path": media_path,
        "start_offset_samples": int(start_offset_samples),
        "duration_samples": int(duration_samples),
        "hint": None
        if ok
        else "Switch to the Fairlight page and select an audio track first.",
    }


def transcribe_audio(clip_name: str | None = None, confirm: bool = False) -> dict:
    """Transcribe speech to text for a clip, or the whole media pool. Long-running.

    Gated: call with confirm=true to actually start the transcription, which can
    take a while. With ``clip_name`` set, transcribes that single MediaPoolItem.
    With ``clip_name`` None, transcribes every clip in the media pool root folder
    and its nested subfolders. Requires a project to be open.

    Returns ``{"status": "done"|"failed", "scope": ...}``; "failed" means Resolve
    declined (e.g. the clip carries no audio).
    """
    if clip_name is not None:
        clip = _find_clip(clip_name)
        if clip is None:
            raise ResolveError(f"No clip named '{clip_name}' in the Media Pool.")
        target = f"clip '{clip_name}'"
    else:
        target = "the entire media pool"

    if not confirm:
        return confirm_required(
            f"transcribe audio for {target}",
            "this can take a while depending on duration",
            scope="clip" if clip_name else "media_pool",
            clip_name=clip_name,
        )

    if clip_name is not None:
        ok = serialize.safe(clip.GetName) and clip.TranscribeAudio()
    else:
        pool = get_media_pool()
        root = pool.GetRootFolder()
        if root is None:
            raise ResolveError("Could not reach the root folder of the Media Pool.")
        ok = root.TranscribeAudio()

    return {
        "status": "done" if ok else "failed",
        "scope": "clip" if clip_name else "media_pool",
        "clip_name": clip_name,
    }


def clear_transcription(clip_name: str | None = None) -> dict:
    """Clear an existing audio transcription for a clip, or the whole media pool.

    With ``clip_name`` set, clears that single MediaPoolItem's transcription.
    With ``clip_name`` None, clears every clip in the media pool root folder and
    its nested subfolders. Requires a project to be open. Additive housekeeping,
    runs immediately.

    Returns ``{"status": "done"|"failed", "scope": ...}``.
    """
    if clip_name is not None:
        clip = _find_clip(clip_name)
        if clip is None:
            raise ResolveError(f"No clip named '{clip_name}' in the Media Pool.")
        ok = clip.ClearTranscription()
        scope = "clip"
    else:
        pool = get_media_pool()
        root = pool.GetRootFolder()
        if root is None:
            raise ResolveError("Could not reach the root folder of the Media Pool.")
        ok = root.ClearTranscription()
        scope = "media_pool"

    return {
        "status": "done" if ok else "failed",
        "scope": scope,
        "clip_name": clip_name,
    }


def set_voice_isolation(track_index: int, enabled: bool, amount: int = 50) -> dict:
    """Enable or disable Voice Isolation on an audio track of the current timeline.

    Precondition: a timeline must be open. ``track_index`` is 1-based and must be
    between 1 and the audio track count. ``amount`` is the isolation strength,
    clamped to 0-100. Additive, runs immediately.

    Returns ``{"status": "done"|"failed", "track_index": ..., "isEnabled": ...,
    "amount": ...}``. A "failed" status usually means the track index is out of
    range.
    """
    timeline = get_timeline()
    amount = max(0, min(100, int(amount)))
    state = {"isEnabled": bool(enabled), "amount": amount}
    ok = timeline.SetVoiceIsolationState(int(track_index), state)
    return {
        "status": "done" if ok else "failed",
        "track_index": int(track_index),
        "isEnabled": bool(enabled),
        "amount": amount,
        "hint": None
        if ok
        else "track_index must be between 1 and the audio track count.",
    }


def create_subtitles_from_audio(language: str = "auto", confirm: bool = False) -> dict:
    """Generate a subtitle track from the timeline's audio. Long-running.

    Gated: call with confirm=true to actually run the auto-caption pass, which
    can take a while. Precondition: a timeline with audio must be open.
    ``language`` is one of "auto", "english", "spanish", "french", "german"
    (default "auto", which auto-detects). Builds the autoCaptionSettings dict
    keyed by resolve.SUBTITLE_LANGUAGE with the matching resolve.AUTO_CAPTION_*
    value.

    Returns ``{"status": "done"|"failed", "language": ...}``; "failed" means
    Resolve declined (e.g. the timeline has no detectable speech).
    """
    key = language.lower()
    if key not in _CAPTION_LANGS:
        raise ResolveError(
            f"Unknown language '{language}'. Choose one of: "
            + ", ".join(sorted(_CAPTION_LANGS))
        )

    timeline = get_timeline()

    if not confirm:
        return confirm_required(
            f"create subtitles from audio ({key})",
            "this can take a while depending on timeline duration",
            language=key,
        )

    resolve = get_resolve()
    lang_key = _enum(resolve, "SUBTITLE_LANGUAGE")
    lang_value = _enum(resolve, _CAPTION_LANGS[key])
    settings = {lang_key: lang_value}

    ok = timeline.CreateSubtitlesFromAudio(settings)
    return {
        "status": "done" if ok else "failed",
        "language": key,
    }


def auto_sync_audio(
    clip_names: list[str],
    mode: str = "waveform",
    confirm: bool = False,
) -> dict:
    """Sync separately recorded audio to video clips in the media pool. Long-running.

    Gated: call with confirm=true to actually run the sync. ``clip_names`` lists
    MediaPoolItem names to sync together; the set must include at least one video
    clip and at least one audio clip. ``mode`` is "waveform" (match by sound) or
    "timecode" (match by embedded timecode), default "waveform". Requires a
    project to be open and every named clip to exist in the Media Pool.

    Returns ``{"status": "done"|"failed", "mode": ..., "clip_names": ...}``;
    "failed" means Resolve could not align the supplied clips.
    """
    key = mode.lower()
    if key not in _SYNC_MODES:
        raise ResolveError(
            f"Unknown sync mode '{mode}'. Choose 'waveform' or 'timecode'."
        )
    if not clip_names or len(clip_names) < 2:
        raise ResolveError(
            "auto_sync_audio needs at least two clips: one video and one audio."
        )

    items = []
    missing = []
    for name in clip_names:
        clip = _find_clip(name)
        if clip is None:
            missing.append(name)
        else:
            items.append(clip)
    if missing:
        raise ResolveError(
            "These clips were not found in the Media Pool: " + ", ".join(missing)
        )

    if not confirm:
        return confirm_required(
            f"auto-sync audio across {len(items)} clips ({key})",
            "ensure the set includes at least one video and one audio clip",
            mode=key,
            clip_names=clip_names,
        )

    resolve = get_resolve()
    mode_key = _enum(resolve, "AUDIO_SYNC_MODE")
    mode_value = _enum(resolve, _SYNC_MODES[key])
    settings = {mode_key: mode_value}

    pool = get_media_pool()
    ok = pool.AutoSyncAudio(items, settings)
    return {
        "status": "done" if ok else "failed",
        "mode": key,
        "clip_names": clip_names,
    }


def register(mcp) -> None:
    for fn in (
        insert_audio_at_playhead,
        transcribe_audio,
        clear_transcription,
        set_voice_isolation,
        create_subtitles_from_audio,
        auto_sync_audio,
    ):
        mcp.tool()(fn)
