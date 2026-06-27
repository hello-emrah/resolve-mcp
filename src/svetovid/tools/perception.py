"""Perception: let the agent see the actual frame on the timeline.

This is the heart of Svetovid. Rather than edit blind against metadata, the
agent exports the real frame at the playhead and looks at it.
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

from mcp.server.fastmcp import Image

from ..connection import ResolveError, get_project, get_timeline

_SCRATCH = Path(tempfile.gettempdir()) / "svetovid"


def render_current_frame() -> Image:
    """See the edit. Export the frame at the playhead and return it as an image.

    Use this to look at what the timeline actually shows before and after an
    edit, rather than reasoning from metadata alone. The current timeline
    must be open and a frame visible at the playhead.
    """
    project = get_project()
    get_timeline()

    _SCRATCH.mkdir(parents=True, exist_ok=True)
    target = _SCRATCH / f"frame_{int(time.time() * 1000)}.png"

    ok = project.ExportCurrentFrameAsStill(str(target))

    path = target
    if not path.exists():
        stills = sorted(_SCRATCH.glob("frame_*.*"), key=lambda p: p.stat().st_mtime)
        path = stills[-1] if stills else target

    if not ok or not path.exists():
        raise ResolveError(
            "Could not export the current frame. Open a timeline and make "
            "sure a frame is visible at the playhead (the Color or Edit page)."
        )

    return Image(data=path.read_bytes(), format=path.suffix.lstrip(".") or "png")


def register(mcp) -> None:
    mcp.tool()(render_current_frame)
