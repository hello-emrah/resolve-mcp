"""Media: browse storage, import into the media pool, manage bins and clip properties."""
from __future__ import annotations

from ..connection import (
    ResolveError,
    get_media_pool,
    get_media_storage,
    get_project,
)
from ..gate import confirm_required
from .. import serialize


def _find_clip(name: str):
    """Locate a MediaPoolItem by GetName(), searching the current bin then the root.

    Resolve has no direct lookup, so we iterate folder.GetClipList() and match on
    name. Returns the first matching MediaPoolItem, or None if nothing matches.
    """
    pool = get_media_pool()
    seen_ids: set[int] = set()
    folders = []

    current = serialize.safe(pool.GetCurrentFolder)
    if current is not None:
        folders.append(current)
    root = serialize.safe(pool.GetRootFolder)
    if root is not None and id(root) not in {id(f) for f in folders}:
        folders.append(root)

    for folder in folders:
        for clip in serialize.safe(folder.GetClipList, default=[]) or []:
            if id(clip) in seen_ids:
                continue
            seen_ids.add(id(clip))
            if serialize.safe(clip.GetName) == name:
                return clip
    return None


def _find_subfolder(name: str, start=None):
    """Find a subfolder by name under ``start`` (defaults to the root folder).

    Searches recursively so a bin nested below the root is still reachable.
    Returns the first matching Folder, or None.
    """
    pool = get_media_pool()
    if start is None:
        start = serialize.safe(pool.GetRootFolder)
    if start is None:
        return None
    stack = [start]
    while stack:
        folder = stack.pop()
        for sub in serialize.safe(folder.GetSubFolderList, default=[]) or []:
            if serialize.safe(sub.GetName) == name:
                return sub
            stack.append(sub)
    return None


def browse_storage(path: str | None = None) -> dict:
    """List Resolve's Media Storage volumes, or the contents of one folder.

    With no path, returns the mounted volumes shown in Resolve's Media Storage
    panel. With an absolute folder path, returns its subfolders and its media
    and file listings (media entries may be logically consolidated). Use this to
    discover what is available to import; it does not touch the media pool.
    """
    storage = get_media_storage()
    if path is None:
        return {
            "volumes": serialize.safe(storage.GetMountedVolumeList, default=[]) or [],
        }
    return {
        "path": path,
        "folders": serialize.safe(storage.GetSubFolderList, path, default=[]) or [],
        "files": serialize.safe(storage.GetFileList, path, default=[]) or [],
    }


def import_media(paths: list[str]) -> dict:
    """Import file or folder paths into the CURRENT media-pool bin.

    Pass a list of absolute file or folder paths (folders import their media
    contents). Imports land in whichever bin is current; call set_current_bin
    first to target a different one. Returns the created clips and a count.
    """
    if not paths:
        raise ResolveError("Provide at least one file or folder path to import.")
    pool = get_media_pool()
    clips = pool.ImportMedia(paths)
    if not clips:
        return {
            "status": "failed",
            "reason": "ImportMedia returned nothing; check the paths exist and are supported media.",
            "imported_count": 0,
            "clips": [],
        }
    serialized = [serialize.clip_to_dict(c) for c in clips]
    return {
        "status": "done",
        "imported_count": len(serialized),
        "clips": serialized,
    }


def list_media_pool(bin_name: str | None = None, full: bool = False) -> dict:
    """List the clips and subfolders in the current bin, or a named subfolder.

    With no bin_name, walks the current media-pool folder. With a bin_name,
    resolves that subfolder by name (searching from the root) and walks it. Set
    full=True to include every clip property per clip. A project must be open.
    """
    pool = get_media_pool()
    if bin_name is None:
        folder = serialize.safe(pool.GetCurrentFolder)
        if folder is None:
            raise ResolveError("No current media-pool folder is available.")
    else:
        folder = _find_subfolder(bin_name)
        if folder is None:
            raise ResolveError(f"No media-pool bin named '{bin_name}' was found.")

    clips = serialize.safe(folder.GetClipList, default=[]) or []
    subfolders = serialize.safe(folder.GetSubFolderList, default=[]) or []
    return {
        "bin": serialize.safe(folder.GetName),
        "clip_count": len(clips),
        "clips": [serialize.clip_to_dict(c, full=full) for c in clips],
        "subfolders": [serialize.safe(s.GetName) for s in subfolders],
    }


def create_bin(name: str, parent: str | None = None) -> dict:
    """Create a subfolder (bin) in the media pool. Additive, runs immediately.

    The bin is added under ``parent`` (resolved by name from the root) when given,
    otherwise under the current folder. A project must be open. Returns the new
    bin name on success.
    """
    pool = get_media_pool()
    if parent is None:
        parent_folder = serialize.safe(pool.GetCurrentFolder)
        if parent_folder is None:
            parent_folder = serialize.safe(pool.GetRootFolder)
    else:
        parent_folder = _find_subfolder(parent)
        if parent_folder is None:
            raise ResolveError(f"No parent bin named '{parent}' was found.")
    if parent_folder is None:
        raise ResolveError("Could not resolve a parent folder for the new bin.")

    new_folder = pool.AddSubFolder(parent_folder, name)
    if not new_folder:
        return {"status": "failed", "name": name, "reason": "AddSubFolder returned nothing."}
    return {
        "status": "done",
        "name": serialize.safe(new_folder.GetName) or name,
        "parent": serialize.safe(parent_folder.GetName),
    }


def set_current_bin(name: str) -> dict:
    """Set the current media-pool bin by name (searched from the root).

    Subsequent imports and listings target this bin. A project must be open.
    Returns the name of the now-current folder.
    """
    pool = get_media_pool()
    folder = _find_subfolder(name)
    if folder is None:
        raise ResolveError(f"No media-pool bin named '{name}' was found.")
    ok = pool.SetCurrentFolder(folder)
    if not ok:
        return {"status": "failed", "name": name, "reason": "SetCurrentFolder returned False."}
    current = serialize.safe(pool.GetCurrentFolder)
    return {
        "status": "done",
        "current_bin": serialize.safe(current.GetName) if current is not None else name,
    }


def get_clip_properties(clip_name: str) -> dict:
    """Read every property of a media-pool clip, found by name.

    Searches the current bin then the root folder for a clip whose name matches.
    Returns the full serialized clip (including the entire clip-property map). A
    project must be open.
    """
    mpi = _find_clip(clip_name)
    if mpi is None:
        raise ResolveError(f"No clip named '{clip_name}' was found in the current bin or root.")
    return serialize.clip_to_dict(mpi, full=True)


def set_clip_property(clip_name: str, key: str, value: str) -> dict:
    """Set a single clip property on a media-pool clip, found by name. Additive.

    Resolves the clip in the current bin then the root, sets ``key`` to ``value``,
    and reads the value back. A project must be open. Some keys are read-only or
    enumerated (e.g. 'Super Scale'); a failed write is reported as status failed.
    """
    mpi = _find_clip(clip_name)
    if mpi is None:
        raise ResolveError(f"No clip named '{clip_name}' was found in the current bin or root.")
    ok = mpi.SetClipProperty(key, value)
    read_back = serialize.safe(mpi.GetClipProperty, key)
    return {
        "status": "done" if ok else "failed",
        "name": clip_name,
        "key": key,
        "value": read_back,
    }


def set_clip_mark_in_out(
    clip_name: str, mark_in: int, mark_out: int, mark_type: str = "all"
) -> dict:
    """Set the in/out marks on a media-pool clip, found by name. Additive.

    ``mark_type`` is one of "video", "audio" or "all" (default). Resolves the
    clip in the current bin then the root. A project must be open. Returns the
    in/out marks read back from the clip.
    """
    if mark_type not in ("video", "audio", "all"):
        raise ResolveError("mark_type must be one of 'video', 'audio' or 'all'.")
    mpi = _find_clip(clip_name)
    if mpi is None:
        raise ResolveError(f"No clip named '{clip_name}' was found in the current bin or root.")
    ok = mpi.SetMarkInOut(mark_in, mark_out, mark_type)
    marks = serialize.safe(mpi.GetMarkInOut, default={}) or {}
    return {
        "status": "done" if ok else "failed",
        "name": clip_name,
        "mark_type": mark_type,
        "marks": marks,
    }


def delete_media_clips(clip_names: list[str], confirm: bool = False) -> dict:
    """Delete clips from the media pool by name. GATED: irreversible.

    Resolves each name in the current bin then the root, previews what would be
    removed, and only deletes when confirm=True. Removing a clip from the media
    pool also removes it from any timeline that uses it. A project must be open.
    """
    if not clip_names:
        raise ResolveError("Provide at least one clip name to delete.")

    found = []
    missing = []
    for name in clip_names:
        mpi = _find_clip(name)
        if mpi is None:
            missing.append(name)
        else:
            found.append((name, mpi))

    if not found:
        raise ResolveError(
            f"None of the named clips were found: {', '.join(clip_names)}."
        )

    found_names = [n for n, _ in found]
    if not confirm:
        detail = f"removes {len(found_names)} clip(s) from the media pool and any timeline using them"
        if missing:
            detail += f"; not found and will be skipped: {', '.join(missing)}"
        return confirm_required(
            f"delete media clips: {', '.join(found_names)}",
            detail,
            targets=found_names,
            missing=missing,
        )

    pool = get_media_pool()
    ok = pool.DeleteClips([mpi for _, mpi in found])
    return {
        "status": "done" if ok else "failed",
        "deleted": found_names if ok else [],
        "missing": missing,
    }


def register(mcp) -> None:
    for fn in (
        browse_storage,
        import_media,
        list_media_pool,
        create_bin,
        set_current_bin,
        get_clip_properties,
        set_clip_property,
        set_clip_mark_in_out,
        delete_media_clips,
    ):
        mcp.tool()(fn)
