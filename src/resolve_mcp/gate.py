"""Confirm gate for destructive or expensive actions.

Resolve MCP's edit surface can delete media, drop timelines and start renders.
Every such tool takes ``confirm: bool = False``. With ``confirm`` False the tool
changes nothing and returns a preview describing exactly what it would do; the
caller must call again with ``confirm=True`` to actually apply it. This keeps a
single round-trip between "tell me what this will do" and "do it", so the agent
never destroys work on a first, exploratory call.
"""
from __future__ import annotations


def confirm_required(action: str, detail: str = "", **extra) -> dict:
    """Return the standard preview payload for a gated action.

    ``action`` is a short imperative ("delete timeline 'Reel v2'"), ``detail``
    is any extra context worth showing before the caller commits. Any keyword
    extras (counts, names, targets) are merged into the payload so the preview
    is specific.
    """
    out: dict = {
        "status": "confirm_required",
        "action": action,
        "hint": "Nothing was changed. Call this tool again with confirm=true to apply it.",
    }
    if detail:
        out["detail"] = detail
    out.update(extra)
    return out
