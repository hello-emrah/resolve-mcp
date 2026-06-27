"""Markers on the timeline, on a timeline item, or on a media-pool clip.

One set of tools, switched by a ``target`` argument:
  - ``"timeline"`` operates on the current timeline.
  - ``"item"`` operates on a TimelineItem (a clip placed on a video track),
    found by name via ``target_name``.
  - ``"clip"`` operates on a MediaPoolItem (a source clip in the media pool),
    found by name via ``target_name``.

Frame numbers are an OFFSET from the start of the chosen object, not an
absolute timecode frame. For a timeline, frame 0 is the timeline start, so a
marker at the playhead sits at ``current_frame - start_frame``, not at the
timecode frame. For an item or clip, frame 0 is that media's own first frame.
"""
from __future__ import annotations

from ..connection import ResolveError, get_media_pool, get_timeline
from ..gate import confirm_required
from .. import serialize

# Marker colours Resolve accepts. AddMarker silently fails (returns False) on
# anything else, so validate up front and tell the caller what is allowed.
VALID_COLORS = [
    "Blue", "Cyan", "Green", "Yellow", "Red", "Pink", "Purple", "Fuchsia",
    "Rose", "Lavender", "Sky", "Mint", "Lemon", "Sand", "Cocoa", "Cream",
]


def _timeline():
    """Return the current timeline, raising ResolveError when none is open."""
    return get_timeline()


def _item(name: str):
    """Find a TimelineItem on the current timeline by clip name.

    Scans every video track in order and returns the first item whose
    GetName() matches. Raises ResolveError if no timeline is open or no
    item carries that name.
    """
    timeline = get_timeline()
    track_count = serialize.safe(timeline.GetTrackCount, "video", default=0) or 0
    for index in range(1, track_count + 1):
        items = serialize.safe(
            timeline.GetItemListInTrack, "video", index, default=[]
        ) or []
        for item in items:
            if serialize.safe(item.GetName) == name:
                return item
    raise ResolveError(
        f"No timeline item named '{name}' on any video track of the current "
        "timeline. Check the name with the inspection tools."
    )


def _clip(name: str):
    """Find a MediaPoolItem anywhere in the media pool by clip name.

    Walks the root folder and every sub-folder, returning the first clip whose
    GetName() matches. Raises ResolveError if no project/media pool is open or
    no clip carries that name.
    """
    pool = get_media_pool()
    root = serialize.safe(pool.GetRootFolder)
    if root is None:
        raise ResolveError("Could not reach the media pool root folder.")

    stack = [root]
    while stack:
        folder = stack.pop()
        clips = serialize.safe(folder.GetClipList, default=[]) or []
        for clip in clips:
            if serialize.safe(clip.GetName) == name:
                return clip
        subs = serialize.safe(folder.GetSubFolderList, default=[]) or []
        stack.extend(subs)
    raise ResolveError(
        f"No media-pool clip named '{name}'. Check the name with the media "
        "tools."
    )


def _resolve_target(target: str, target_name: str | None):
    """Map a ``target``/``target_name`` pair to the marker-bearing object.

    Returns the object whose AddMarker/GetMarkers/DeleteMarker* methods the
    tools call. Raises ResolveError on an unknown target or a missing name.
    """
    if target == "timeline":
        return _timeline()
    if target == "item":
        if not target_name:
            raise ResolveError("target 'item' requires target_name (the clip name).")
        return _item(target_name)
    if target == "clip":
        if not target_name:
            raise ResolveError("target 'clip' requires target_name (the clip name).")
        return _clip(target_name)
    raise ResolveError(
        f"Unknown target '{target}'. Use 'timeline', 'item' or 'clip'."
    )


def add_marker(
    frame: int,
    color: str = "Blue",
    name: str = "",
    note: str = "",
    duration: int = 1,
    custom_data: str = "",
    target: str = "timeline",
    target_name: str | None = None,
) -> dict:
    """Add a marker at a frame offset on the timeline, an item, or a clip.

    ``frame`` is an OFFSET from the start of the chosen object, not an absolute
    timecode frame. For the timeline, 0 is the timeline start. ``color`` must be
    one of the valid marker colours (Blue, Cyan, Green, Yellow, Red, Pink,
    Purple, Fuchsia, Rose, Lavender, Sky, Mint, Lemon, Sand, Cocoa, Cream).
    ``duration`` is in frames. ``custom_data`` attaches a hidden string for
    later lookup.

    target selects where the marker lives: "timeline" (current timeline,
    target_name ignored), "item" (a TimelineItem named target_name on a video
    track) or "clip" (a MediaPoolItem named target_name).

    Returns ``status: "added"`` on success. Resolve returns False (reported as
    ``status: "failed"``) when a marker already exists at that frame or the
    frame is out of range.
    """
    if color not in VALID_COLORS:
        raise ResolveError(
            f"Invalid marker color '{color}'. Valid colours: "
            + ", ".join(VALID_COLORS)
        )

    obj = _resolve_target(target, target_name)
    ok = serialize.safe(
        obj.AddMarker, frame, color, name, note, duration, custom_data,
        default=False,
    )
    return {
        "status": "added" if ok else "failed",
        "target": target,
        "target_name": target_name,
        "frame": frame,
        "color": color,
        "name": name,
        "duration": duration,
        "reason": None if ok else (
            "Resolve refused the marker. A marker may already exist at this "
            "frame, or the frame is out of range for this object."
        ),
    }


def list_markers(target: str = "timeline", target_name: str | None = None) -> dict:
    """List every marker on the timeline, an item, or a clip.

    target selects the source: "timeline" (current timeline), "item" (a
    TimelineItem named target_name) or "clip" (a MediaPoolItem named
    target_name). Each marker reports its frame offset, colour, name, note,
    duration and custom data; the list is sorted by frame. Frames are offsets
    from the object's start, not absolute timecode frames.
    """
    obj = _resolve_target(target, target_name)
    markers = serialize.safe(obj.GetMarkers, default={}) or {}
    rows = serialize.markers_to_list(markers)
    return {
        "target": target,
        "target_name": target_name,
        "count": len(rows),
        "markers": rows,
    }


def delete_marker(
    frame: int,
    target: str = "timeline",
    target_name: str | None = None,
    confirm: bool = False,
) -> dict:
    """Delete the marker at a frame offset on the timeline, an item, or a clip.

    GATED: call once to preview, again with ``confirm=true`` to delete. ``frame``
    is an offset from the object's start, not an absolute timecode frame. target
    selects the source: "timeline", "item" (target_name) or "clip"
    (target_name).

    Returns ``status: "deleted"`` on success. Resolve returns False (reported as
    ``status: "failed"``) when no marker exists at that frame.
    """
    obj = _resolve_target(target, target_name)
    where = target if target == "timeline" else f"{target} '{target_name}'"
    if not confirm:
        return confirm_required(
            f"delete the marker at frame {frame} on the {where}",
            "this removes a single marker and cannot be undone via this tool",
            target=target,
            target_name=target_name,
            frame=frame,
        )

    ok = serialize.safe(obj.DeleteMarkerAtFrame, frame, default=False)
    return {
        "status": "deleted" if ok else "failed",
        "target": target,
        "target_name": target_name,
        "frame": frame,
        "reason": None if ok else "No marker exists at that frame.",
    }


def delete_markers_by_color(
    color: str,
    target: str = "timeline",
    target_name: str | None = None,
    confirm: bool = False,
) -> dict:
    """Delete every marker of one colour on the timeline, an item, or a clip.

    GATED: call once to preview, again with ``confirm=true`` to delete. ``color``
    must be a valid marker colour, or the literal "All" to clear every marker
    regardless of colour. target selects the source: "timeline", "item"
    (target_name) or "clip" (target_name).

    Returns ``status: "deleted"`` on success. Resolve returns False (reported as
    ``status: "failed"``) when no marker of that colour exists.
    """
    if color != "All" and color not in VALID_COLORS:
        raise ResolveError(
            f"Invalid marker color '{color}'. Use 'All' to clear every marker, "
            "or one of: " + ", ".join(VALID_COLORS)
        )

    obj = _resolve_target(target, target_name)
    where = target if target == "timeline" else f"{target} '{target_name}'"
    label = "all markers" if color == "All" else f"all '{color}' markers"
    if not confirm:
        return confirm_required(
            f"delete {label} on the {where}",
            "this cannot be undone via this tool",
            target=target,
            target_name=target_name,
            color=color,
        )

    ok = serialize.safe(obj.DeleteMarkersByColor, color, default=False)
    return {
        "status": "deleted" if ok else "failed",
        "target": target,
        "target_name": target_name,
        "color": color,
        "reason": None if ok else f"No markers of colour '{color}' to delete.",
    }


def register(mcp) -> None:
    for fn in (add_marker, list_markers, delete_marker, delete_markers_by_color):
        mcp.tool()(fn)
