"""Timeline lifecycle, tracks, and timeline-level settings."""
from __future__ import annotations

from ..connection import (
    ResolveError,
    get_media_pool,
    get_project,
    get_timeline,
)
from ..gate import confirm_required
from .. import serialize

_TRACK_TYPES = ("video", "audio", "subtitle")


def _all_timelines(project) -> list:
    """Return every timeline object in the project, in index order (may be empty)."""
    count = serialize.safe(project.GetTimelineCount, default=0) or 0
    out = []
    for i in range(1, count + 1):
        tl = serialize.safe(project.GetTimelineByIndex, i)
        if tl is not None:
            out.append(tl)
    return out


def _find_timeline(project, name: str):
    """Return the timeline object whose name matches, or None."""
    for tl in _all_timelines(project):
        if serialize.safe(tl.GetName) == name:
            return tl
    return None


def _check_track_type(track_type: str) -> str:
    """Normalise and validate a track type, raising on an unknown value."""
    tt = (track_type or "").strip().lower()
    if tt not in _TRACK_TYPES:
        raise ResolveError(
            f"Unknown track type '{track_type}'. Use one of: video, audio, subtitle."
        )
    return tt


def list_timelines() -> dict:
    """List every timeline in the open project and flag the current one.

    Precondition: a project must be open. Each timeline is serialized with its
    name, frame range, timecode and track counts. The 'current' key holds the
    name of the currently loaded timeline, or None if none is loaded.
    """
    project = get_project()
    timelines = [serialize.timeline_to_dict(tl) for tl in _all_timelines(project)]
    current = serialize.safe(project.GetCurrentTimeline)
    current_name = serialize.safe(current.GetName) if current is not None else None
    return {
        "count": len(timelines),
        "current": current_name,
        "timelines": timelines,
    }


def create_empty_timeline(name: str) -> dict:
    """Create a new empty timeline and load it as the current timeline.

    Precondition: a project must be open. Adds a timeline named 'name' to the
    media pool (the name must be unique) and sets it current. Returns the new
    timeline's serialized state, or status 'failed' if creation did not succeed
    (most often a duplicate name).
    """
    pool = get_media_pool()
    tl = pool.CreateEmptyTimeline(name)
    if tl is None:
        return {
            "status": "failed",
            "name": name,
            "reason": "Could not create the timeline. The name may already be in use.",
        }
    project = get_project()
    set_current = bool(serialize.safe(project.SetCurrentTimeline, tl, default=False))
    out = serialize.timeline_to_dict(tl)
    out["status"] = "created"
    out["set_current"] = set_current
    return out


def set_current_timeline(name: str) -> dict:
    """Load the named timeline as the current timeline.

    Precondition: a project must be open and a timeline named 'name' must exist.
    Returns status 'done' on success or 'failed' if Resolve rejected the switch.
    """
    project = get_project()
    tl = _find_timeline(project, name)
    if tl is None:
        raise ResolveError(f"No timeline named '{name}' exists in this project.")
    ok = bool(serialize.safe(project.SetCurrentTimeline, tl, default=False))
    return {"status": "done" if ok else "failed", "name": name}


def rename_timeline(name: str, new_name: str) -> dict:
    """Rename a timeline. The new name must be unique within the project.

    Precondition: a project must be open and a timeline named 'name' must exist.
    Returns status 'done' on success or 'failed' if the new name is not unique.
    """
    project = get_project()
    tl = _find_timeline(project, name)
    if tl is None:
        raise ResolveError(f"No timeline named '{name}' exists in this project.")
    ok = bool(serialize.safe(tl.SetName, new_name, default=False))
    return {
        "status": "done" if ok else "failed",
        "name": new_name if ok else name,
        "previous_name": name,
        "reason": None if ok else "The new name may already be in use.",
    }


def duplicate_timeline(name: str, new_name: str | None = None) -> dict:
    """Duplicate a timeline, optionally naming the copy.

    Precondition: a project must be open and a timeline named 'name' must exist.
    If 'new_name' is omitted Resolve auto-names the copy. Returns the new
    timeline's serialized state, or status 'failed' if duplication did not
    succeed.
    """
    project = get_project()
    tl = _find_timeline(project, name)
    if tl is None:
        raise ResolveError(f"No timeline named '{name}' exists in this project.")
    if new_name is None:
        dup = serialize.safe(tl.DuplicateTimeline)
    else:
        dup = serialize.safe(tl.DuplicateTimeline, new_name)
    if dup is None:
        return {
            "status": "failed",
            "source": name,
            "reason": "Could not duplicate the timeline. The requested name may already be in use.",
        }
    out = serialize.timeline_to_dict(dup)
    out["status"] = "duplicated"
    out["source"] = name
    return out


def delete_timeline(name: str, confirm: bool = False) -> dict:
    """Delete a timeline from the media pool. Irreversible. GATED.

    Precondition: a project must be open and a timeline named 'name' must exist.
    Resolves and previews the target before any change; call again with
    confirm=true to actually delete it. Returns status 'done' or 'failed'.
    """
    project = get_project()
    tl = _find_timeline(project, name)
    if tl is None:
        raise ResolveError(f"No timeline named '{name}' exists in this project.")

    if not confirm:
        return confirm_required(
            f"delete timeline '{name}'",
            "this removes the timeline from the media pool and cannot be undone",
            timeline=serialize.timeline_to_dict(tl),
        )

    pool = get_media_pool()
    # DeleteTimelines wants the Timeline object whose backing MediaPoolItem is
    # the deletion target; the Timeline handle itself is what the API accepts.
    ok = bool(serialize.safe(pool.DeleteTimelines, [tl], default=False))
    return {"status": "done" if ok else "failed", "name": name}


def get_timeline_settings(keys: list[str] | None = None) -> dict:
    """Read the current timeline's settings as a snapshot or specific keys.

    Precondition: a timeline must be open. With no 'keys' returns the full
    settings snapshot (Timeline.GetSetting() with no argument). With 'keys'
    returns only those settingName values; an unknown key yields an empty
    string. Returns {'settings': {key: value, ...}}.
    """
    timeline = get_timeline()
    if keys:
        settings = {
            key: serialize.safe(timeline.GetSetting, key, default="") or ""
            for key in keys
        }
    else:
        snapshot = serialize.safe(timeline.GetSetting, default={})
        settings = snapshot if isinstance(snapshot, dict) else {}
    return {"timeline": serialize.safe(timeline.GetName), "settings": settings}


def set_timeline_setting(key: str, value: str) -> dict:
    """Set a single timeline setting and read the stored value back.

    Precondition: a timeline must be open. 'key' is a settingName, 'value' its
    string value (see the timeline settings reference). Returns status 'done' or
    'failed', plus the value Resolve actually stored after the write.
    """
    timeline = get_timeline()
    ok = bool(serialize.safe(timeline.SetSetting, key, value, default=False))
    stored = serialize.safe(timeline.GetSetting, key, default="")
    return {
        "status": "done" if ok else "failed",
        "key": key,
        "requested": value,
        "stored": stored,
    }


def set_timeline_start_timecode(timecode: str) -> dict:
    """Set the current timeline's start timecode (e.g. '01:00:00:00').

    Precondition: a timeline must be open. Returns status 'done' or 'failed'
    plus the start timecode read back after the write.
    """
    timeline = get_timeline()
    ok = bool(serialize.safe(timeline.SetStartTimecode, timecode, default=False))
    return {
        "status": "done" if ok else "failed",
        "requested": timecode,
        "start_timecode": serialize.safe(timeline.GetStartTimecode),
    }


def add_track(track_type: str, sub_type: str | None = None) -> dict:
    """Add a track to the current timeline and return the new track count.

    Precondition: a timeline must be open. 'track_type' is 'video', 'audio' or
    'subtitle'. For audio, 'sub_type' is the channel format ('mono', 'stereo',
    '5.1', etc.) and defaults to 'mono'; it is ignored for video and subtitle.
    Returns status 'done' or 'failed' and the resulting track count for that
    type.
    """
    tt = _check_track_type(track_type)
    timeline = get_timeline()
    if tt == "audio":
        st = sub_type or "mono"
        ok = bool(serialize.safe(timeline.AddTrack, tt, st, default=False))
    else:
        ok = bool(serialize.safe(timeline.AddTrack, tt, default=False))
    return {
        "status": "done" if ok else "failed",
        "track_type": tt,
        "sub_type": (sub_type or "mono") if tt == "audio" else None,
        "track_count": serialize.safe(timeline.GetTrackCount, tt, default=0),
    }


def delete_track(track_type: str, index: int, confirm: bool = False) -> dict:
    """Delete a track from the current timeline by 1-based index. GATED.

    Precondition: a timeline must be open. 'track_type' is 'video', 'audio' or
    'subtitle'; 'index' is 1-based and must be within the current track count.
    Previews the target (including any clips it holds) before any change; call
    again with confirm=true to delete it. Returns status 'done' or 'failed'.
    """
    tt = _check_track_type(track_type)
    timeline = get_timeline()
    count = serialize.safe(timeline.GetTrackCount, tt, default=0) or 0
    if index < 1 or index > count:
        raise ResolveError(
            f"Track index {index} is out of range; the timeline has {count} "
            f"{tt} track(s) (use 1..{count})."
        )

    if not confirm:
        name = serialize.safe(timeline.GetTrackName, tt, index)
        clips = serialize.safe(timeline.GetItemListInTrack, tt, index, default=[]) or []
        return confirm_required(
            f"delete {tt} track {index}",
            "deleting a track removes it and any clips on it; this cannot be undone",
            track_type=tt,
            index=index,
            track_name=name,
            clip_count=len(clips),
        )

    ok = bool(serialize.safe(timeline.DeleteTrack, tt, index, default=False))
    return {
        "status": "done" if ok else "failed",
        "track_type": tt,
        "index": index,
        "track_count": serialize.safe(timeline.GetTrackCount, tt, default=0),
    }


def set_track_name(track_type: str, index: int, name: str) -> dict:
    """Rename a track on the current timeline by 1-based index.

    Precondition: a timeline must be open. 'track_type' is 'video', 'audio' or
    'subtitle'; 'index' is 1-based and must be within the current track count.
    Returns status 'done' or 'failed' and the track name read back.
    """
    tt = _check_track_type(track_type)
    timeline = get_timeline()
    count = serialize.safe(timeline.GetTrackCount, tt, default=0) or 0
    if index < 1 or index > count:
        raise ResolveError(
            f"Track index {index} is out of range; the timeline has {count} "
            f"{tt} track(s) (use 1..{count})."
        )
    ok = bool(serialize.safe(timeline.SetTrackName, tt, index, name, default=False))
    return {
        "status": "done" if ok else "failed",
        "track_type": tt,
        "index": index,
        "name": serialize.safe(timeline.GetTrackName, tt, index),
    }


def set_track_enabled(track_type: str, index: int, enabled: bool) -> dict:
    """Enable or disable a track on the current timeline by 1-based index.

    Precondition: a timeline must be open. 'track_type' is 'video', 'audio' or
    'subtitle'; 'index' is 1-based and must be within the current track count.
    A disabled track does not play back or render. Returns status 'done' or
    'failed' and the track's enabled state read back.
    """
    tt = _check_track_type(track_type)
    timeline = get_timeline()
    count = serialize.safe(timeline.GetTrackCount, tt, default=0) or 0
    if index < 1 or index > count:
        raise ResolveError(
            f"Track index {index} is out of range; the timeline has {count} "
            f"{tt} track(s) (use 1..{count})."
        )
    ok = bool(serialize.safe(timeline.SetTrackEnable, tt, index, bool(enabled), default=False))
    return {
        "status": "done" if ok else "failed",
        "track_type": tt,
        "index": index,
        "enabled": serialize.safe(timeline.GetIsTrackEnabled, tt, index),
    }


def set_track_locked(track_type: str, index: int, locked: bool) -> dict:
    """Lock or unlock a track on the current timeline by 1-based index.

    Precondition: a timeline must be open. 'track_type' is 'video', 'audio' or
    'subtitle'; 'index' is 1-based and must be within the current track count.
    A locked track cannot be edited until unlocked. Returns status 'done' or
    'failed' and the track's locked state read back.
    """
    tt = _check_track_type(track_type)
    timeline = get_timeline()
    count = serialize.safe(timeline.GetTrackCount, tt, default=0) or 0
    if index < 1 or index > count:
        raise ResolveError(
            f"Track index {index} is out of range; the timeline has {count} "
            f"{tt} track(s) (use 1..{count})."
        )
    ok = bool(serialize.safe(timeline.SetTrackLock, tt, index, bool(locked), default=False))
    return {
        "status": "done" if ok else "failed",
        "track_type": tt,
        "index": index,
        "locked": serialize.safe(timeline.GetIsTrackLocked, tt, index),
    }


def register(mcp) -> None:
    for fn in (
        list_timelines,
        create_empty_timeline,
        set_current_timeline,
        rename_timeline,
        duplicate_timeline,
        delete_timeline,
        get_timeline_settings,
        set_timeline_setting,
        set_timeline_start_timecode,
        add_track,
        delete_track,
        set_track_name,
        set_track_enabled,
        set_track_locked,
    ):
        mcp.tool()(fn)
