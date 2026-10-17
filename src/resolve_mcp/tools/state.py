"""Orientation: read the current Resolve project and timeline state."""
from __future__ import annotations

from ..connection import get_project, get_resolve


def get_state() -> dict:
    """Orient in DaVinci Resolve. Call this first.

    Returns the product and version, the open project, every timeline in
    the project, and for the current timeline its frame rate, resolution,
    track counts, clip count and frame range.
    """
    resolve = get_resolve()
    project = get_project()

    count = project.GetTimelineCount()
    timelines = [
        project.GetTimelineByIndex(i).GetName() for i in range(1, count + 1)
    ]

    state: dict = {
        "product": resolve.GetProductName(),
        "version": resolve.GetVersionString(),
        "page": resolve.GetCurrentPage(),
        "project": project.GetName(),
        "timeline_count": count,
        "timelines": timelines,
    }

    timeline = project.GetCurrentTimeline()
    if timeline is not None:
        video_tracks = timeline.GetTrackCount("video")
        audio_tracks = timeline.GetTrackCount("audio")
        clip_count = sum(
            len(timeline.GetItemListInTrack("video", i) or [])
            for i in range(1, video_tracks + 1)
        )
        width = project.GetSetting("timelineResolutionWidth")
        height = project.GetSetting("timelineResolutionHeight")
        state["timeline"] = {
            "name": timeline.GetName(),
            "fps": project.GetSetting("timelineFrameRate"),
            "resolution": f"{width}x{height}",
            "video_tracks": video_tracks,
            "audio_tracks": audio_tracks,
            "video_clip_count": clip_count,
            "start_frame": timeline.GetStartFrame(),
            "end_frame": timeline.GetEndFrame(),
            "current_timecode": timeline.GetCurrentTimecode(),
        }

    return state


def register(mcp) -> None:
    mcp.tool()(get_state)
