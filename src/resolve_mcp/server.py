"""Resolve MCP MCP server: the entry point that registers the tool modules.

Each module under ``tools`` owns one DaVinci Resolve domain and exposes a
``register(mcp)`` function. They are registered in a deliberate order: orient and
see first, then project and media, then timeline assembly, then the finishing
surfaces (clip transforms, markers, colour, audio) and finally delivery.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .tools import (
    audio,
    clip,
    color,
    edit,
    markers,
    media,
    navigate,
    perception,
    project,
    render,
    state,
    timeline,
)

mcp = FastMCP("resolve")

# Orient and see.
state.register(mcp)
perception.register(mcp)
navigate.register(mcp)

# Project and media.
project.register(mcp)
media.register(mcp)

# Build the edit.
timeline.register(mcp)
edit.register(mcp)
clip.register(mcp)
markers.register(mcp)

# Finish and deliver.
color.register(mcp)
audio.register(mcp)
render.register(mcp)


def main() -> None:
    """Run the server over stdio (the default MCP transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
