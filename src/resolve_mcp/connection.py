"""Lazy connection to a running DaVinci Resolve Studio instance.

The Resolve scripting API is served by the bundled ``fusionscript`` native
module, reachable from an external process only when Resolve Studio is running
with External scripting set to Local (Preferences, System, General). This module
finds that library across platforms, connects once, caches the handle and
revives it if Resolve restarts.
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

_MAC_API = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
_MAC_LIB = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
_WIN_API = r"%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"
_WIN_LIB = r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll"
_LIN_API = "/opt/resolve/Developer/Scripting"
_LIN_LIB = "/opt/resolve/libs/Fusion/fusionscript.so"

_ENABLE_HINT = (
    "Make sure DaVinci Resolve Studio is running and that Preferences, System, "
    "General, External scripting using is set to Local."
)


class ResolveError(RuntimeError):
    """Raised when Resolve is unreachable or in an unexpected state."""


def _platform_paths() -> tuple[str, str]:
    if sys.platform == "darwin":
        return _MAC_API, _MAC_LIB
    if sys.platform.startswith("win"):
        return os.path.expandvars(_WIN_API), _WIN_LIB
    return _LIN_API, _LIN_LIB


def _load_module():
    default_api, default_lib = _platform_paths()
    api = os.environ.get("RESOLVE_SCRIPT_API") or default_api
    lib = os.environ.get("RESOLVE_SCRIPT_LIB") or default_lib
    os.environ.setdefault("RESOLVE_SCRIPT_API", api)
    os.environ.setdefault("RESOLVE_SCRIPT_LIB", lib)

    modules = str(Path(api) / "Modules")
    if modules not in sys.path:
        sys.path.append(modules)
    try:
        import DaVinciResolveScript as dvr  # type: ignore
    except ImportError as exc:
        raise ResolveError(
            f"Could not load the Resolve scripting API from {modules}. "
            "Is DaVinci Resolve Studio installed? " + _ENABLE_HINT
        ) from exc
    return dvr


_lock = threading.Lock()
_resolve = None


def _alive(handle) -> bool:
    try:
        return bool(handle.GetProductName())
    except Exception:
        return False


def get_resolve():
    """Return a live Resolve handle, connecting or reconnecting as needed."""
    global _resolve
    with _lock:
        if _resolve is not None and _alive(_resolve):
            return _resolve
        dvr = _load_module()
        handle = dvr.scriptapp("Resolve")
        if handle is None:
            raise ResolveError("DaVinci Resolve is not reachable. " + _ENABLE_HINT)
        _resolve = handle
        return _resolve


def get_project_manager():
    """Return the Project Manager."""
    return get_resolve().GetProjectManager()


def get_media_storage():
    """Return the Media Storage object for browsing volumes and files."""
    return get_resolve().GetMediaStorage()


def get_project():
    """Return the open project, or raise if none is open."""
    project = get_project_manager().GetCurrentProject()
    if project is None:
        raise ResolveError("No project is open in Resolve.")
    return project


def get_media_pool():
    """Return the current project's Media Pool, or raise if no project is open."""
    pool = get_project().GetMediaPool()
    if pool is None:
        raise ResolveError("Could not reach the Media Pool of the open project.")
    return pool


def get_timeline():
    """Return the current timeline, or raise if none is open."""
    timeline = get_project().GetCurrentTimeline()
    if timeline is None:
        raise ResolveError("No timeline is open in the current project.")
    return timeline
