"""Inspect and transform clips already on the timeline (TimelineItems).

Covers reading the items on each track, their transform/composite properties,
and the additive sizing setters (pan, tilt, zoom, rotation, opacity, crop, flip,
composite mode), plus enable, clip colour, Fusion comps and the long-running
Smart Reframe and Stabilize analyses. Colour grading lives in color.py and
markers in markers.py; this module owns geometry, not grades.
"""
from __future__ import annotations

from ..connection import ResolveError, get_timeline
from .. import serialize

# The documented SetProperty/GetProperty keys (README "Looking up Timeline item
# properties"). Used to validate set_item_property before touching Resolve so a
# typo returns a clear error instead of a silent no-op.
_TRANSFORM_KEYS = (
    "Pan",
    "Tilt",
    "ZoomX",
    "ZoomY",
    "ZoomGang",
    "RotationAngle",
    "AnchorPointX",
    "AnchorPointY",
    "Pitch",
    "Yaw",
    "FlipX",
    "FlipY",
    "CropLeft",
    "CropRight",
    "CropTop",
    "CropBottom",
    "CropSoftness",
    "CropRetain",
    "DynamicZoomEase",
    "CompositeMode",
    "Opacity",
    "Distortion",
    "RetimeProcess",
    "MotionEstimation",
    "Scaling",
    "ResizeFilter",
)
_VALID_KEYS = frozenset(_TRANSFORM_KEYS)

# A short, friendly subset surfaced in error messages so the agent can recover.
_COMMON_KEYS = (
    "Pan",
    "Tilt",
    "ZoomX",
    "ZoomY",
    "RotationAngle",
    "AnchorPointX",
    "AnchorPointY",
    "FlipX",
    "FlipY",
    "CropLeft",
    "CropRight",
    "CropTop",
    "CropBottom",
    "Opacity",
    "CompositeMode",
)

_TRACK_TYPES = ("video", "audio", "subtitle")


def _find_item(name: str):
    """Find the first TimelineItem named ``name`` across all video tracks.

    Resolve offers no item-by-name lookup, so we scan every video track with
    GetItemListInTrack and match on GetName(). Names can repeat; the first match
    wins and the total match count is reported by callers. Returns
    ``(item, total_matches, total_scanned)``; ``item`` is None when nothing
    matched. Transform/property work only applies to video items, so only video
    tracks are scanned here.
    """
    timeline = get_timeline()
    track_count = serialize.safe(timeline.GetTrackCount, "video", default=0) or 0
    first = None
    matches = 0
    scanned = 0
    for i in range(1, track_count + 1):
        items = serialize.safe(timeline.GetItemListInTrack, "video", i, default=[]) or []
        for item in items:
            scanned += 1
            if serialize.safe(item.GetName) == name:
                matches += 1
                if first is None:
                    first = item
    return first, matches, scanned


def _require_item(name: str):
    """Resolve a TimelineItem by name or raise a clear ResolveError."""
    item, matches, _ = _find_item(name)
    if item is None:
        raise ResolveError(
            f"No timeline item named {name!r} found on any video track. "
            "Open the timeline that holds it and check the name with "
            "list_timeline_items."
        )
    return item, matches


def list_timeline_items(track_type: str = "video", track_index: int | None = None) -> dict:
    """List the clips on a timeline track, serialized to plain dicts.

    Precondition: a timeline must be open. ``track_type`` is one of "video",
    "audio" or "subtitle". When ``track_index`` is None, every track of that
    type is walked; otherwise just that one (1-based). Each returned item carries
    its ``track`` (the track number) alongside the standard TimelineItem fields.
    """
    if track_type not in _TRACK_TYPES:
        raise ResolveError(
            f"Unknown track_type {track_type!r}. Use one of "
            f"{', '.join(_TRACK_TYPES)}."
        )

    timeline = get_timeline()
    total_tracks = serialize.safe(timeline.GetTrackCount, track_type, default=0) or 0

    if track_index is None:
        indices = range(1, total_tracks + 1)
    else:
        if track_index < 1 or track_index > total_tracks:
            raise ResolveError(
                f"track_index {track_index} is out of range; the timeline has "
                f"{total_tracks} {track_type} track(s)."
            )
        indices = range(track_index, track_index + 1)

    items: list = []
    for i in indices:
        track_items = serialize.safe(
            timeline.GetItemListInTrack, track_type, i, default=[]
        ) or []
        for ti in track_items:
            row = serialize.item_to_dict(ti)
            row["track"] = i
            items.append(row)

    return {
        "timeline": serialize.safe(timeline.GetName),
        "track_type": track_type,
        "track_count": total_tracks,
        "item_count": len(items),
        "items": items,
    }


def get_item_properties(item_name: str) -> dict:
    """Return a timeline item's full transform/composite property map plus basics.

    Precondition: a timeline holding a clip named ``item_name`` must be open.
    Looks up the first matching item, returns its GetProperty() map (Pan, Tilt,
    ZoomX/ZoomY, RotationAngle, crop, Opacity, CompositeMode, and so on) under
    ``properties`` together with the standard TimelineItem fields. ``matches``
    reports how many items share that name.
    """
    item, matches = _require_item(item_name)
    props = serialize.safe(item.GetProperty, default={})
    if not isinstance(props, dict):
        props = {}
    return {
        "name": item_name,
        "matches": matches,
        "basics": serialize.item_to_dict(item),
        "properties": props,
    }


def set_item_property(item_name: str, key: str, value) -> dict:
    """Set one transform/composite property on a timeline item and read it back.

    Precondition: a timeline holding ``item_name`` must be open. ``key`` must be
    a documented property (Pan, Tilt, ZoomX, ZoomY, RotationAngle, AnchorPointX,
    AnchorPointY, Pitch, Yaw, FlipX, FlipY, CropLeft/Right/Top/Bottom,
    CropSoftness, Opacity, CompositeMode, and others); an unknown key returns a
    clear error listing common keys without touching Resolve. ``value`` may be a
    number or a bool. Resolve clips out-of-range values silently, so the actual
    stored value is read back and returned under ``value``.
    """
    if key not in _VALID_KEYS:
        return {
            "status": "failed",
            "name": item_name,
            "key": key,
            "reason": f"Unknown property key {key!r}.",
            "common_keys": list(_COMMON_KEYS),
        }

    item, matches = _require_item(item_name)
    ok = bool(serialize.safe(item.SetProperty, key, value, default=False))
    actual = serialize.safe(item.GetProperty, key)
    return {
        "status": "done" if ok else "failed",
        "name": item_name,
        "matches": matches,
        "key": key,
        "requested": value,
        "value": actual,
    }


def set_item_transform(
    item_name: str,
    pan: float | None = None,
    tilt: float | None = None,
    zoom_x: float | None = None,
    zoom_y: float | None = None,
    rotation: float | None = None,
    opacity: float | None = None,
) -> dict:
    """Set several transform properties on a timeline item in one call.

    Precondition: a timeline holding ``item_name`` must be open. Each supplied
    argument maps to a SetProperty key: pan->Pan, tilt->Tilt, zoom_x->ZoomX,
    zoom_y->ZoomY, rotation->RotationAngle, opacity->Opacity. Arguments left None
    are not touched. Note ZoomX/ZoomY are 0.0-100.0 (some builds treat 1.0 as
    100%); every set value is read back and returned under ``results`` so the
    caller sees what Resolve actually stored. Out-of-range values are clipped.
    """
    item, matches = _require_item(item_name)

    requested = {
        "Pan": pan,
        "Tilt": tilt,
        "ZoomX": zoom_x,
        "ZoomY": zoom_y,
        "RotationAngle": rotation,
        "Opacity": opacity,
    }

    results: dict = {}
    any_set = False
    all_ok = True
    for key, val in requested.items():
        if val is None:
            continue
        any_set = True
        ok = bool(serialize.safe(item.SetProperty, key, val, default=False))
        all_ok = all_ok and ok
        results[key] = {
            "ok": ok,
            "requested": val,
            "value": serialize.safe(item.GetProperty, key),
        }

    if not any_set:
        return {
            "status": "noop",
            "name": item_name,
            "matches": matches,
            "reason": "No transform values supplied; pass at least one of pan, "
            "tilt, zoom_x, zoom_y, rotation, opacity.",
        }

    return {
        "status": "done" if all_ok else "failed",
        "name": item_name,
        "matches": matches,
        "results": results,
    }


def set_item_enabled(item_name: str, enabled: bool) -> dict:
    """Enable or disable a timeline item (mute the clip without removing it).

    Precondition: a timeline holding ``item_name`` must be open. Calls
    SetClipEnabled and reads the state back via GetClipEnabled.
    """
    item, matches = _require_item(item_name)
    ok = bool(serialize.safe(item.SetClipEnabled, enabled, default=False))
    return {
        "status": "done" if ok else "failed",
        "name": item_name,
        "matches": matches,
        "requested": enabled,
        "enabled": serialize.safe(item.GetClipEnabled),
    }


def set_item_clip_color(item_name: str, color: str) -> dict:
    """Set the clip colour label of a timeline item.

    Precondition: a timeline holding ``item_name`` must be open. ``color`` is a
    Resolve colour name (e.g. "Orange", "Apricot", "Yellow", "Lime", "Olive",
    "Green", "Teal", "Navy", "Blue", "Purple", "Violet", "Pink", "Tan",
    "Beige", "Brown", "Chocolate"). Calls SetClipColor and reads it back.
    """
    item, matches = _require_item(item_name)
    ok = bool(serialize.safe(item.SetClipColor, color, default=False))
    return {
        "status": "done" if ok else "failed",
        "name": item_name,
        "matches": matches,
        "requested": color,
        "clip_color": serialize.safe(item.GetClipColor),
    }


def add_fusion_comp(item_name: str) -> dict:
    """Add a new Fusion composition to a timeline item.

    Precondition: a timeline holding ``item_name`` must be open. Calls
    AddFusionComp and returns the resulting comp count and the list of comp
    names (GetFusionCompNameList) so the caller can confirm it was attached.
    """
    item, matches = _require_item(item_name)
    comp = serialize.safe(item.AddFusionComp)
    names = serialize.safe(item.GetFusionCompNameList, default=[]) or []
    count = serialize.safe(item.GetFusionCompCount, default=len(names))
    return {
        "status": "done" if comp is not None else "failed",
        "name": item_name,
        "matches": matches,
        "comp_count": count,
        "comp_names": list(names),
    }


def smart_reframe(item_name: str, confirm: bool = False) -> dict:
    """Run Smart Reframe on a timeline item (gated, long-running analysis).

    Precondition: a timeline holding ``item_name`` must be open; the project's
    output aspect ratio should differ from the source for reframing to have an
    effect. This kicks off an AI analysis that can take a while, so it is gated:
    call once to preview, then again with confirm=true to run it. Returns the
    SmartReframe() success flag.
    """
    from ..gate import confirm_required

    item, matches = _require_item(item_name)
    if not confirm:
        return confirm_required(
            f"run Smart Reframe on timeline item {item_name!r}",
            "This triggers a long-running AI reframing analysis.",
            name=item_name,
            matches=matches,
        )
    ok = bool(serialize.safe(item.SmartReframe, default=False))
    return {
        "status": "done" if ok else "failed",
        "name": item_name,
        "matches": matches,
    }


def stabilize(item_name: str, confirm: bool = False) -> dict:
    """Run Stabilize on a timeline item (gated, long-running analysis).

    Precondition: a timeline holding ``item_name`` must be open. This runs the
    stabilization analysis over the clip, which can take a while, so it is gated:
    call once to preview, then again with confirm=true to run it. Returns the
    Stabilize() success flag.
    """
    from ..gate import confirm_required

    item, matches = _require_item(item_name)
    if not confirm:
        return confirm_required(
            f"run Stabilize on timeline item {item_name!r}",
            "This triggers a long-running stabilization analysis.",
            name=item_name,
            matches=matches,
        )
    ok = bool(serialize.safe(item.Stabilize, default=False))
    return {
        "status": "done" if ok else "failed",
        "name": item_name,
        "matches": matches,
    }


def register(mcp) -> None:
    for fn in (
        list_timeline_items,
        get_item_properties,
        set_item_property,
        set_item_transform,
        set_item_enabled,
        set_item_clip_color,
        add_fusion_comp,
        smart_reframe,
        stabilize,
    ):
        mcp.tool()(fn)
