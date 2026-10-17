"""Colour grading: color groups, the node graph, LUTs, CDL, grade copy and stills.

Most tools here drive the Color page. Resolve's colour getters and graph object
are only meaningful when the Color page is open and a clip is selected, so the
caller should usually run navigate.open_page("color") first. Node indices are
1-based throughout, matching the Resolve UI and scripting API.
"""
from __future__ import annotations

from ..connection import ResolveError, get_project, get_timeline
from ..gate import confirm_required
from .. import serialize


def _find_item(item_name: str):
    """Resolve a TimelineItem by name across every video track of the open timeline.

    Raises ResolveError when no timeline is open or no clip matches. Returns the
    first matching TimelineItem; clip names are not guaranteed unique, so the
    first hit in track order wins.
    """
    timeline = get_timeline()
    video_tracks = serialize.safe(timeline.GetTrackCount, "video", default=0) or 0
    for track in range(1, video_tracks + 1):
        items = serialize.safe(
            timeline.GetItemListInTrack, "video", track, default=[]
        ) or []
        for item in items:
            if serialize.safe(item.GetName) == item_name:
                return item
    raise ResolveError(
        f"No video clip named '{item_name}' on the current timeline. "
        "Check the name with a timeline-inspection tool first."
    )


def _find_group(group_name: str):
    """Resolve a ColorGroup by name in the open project, or raise."""
    project = get_project()
    groups = serialize.safe(project.GetColorGroupsList, default=[]) or []
    for group in groups:
        if serialize.safe(group.GetName) == group_name:
            return group
    raise ResolveError(
        f"No color group named '{group_name}' in this project. "
        "Create it first with add_color_group."
    )


def list_color_groups() -> dict:
    """List every color group in the open project with its clip count.

    Requires an open project and timeline (clip counts are read against the
    current timeline). Returns each group's name and how many clips on the
    current timeline belong to it.
    """
    project = get_project()
    groups = serialize.safe(project.GetColorGroupsList, default=[]) or []
    out = []
    for group in groups:
        clips = serialize.safe(group.GetClipsInTimeline, default=[]) or []
        out.append({"name": serialize.safe(group.GetName), "clip_count": len(clips)})
    return {"count": len(out), "groups": out}


def add_color_group(name: str) -> dict:
    """Create a new color group in the open project. Additive, runs immediately.

    'name' must be unique among existing groups. Returns the created group name,
    or a failed status if Resolve rejected the name (e.g. a duplicate).
    """
    project = get_project()
    group = serialize.safe(project.AddColorGroup, name)
    if group is None:
        return {
            "status": "failed",
            "name": name,
            "reason": "Resolve refused to create the group. The name may already be in use.",
        }
    return {"status": "done", "name": serialize.safe(group.GetName) or name}


def assign_to_color_group(item_name: str, group_name: str) -> dict:
    """Assign a timeline clip to an existing color group. Color page recommended.

    Resolves the clip by name on the current timeline and the group by name in
    the project, then assigns the clip to the group. Both must already exist.
    """
    item = _find_item(item_name)
    group = _find_group(group_name)
    ok = bool(serialize.safe(item.AssignToColorGroup, group, default=False))
    return {
        "status": "done" if ok else "failed",
        "item": item_name,
        "group": group_name,
    }


def get_node_graph_info(item_name: str) -> dict:
    """Inspect a clip's color node graph: node count, plus each node's label and tools.

    Open the Color page first; the node graph is read from the clip's first node
    layer. Per-node enabled state is not readable through the API, so only the
    label (GetNodeLabel) and the tools used in each node (GetToolsInNode) are
    returned. Node indices in the result are 1-based.
    """
    item = _find_item(item_name)
    graph = serialize.safe(item.GetNodeGraph)
    if graph is None:
        raise ResolveError(
            f"Could not read the node graph for '{item_name}'. "
            "Open the Color page and select the clip, then retry."
        )
    num_nodes = serialize.safe(graph.GetNumNodes, default=0) or 0
    nodes = []
    for index in range(1, num_nodes + 1):
        nodes.append(
            {
                "index": index,
                "label": serialize.safe(graph.GetNodeLabel, index, default=""),
                "tools": serialize.safe(graph.GetToolsInNode, index, default=[]) or [],
            }
        )
    return {"item": item_name, "num_nodes": num_nodes, "nodes": nodes}


def set_node_lut(item_name: str, node_index: int, lut_path: str) -> dict:
    """Apply a LUT to one node of a clip's grade. Color page; node_index is 1-based.

    Refreshes the project LUT list first (RefreshLUTList) so newly added LUTs are
    discoverable, then sets the LUT on the given node. 'lut_path' may be absolute
    or relative to a known LUT folder; Resolve only accepts LUTs it has already
    discovered. Fails if the node index is out of range or the path is unknown.
    """
    item = _find_item(item_name)
    project = get_project()
    serialize.safe(project.RefreshLUTList)
    graph = serialize.safe(item.GetNodeGraph)
    if graph is None:
        raise ResolveError(
            f"Could not read the node graph for '{item_name}'. "
            "Open the Color page and select the clip, then retry."
        )
    ok = bool(serialize.safe(graph.SetLUT, node_index, lut_path, default=False))
    return {
        "status": "done" if ok else "failed",
        "item": item_name,
        "node_index": node_index,
        "lut_path": lut_path,
        "reason": None if ok else "Invalid node index or a LUT path Resolve has not discovered.",
    }


def set_node_enabled(item_name: str, node_index: int, enabled: bool) -> dict:
    """Enable or disable one node of a clip's grade. Color page; node_index is 1-based.

    Toggles the node at node_index on the clip's first node layer. Fails if the
    node index is out of range (1 <= node_index <= node count).
    """
    item = _find_item(item_name)
    graph = serialize.safe(item.GetNodeGraph)
    if graph is None:
        raise ResolveError(
            f"Could not read the node graph for '{item_name}'. "
            "Open the Color page and select the clip, then retry."
        )
    ok = bool(serialize.safe(graph.SetNodeEnabled, node_index, enabled, default=False))
    return {
        "status": "done" if ok else "failed",
        "item": item_name,
        "node_index": node_index,
        "enabled": enabled,
        "reason": None if ok else "Node index is likely out of range.",
    }


def set_cdl(
    item_name: str,
    slope: str,
    offset: str,
    power: str,
    saturation: str,
    node_index: int = 1,
) -> dict:
    """Apply an ASC CDL (slope, offset, power, saturation) to one node of a clip.

    Open the Color page first. 'slope', 'offset' and 'power' are space-separated
    RGB triples, e.g. "1.0 1.0 1.0"; 'saturation' is a single value, e.g. "1.0".
    'node_index' is 1-based (default 1). Fails if the values or node index are
    invalid.
    """
    item = _find_item(item_name)
    cdl = {
        "NodeIndex": str(node_index),
        "Slope": slope,
        "Offset": offset,
        "Power": power,
        "Saturation": saturation,
    }
    ok = bool(serialize.safe(item.SetCDL, cdl, default=False))
    return {
        "status": "done" if ok else "failed",
        "item": item_name,
        "node_index": node_index,
        "cdl": {
            "slope": slope,
            "offset": offset,
            "power": power,
            "saturation": saturation,
        },
        "reason": None if ok else "Resolve rejected the CDL values or node index.",
    }


def copy_grade(from_item: str, to_items: list[str]) -> dict:
    """Copy the grade from one clip to one or more other clips. Color page recommended.

    Resolves the source clip and every target clip by name on the current
    timeline, then copies the source's current node-stack layer grade onto the
    same layer of each target. Reports the targets it could not resolve and
    whether Resolve accepted the copy.
    """
    source = _find_item(from_item)
    targets = []
    missing = []
    for name in to_items:
        try:
            targets.append(_find_item(name))
        except ResolveError:
            missing.append(name)
    if not targets:
        return {
            "status": "failed",
            "from": from_item,
            "reason": "None of the target clips were found on the current timeline.",
            "missing": missing,
        }
    ok = bool(serialize.safe(source.CopyGrades, targets, default=False))
    return {
        "status": "done" if ok else "failed",
        "from": from_item,
        "to": [name for name in to_items if name not in missing],
        "missing": missing,
        "reason": None if ok else "Resolve rejected the grade copy.",
    }


def reset_grades(item_name: str, confirm: bool = False) -> dict:
    """Reset all grades on a clip's node graph. Destructive; gated by confirm.

    Open the Color page first. Resolves the clip by name, then clears every grade
    on its node graph. This cannot be undone through the API, so it only runs
    when confirm is True; otherwise it returns a preview of what it would do.
    """
    item = _find_item(item_name)
    if not confirm:
        return confirm_required(
            f"reset all grades on clip '{item_name}'",
            "every node grade on this clip will be cleared; this cannot be undone",
            item=item_name,
        )
    graph = serialize.safe(item.GetNodeGraph)
    if graph is None:
        raise ResolveError(
            f"Could not read the node graph for '{item_name}'. "
            "Open the Color page and select the clip, then retry."
        )
    ok = bool(serialize.safe(graph.ResetAllGrades, default=False))
    return {
        "status": "done" if ok else "failed",
        "item": item_name,
        "reason": None if ok else "Resolve reported the grade reset did not complete.",
    }


def grab_still() -> dict:
    """Grab a still of the current clip into the gallery. Requires the Color page open.

    Additive: captures the still at the current playhead on the current timeline
    into the Stills gallery. The Color page must be open and a clip current, or
    Resolve grabs nothing. Returns whether a still was captured.
    """
    timeline = get_timeline()
    still = serialize.safe(timeline.GrabStill)
    captured = still is not None
    return {
        "status": "done" if captured else "failed",
        "reason": None if captured else (
            "No still was grabbed. Open the Color page with a clip at the playhead and retry."
        ),
    }


def register(mcp) -> None:
    for fn in (
        list_color_groups,
        add_color_group,
        assign_to_color_group,
        get_node_graph_info,
        set_node_lut,
        set_node_enabled,
        set_cdl,
        copy_grade,
        reset_grades,
        grab_still,
    ):
        mcp.tool()(fn)
