"""Assemble clips, titles and generators onto the timeline."""
from __future__ import annotations

from ..connection import ResolveError, get_media_pool, get_project, get_timeline
from ..gate import confirm_required
from .. import serialize


def _all_media_pool_clips() -> list:
    """Return every MediaPoolItem in the project, walking all folders depth-first."""
    pool = get_media_pool()
    root = pool.GetRootFolder()
    if root is None:
        return []
    clips: list = []
    stack = [root]
    while stack:
        folder = stack.pop()
        for clip in (serialize.safe(folder.GetClipList, default=[]) or []):
            clips.append(clip)
        for sub in (serialize.safe(folder.GetSubFolderList, default=[]) or []):
            stack.append(sub)
    return clips


def _resolve_clips_by_name(clip_names: list[str]) -> tuple[list, list[str]]:
    """Match MediaPoolItems by exact GetName(). Returns (found_items, missing_names).

    Preserves the order of ``clip_names``; a duplicate name resolves to the
    first matching media-pool clip.
    """
    by_name: dict[str, object] = {}
    for clip in _all_media_pool_clips():
        name = serialize.safe(clip.GetName)
        if name is not None and name not in by_name:
            by_name[name] = clip
    found: list = []
    missing: list[str] = []
    for name in clip_names:
        clip = by_name.get(name)
        if clip is None:
            missing.append(name)
        else:
            found.append(clip)
    return found, missing


def _all_video_items(timeline) -> list:
    """Return every TimelineItem across all video tracks of the given timeline."""
    items: list = []
    track_count = serialize.safe(timeline.GetTrackCount, "video", default=0) or 0
    for i in range(1, track_count + 1):
        for item in (serialize.safe(timeline.GetItemListInTrack, "video", i, default=[]) or []):
            items.append(item)
    return items


def _resolve_items_by_name(timeline, item_names: list[str]) -> tuple[list, list[str]]:
    """Match TimelineItems on the current timeline by exact GetName().

    Returns (found_items, missing_names) preserving the order of ``item_names``;
    a duplicate name resolves to the first matching item across the video tracks.
    """
    by_name: dict[str, object] = {}
    for item in _all_video_items(timeline):
        name = serialize.safe(item.GetName)
        if name is not None and name not in by_name:
            by_name[name] = item
    found: list = []
    missing: list[str] = []
    for name in item_names:
        item = by_name.get(name)
        if item is None:
            missing.append(name)
        else:
            found.append(item)
    return found, missing


def create_timeline_from_clips(name: str, clip_names: list[str]) -> dict:
    """Create a new timeline named ``name`` from media-pool clips and make it current.

    Resolves each name in ``clip_names`` to a MediaPoolItem by its exact clip
    name (searched across every media-pool folder), then builds a timeline that
    appends them in the given order. A project must be open. Every name must
    match a media-pool clip; if any are missing nothing is created.

    Returns the serialized new timeline, or status "failed" with a reason.
    """
    found, missing = _resolve_clips_by_name(clip_names)
    if missing:
        return {
            "status": "failed",
            "reason": "clips not found in media pool",
            "missing": missing,
        }
    if not found:
        return {"status": "failed", "reason": "no clips given"}

    pool = get_media_pool()
    timeline = pool.CreateTimelineFromClips(name, found)
    if not timeline:
        return {"status": "failed", "reason": "CreateTimelineFromClips returned no timeline", "name": name}

    get_project().SetCurrentTimeline(timeline)
    return {"status": "done", "timeline": serialize.timeline_to_dict(timeline)}


def append_to_timeline(
    clip_names: list[str],
    track_index: int | None = None,
    start_frame: int | None = None,
    end_frame: int | None = None,
) -> dict:
    """Append media-pool clips to the end of the current timeline.

    A current timeline must already exist; call create_timeline_from_clips first
    if none is open. Resolves each name in ``clip_names`` to a MediaPoolItem by
    its exact clip name (searched across every media-pool folder). The optional
    ``start_frame`` / ``end_frame`` set source in/out points (applied to every
    clip in this call); ``track_index`` (1-based) places them on a specific
    video track. Every name must match a media-pool clip; if any are missing
    nothing is appended.

    Returns the list of appended timeline items, or status "failed" with a reason.
    """
    try:
        get_timeline()
    except ResolveError as exc:
        raise ResolveError(
            "No timeline is open to append to. Create one first with "
            "create_timeline_from_clips."
        ) from exc

    found, missing = _resolve_clips_by_name(clip_names)
    if missing:
        return {
            "status": "failed",
            "reason": "clips not found in media pool",
            "missing": missing,
        }
    if not found:
        return {"status": "failed", "reason": "no clips given"}

    clip_infos: list[dict] = []
    for clip in found:
        info: dict = {"mediaPoolItem": clip}
        if start_frame is not None:
            info["startFrame"] = start_frame
        if end_frame is not None:
            info["endFrame"] = end_frame
        if track_index is not None:
            info["trackIndex"] = track_index
        clip_infos.append(info)

    pool = get_media_pool()
    appended = pool.AppendToTimeline(clip_infos)
    if not appended:
        return {"status": "failed", "reason": "AppendToTimeline appended nothing"}

    return {
        "status": "done",
        "appended": [serialize.item_to_dict(ti) for ti in appended],
        "count": len(appended),
    }


def insert_title(title_name: str = "Text") -> dict:
    """Insert a standard title at the playhead on the current timeline.

    A timeline must be open. ``title_name`` must match an entry in Resolve's
    title list; the always-present plain title is "Text". For an animated
    Fusion title use insert_fusion_title instead.

    Returns the new timeline item, or status "failed" if the name is unknown.
    """
    timeline = get_timeline()
    item = timeline.InsertTitleIntoTimeline(title_name)
    if not item:
        return {
            "status": "failed",
            "reason": "InsertTitleIntoTimeline returned nothing; title name may be unknown",
            "title_name": title_name,
        }
    return {"status": "done", "item": serialize.item_to_dict(item)}


def insert_fusion_title(title_name: str = "Text+") -> dict:
    """Insert a Fusion (animated) title at the playhead on the current timeline.

    A timeline must be open. ``title_name`` must match an entry in Resolve's
    Fusion title list; the always-present animated title is "Text+".

    Returns the new timeline item, or status "failed" if the name is unknown.
    """
    timeline = get_timeline()
    item = timeline.InsertFusionTitleIntoTimeline(title_name)
    if not item:
        return {
            "status": "failed",
            "reason": "InsertFusionTitleIntoTimeline returned nothing; title name may be unknown",
            "title_name": title_name,
        }
    return {"status": "done", "item": serialize.item_to_dict(item)}


def insert_generator(generator_name: str) -> dict:
    """Insert a generator at the playhead on the current timeline.

    A timeline must be open. ``generator_name`` must match an entry in Resolve's
    generator list (common: "Solid Color", "Gray Scale", "Window").

    Returns the new timeline item, or status "failed" if the name is unknown.
    """
    timeline = get_timeline()
    item = timeline.InsertGeneratorIntoTimeline(generator_name)
    if not item:
        return {
            "status": "failed",
            "reason": "InsertGeneratorIntoTimeline returned nothing; generator name may be unknown",
            "generator_name": generator_name,
        }
    return {"status": "done", "item": serialize.item_to_dict(item)}


def create_compound_clip(item_names: list[str], name: str | None = None) -> dict:
    """Compound the named timeline items on the current timeline into one clip.

    A timeline must be open. Resolves each name in ``item_names`` to a
    TimelineItem by its exact name across the video tracks, then nests them into
    a single compound clip (optionally named ``name``). Every name must match an
    item on the timeline; if any are missing nothing is created.

    Returns the created compound timeline item, or status "failed" with a reason.
    """
    timeline = get_timeline()
    found, missing = _resolve_items_by_name(timeline, item_names)
    if missing:
        return {
            "status": "failed",
            "reason": "items not found on current timeline",
            "missing": missing,
        }
    if not found:
        return {"status": "failed", "reason": "no items given"}

    if name:
        item = timeline.CreateCompoundClip(found, {"name": name})
    else:
        item = timeline.CreateCompoundClip(found)
    if not item:
        return {"status": "failed", "reason": "CreateCompoundClip returned nothing"}
    return {"status": "done", "item": serialize.item_to_dict(item)}


def create_fusion_clip(item_names: list[str]) -> dict:
    """Turn the named timeline items on the current timeline into one Fusion clip.

    A timeline must be open. Resolves each name in ``item_names`` to a
    TimelineItem by its exact name across the video tracks, then combines them
    into a single Fusion clip for compositing. Every name must match an item on
    the timeline; if any are missing nothing is created.

    Returns the created Fusion timeline item, or status "failed" with a reason.
    """
    timeline = get_timeline()
    found, missing = _resolve_items_by_name(timeline, item_names)
    if missing:
        return {
            "status": "failed",
            "reason": "items not found on current timeline",
            "missing": missing,
        }
    if not found:
        return {"status": "failed", "reason": "no items given"}

    item = timeline.CreateFusionClip(found)
    if not item:
        return {"status": "failed", "reason": "CreateFusionClip returned nothing"}
    return {"status": "done", "item": serialize.item_to_dict(item)}


def detect_scene_cuts(confirm: bool = False) -> dict:
    """Auto-detect scene changes and razor the current timeline at each cut. GATED.

    A timeline must be open. This rewrites the timeline by adding cuts in place,
    so it is gated: the first call previews, a second call with confirm=true
    applies it.

    Returns status "done" / "failed" once applied.
    """
    timeline = get_timeline()
    if not confirm:
        return confirm_required(
            "detect scene cuts on the current timeline",
            "razors the timeline at every detected scene change; run analysis can take a while",
            timeline=serialize.safe(timeline.GetName),
        )
    ok = timeline.DetectSceneCuts()
    return {"status": "done" if ok else "failed", "timeline": serialize.safe(timeline.GetName)}


def delete_timeline_items(
    item_names: list[str],
    ripple: bool = False,
    confirm: bool = False,
) -> dict:
    """Delete named clips from the current timeline. GATED.

    A timeline must be open. Resolves each name in ``item_names`` to a
    TimelineItem by its exact name across the video tracks. With ``ripple`` true
    the following clips shift left to close the gap; with it false a gap is left.
    Gated: the first call previews the resolved targets and the ripple flag, a
    second call with confirm=true deletes them. This cannot be undone via the API.

    Returns status "done" / "failed", the names deleted and any that were missing.
    """
    timeline = get_timeline()
    found, missing = _resolve_items_by_name(timeline, item_names)

    if not confirm:
        return confirm_required(
            f"delete {len(found)} timeline item(s)",
            "this cannot be undone"
            + (" and ripples the following clips left" if ripple else ""),
            ripple=ripple,
            targets=[serialize.safe(it.GetName) for it in found],
            missing=missing,
        )

    if not found:
        return {
            "status": "failed",
            "reason": "no matching items on the current timeline",
            "missing": missing,
        }

    ok = timeline.DeleteClips(found, ripple)
    return {
        "status": "done" if ok else "failed",
        "deleted": [serialize.safe(it.GetName) for it in found],
        "ripple": ripple,
        "missing": missing,
    }


def register(mcp) -> None:
    for fn in (
        create_timeline_from_clips,
        append_to_timeline,
        insert_title,
        insert_fusion_title,
        insert_generator,
        create_compound_clip,
        create_fusion_clip,
        detect_scene_cuts,
        delete_timeline_items,
    ):
        mcp.tool()(fn)
