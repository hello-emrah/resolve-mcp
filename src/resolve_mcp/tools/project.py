"""Project lifecycle and project-wide settings."""
from __future__ import annotations

from ..connection import ResolveError, get_project, get_project_manager
from .. import serialize

# The handful of settings worth surfacing in get_project_info. Each is queried
# individually (faster than a full snapshot) and guarded, since GetSetting on an
# unknown key or wrong context returns a trivial result rather than raising.
_COMMON_SETTINGS = (
    "timelineFrameRate",
    "timelineResolutionWidth",
    "timelineResolutionHeight",
    "videoMonitorFormat",
    "colorScienceMode",
)


def list_projects() -> dict:
    """List every project in the current database folder, plus the current one.

    Reports the projects in the current folder, the name of the open project (or
    None when nothing is open), the current folder name, and the subfolders
    available to switch into. A project must be open for the open-project name to
    be populated; the folder and project lists work regardless.
    """
    pm = get_project_manager()
    projects = serialize.safe(pm.GetProjectListInCurrentFolder, default=[]) or []
    folders = serialize.safe(pm.GetFolderListInCurrentFolder, default=[]) or []
    current_folder = serialize.safe(pm.GetCurrentFolder, default="")

    open_project = pm.GetCurrentProject()
    current_name = serialize.safe(open_project.GetName) if open_project else None

    return {
        "projects": list(projects),
        "current_project": current_name,
        "current_folder": current_folder,
        "folders": list(folders),
    }


def get_project_info() -> dict:
    """Summarise the open project: name, timeline count and core settings.

    Returns the project name, how many timelines it holds, the timeline frame
    rate, resolution width and height, the colour science mode and video monitor
    format, plus the raw value of each curated setting. A project must be open or
    this raises. Missing settings come back as None rather than failing.
    """
    project = get_project()

    settings = {key: serialize.safe(project.GetSetting, key) for key in _COMMON_SETTINGS}
    width = settings.get("timelineResolutionWidth")
    height = settings.get("timelineResolutionHeight")

    return {
        "name": serialize.safe(project.GetName),
        "timeline_count": serialize.safe(project.GetTimelineCount, default=0),
        "frame_rate": settings.get("timelineFrameRate"),
        "resolution_width": width,
        "resolution_height": height,
        "resolution": f"{width}x{height}" if width and height else None,
        "color_science": settings.get("colorScienceMode"),
        "video_monitor_format": settings.get("videoMonitorFormat"),
        "settings": settings,
    }


def create_project(name: str) -> dict:
    """Create a new project by name in the current folder and switch to it.

    The name must be unique within the current database folder; Resolve returns
    nothing and the call fails if it is taken. Creating a project makes it the
    current project, switching context away from whatever was open, so save any
    in-progress work first. Additive, runs immediately.
    """
    pm = get_project_manager()
    project = pm.CreateProject(name)
    if project is None:
        return {
            "status": "failed",
            "name": name,
            "reason": "Could not create the project. The name may already be in use in this folder.",
        }

    current = pm.GetCurrentProject()
    became_current = bool(current) and serialize.safe(current.GetName) == name
    return {"status": "done", "name": name, "is_current": became_current}


def load_project(name: str) -> dict:
    """Save the open project, then load the named project from the current folder.

    The named project must exist in the current database folder; loading fails
    and returns nothing if there is no match. The currently open project is saved
    first so no work is lost, then this switches context to the loaded project.
    """
    pm = get_project_manager()

    saved = None
    if pm.GetCurrentProject() is not None:
        saved = bool(pm.SaveProject())

    project = pm.LoadProject(name)
    if project is None:
        return {
            "status": "failed",
            "name": name,
            "saved_previous": saved,
            "reason": "No project with that name was found in the current folder.",
        }

    return {"status": "done", "name": serialize.safe(project.GetName) or name, "saved_previous": saved}


def save_project() -> dict:
    """Save the open project under its own name.

    A project must be open. Returns whether Resolve reported the save succeeded.
    """
    pm = get_project_manager()
    if pm.GetCurrentProject() is None:
        raise ResolveError("No project is open to save.")

    ok = bool(pm.SaveProject())
    return {"status": "done" if ok else "failed", "saved": ok}


def get_project_settings(keys: list[str] | None = None) -> dict:
    """Read project settings: the named keys, or the whole snapshot when keys is None.

    A project must be open. Pass a list of setting keys (for example
    timelineFrameRate, timelineResolutionWidth, superScale) to read just those,
    each guarded so an unknown key comes back as None. Pass nothing to get the
    full snapshot of every queryable project setting as a flat dict.
    """
    project = get_project()

    if keys is None:
        snapshot = serialize.safe(project.GetSetting, default={}) or {}
        return {"settings": dict(snapshot) if isinstance(snapshot, dict) else {}}

    return {"settings": {key: serialize.safe(project.GetSetting, key) for key in keys}}


def set_project_setting(key: str, value: str) -> dict:
    """Set one project setting and read the value back to confirm it stuck.

    A project must be open. Values are always strings; numbers and booleans are
    coerced to text before being applied. Some keys take enumerated forms, for
    instance timelineFrameRate accepts drop-frame values like "29.97 DF". Some
    settings are read only in certain contexts and will fail. Additive, runs
    immediately; returns the new value Resolve reports after the change.
    """
    project = get_project()

    ok = bool(project.SetSetting(key, str(value)))
    new_value = serialize.safe(project.GetSetting, key)
    return {
        "status": "done" if ok else "failed",
        "key": key,
        "requested": str(value),
        "value": new_value,
    }


def register(mcp) -> None:
    for fn in (
        list_projects,
        get_project_info,
        create_project,
        load_project,
        save_project,
        get_project_settings,
        set_project_setting,
    ):
        mcp.tool()(fn)
