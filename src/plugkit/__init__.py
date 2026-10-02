"""Shared helpers for the plugins in this repository."""

from __future__ import annotations

import html as _html
from importlib import resources
from typing import Any

from mcp_types import CallToolResult, TextContent, ToolAnnotations

from .usage import record, summary, tracked

__all__ = ["READ_ONLY", "READ_ONLY_OPEN", "result", "error", "widget_html", "tracked", "record", "summary"]

# Every tool in this repo computes or reads; none writes, deletes or sends anything.
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False, idempotent_hint=True)
# Same, but reads from the public internet (a bank's rate feed, a shop's public catalogue).
READ_ONLY_OPEN = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True, idempotent_hint=True)


def result(text: str, data: dict[str, Any]) -> CallToolResult:
    """A tool result with a short text for the model and structured data for the widget."""
    return CallToolResult(content=[TextContent(type="text", text=text)], structured_content=data)


def error(text: str) -> CallToolResult:
    """A tool-level error the model can read and explain to the user."""
    return CallToolResult(content=[TextContent(type="text", text=text)], is_error=True)


def _static(name: str) -> str:
    return resources.files("plugkit").joinpath("static", name).read_text(encoding="utf-8")


def widget_html(title: str, body: str, script: str, extra_css: str = "") -> str:
    """One self-contained HTML document: base styles, the host bridge, then the widget code."""
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{_html.escape(title)}</title>"
        f"<style>{_static('base.css')}{extra_css}</style></head>"
        f"<body>{body}<script>{_static('bridge.js')}</script><script>{script}</script></body></html>"
    )

