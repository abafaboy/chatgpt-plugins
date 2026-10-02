"""Usage counting for picking the plugin that works best.

Every tool call is recorded as one line of JSON: when, which plugin, which tool,
whether it succeeded and how long it took. Nothing the user typed, uploaded or
received is recorded, so the log can be shown in a privacy policy as it is.

The log answers the one question the experiment needs: which plugin do people
actually use, and do they come back.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json
import os
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

_lock = threading.Lock()


def _log_path() -> Path:
    return Path(os.environ.get("USAGE_LOG", "usage.jsonl"))


def record(plugin: str, tool: str, ok: bool, ms: int) -> None:
    """Append one usage event. Never raises: a full disk must not break a tool call."""
    event = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "plugin": plugin,
        "tool": tool,
        "ok": ok,
        "ms": ms,
    }
    line = json.dumps(event, separators=(",", ":")) + "\n"
    if os.environ.get("USAGE_STDOUT") == "1":
        # A second copy in the platform's log stream, in case the disk is lost.
        print("usage " + line, end="", flush=True)
    try:
        with _lock, _log_path().open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        pass


def tracked(plugin: str) -> Callable[[F], F]:
    """Decorator: count every call of a tool function, sync or async.

    `functools.wraps` keeps `__wrapped__`, so the MCP SDK still reads the original
    signature and builds the same input schema.
    """

    def decorator(fn: F) -> F:
        name = fn.__name__
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                start = time.perf_counter()
                ok = False
                try:
                    result = await fn(*args, **kwargs)
                    ok = not getattr(result, "is_error", False)
                    return result
                finally:
                    record(plugin, name, ok, int((time.perf_counter() - start) * 1000))

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            ok = False
            try:
                result = fn(*args, **kwargs)
                ok = not getattr(result, "is_error", False)
                return result
            finally:
                record(plugin, name, ok, int((time.perf_counter() - start) * 1000))

        return wrapper  # type: ignore[return-value]

    return decorator


def summary(path: Path | None = None) -> dict[str, Any]:
    """Counts per plugin, per tool and per day, for the /stats page."""
    path = path or _log_path()
    by_plugin: Counter[str] = Counter()
    by_tool: Counter[str] = Counter()
    by_day: dict[str, Counter[str]] = {}
    errors: Counter[str] = Counter()
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            for raw in fh:
                try:
                    ev = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                plugin = ev.get("plugin", "?")
                by_plugin[plugin] += 1
                by_tool[f"{plugin}/{ev.get('tool', '?')}"] += 1
                by_day.setdefault(str(ev.get("ts", ""))[:10], Counter())[plugin] += 1
                if not ev.get("ok", False):
                    errors[plugin] += 1
    return {
        "calls_by_plugin": dict(by_plugin.most_common()),
        "errors_by_plugin": dict(errors),
        "calls_by_tool": dict(by_tool.most_common()),
        "calls_by_day": {day: dict(c) for day, c in sorted(by_day.items())},
    }


async def to_thread(fn: Callable[..., Any], *args: Any) -> Any:
    """Run blocking work (file parsing) off the event loop."""
    return await asyncio.to_thread(fn, *args)
