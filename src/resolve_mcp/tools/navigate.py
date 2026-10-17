"""Navigation: switch pages and move the timeline playhead."""
from __future__ import annotations

from ..connection import ResolveError, get_project, get_resolve, get_timeline
from .. import serialize

# Resolve accepts exactly these page names for OpenPage.
VALID_PAGES = ("media", "cut", "edit", "fusion", "color", "fairlight", "deliver")


def open_page(page: str) -> dict:
    """Switch DaVinci Resolve to a named page.

    Use this to move the UI to the page a later action needs (the Color page
    for grading, the Edit page for cutting, the Deliver page for rendering).
    Valid pages: media, cut, edit, fusion, color, fairlight, deliver.
    Rejects any other name. Returns the page actually displayed afterward.
    """
    name = (page or "").strip().lower()
    if name not in VALID_PAGES:
        raise ResolveError(
            f"Invalid page '{page}'. Valid pages: {', '.join(VALID_PAGES)}."
        )

    resolve = get_resolve()
    ok = resolve.OpenPage(name)
    current = resolve.GetCurrentPage()
    return {
        "status": "done" if ok else "failed",
        "requested": name,
        "page": current,
    }


def get_playhead() -> dict:
    """Report where the playhead is: page, timeline, timecode and current clip.

    Use this to orient before moving the playhead or acting on the clip under
    it. Returns the current page, the open timeline's name, its current
    timecode, and the video timeline item at the playhead (or None if there is
    no clip there). Requires an open project and timeline.
    """
    resolve = get_resolve()
    timeline = get_timeline()

    item = serialize.safe(timeline.GetCurrentVideoItem)
    return {
        "page": resolve.GetCurrentPage(),
        "timeline": serialize.safe(timeline.GetName),
        "current_timecode": serialize.safe(timeline.GetCurrentTimecode),
        "current_item": serialize.item_to_dict(item) if item else None,
    }


def set_playhead_timecode(timecode: str) -> dict:
    """Move the playhead to a timecode on the open timeline.

    Pass a timecode string in "HH:MM:SS:FF" form (drop-frame uses ';' before
    the frames, e.g. "00:01:00;02"). Works on the Cut, Edit, Color, Fairlight
    and Deliver pages. Returns the timecode read back from the timeline so the
    caller can confirm the move landed. Requires an open timeline.
    """
    timeline = get_timeline()
    ok = timeline.SetCurrentTimecode(timecode)
    return {
        "status": "done" if ok else "failed",
        "requested": timecode,
        "current_timecode": serialize.safe(timeline.GetCurrentTimecode),
    }


def set_playhead_frame(frame: int) -> dict:
    """Move the playhead to an absolute timeline frame number on the open timeline.

    The frame number is absolute, the same scale that ``list_timeline_items``
    and an item's ``start``/``end`` report, not an offset from zero. A timeline
    whose start timecode is 01:00:00:00 begins at frame 108000 at 30 fps, so
    pass an item's ``start`` to jump straight to that clip. The number is
    converted to a timecode using the project frame rate and the timeline start;
    frames below the start are clamped to the start. Returns the resulting
    timecode read back from the timeline. Requires an open project and timeline.
    """
    project = get_project()
    timeline = get_timeline()

    start_frame = serialize.safe(timeline.GetStartFrame, default=0) or 0
    try:
        frame = int(frame)
    except (TypeError, ValueError):
        raise ResolveError(f"Frame must be an integer, got {frame!r}.")
    if frame < start_frame:
        frame = start_frame

    fps_setting = project.GetSetting("timelineFrameRate")
    try:
        fps = float(fps_setting)
    except (TypeError, ValueError):
        raise ResolveError(
            "Could not read the timeline frame rate to convert the frame "
            "number. Open a timeline and try set_playhead_timecode instead."
        )
    if fps <= 0:
        raise ResolveError("Timeline frame rate is not positive; cannot convert.")

    # Drop-frame timelines report a start timecode with ';' before the frames.
    start_tc = serialize.safe(timeline.GetStartTimecode, default="") or ""
    drop_frame = ";" in start_tc

    timecode = _frame_to_timecode(frame, fps, drop_frame)
    ok = timeline.SetCurrentTimecode(timecode)
    return {
        "status": "done" if ok else "failed",
        "requested_frame": frame,
        "requested_timecode": timecode,
        "current_timecode": serialize.safe(timeline.GetCurrentTimecode),
    }


def get_current_item() -> dict:
    """Return the video timeline item under the playhead, serialized.

    Use this to inspect the clip currently at the playhead (its name, range,
    track and offsets) before acting on it. Returns the serialized item, or a
    "no current item" status when nothing sits under the playhead. Requires an
    open timeline.
    """
    timeline = get_timeline()
    item = serialize.safe(timeline.GetCurrentVideoItem)
    if not item:
        return {
            "status": "no current item",
            "detail": "No video clip is under the playhead on the open timeline.",
            "item": None,
        }
    return {"status": "ok", "item": serialize.item_to_dict(item)}


def _frame_to_timecode(frame: int, fps: float, drop_frame: bool) -> str:
    """Convert a timeline frame number to an "HH:MM:SS:FF" timecode string.

    Rounds the frame rate to the nominal integer count for whole-frame display.
    Drop-frame (NTSC 29.97 / 59.94) skips frame numbers each minute except every
    tenth minute; the frames separator is ';'. Otherwise the separator is ':'.
    """
    frame = max(0, int(frame))
    nominal = int(round(fps))
    if nominal <= 0:
        nominal = 1

    if drop_frame:
        # Drop two frames per minute at ~29.97, four per minute at ~59.94,
        # except on every tenth minute. drop = round(fps * 0.066666...).
        drop = int(round(fps * (2.0 / 30.0)))
        frames_per_min = nominal * 60 - drop
        frames_per_10min = nominal * 600 - drop * 9

        d = frame // frames_per_10min
        m = frame % frames_per_10min
        if m > drop:
            frame += drop * 9 * d + drop * ((m - drop) // frames_per_min)
        else:
            frame += drop * 9 * d

        ff = frame % nominal
        ss = (frame // nominal) % 60
        mm = (frame // (nominal * 60)) % 60
        hh = frame // (nominal * 3600)
        return f"{hh:02d}:{mm:02d}:{ss:02d};{ff:02d}"

    ff = frame % nominal
    ss = (frame // nominal) % 60
    mm = (frame // (nominal * 60)) % 60
    hh = (frame // (nominal * 3600)) % 24
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


def register(mcp) -> None:
    for fn in (
        open_page,
        get_playhead,
        set_playhead_timecode,
        set_playhead_frame,
        get_current_item,
    ):
        mcp.tool()(fn)
