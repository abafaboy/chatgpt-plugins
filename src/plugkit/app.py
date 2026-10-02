"""One web process that serves every plugin at its own path.

    /uz-text/mcp          UzText
    /tg-shop/mcp          Telegram shop catalogue
    /invoice-check/mcp    Proforma & invoice checker
    /speaking-coach/mcp   Speaking practice
    /gpt-to-plugin/mcp    GPT to plugin packager
    /, /site/<slug>, /privacy, /terms   public pages for the submission form
    /healthz              liveness check
    /stats                usage counts (needs the STATS_TOKEN header)

Each plugin is still a separate MCP server with its own URL, so each is
submitted, listed and measured on its own. Running them in one process only
saves hosting cost.
"""

from __future__ import annotations

import contextlib
import hmac
import os
from collections.abc import AsyncIterator
from importlib import import_module

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route

from mcp.server.transport_security import TransportSecuritySettings

from .site import routes as site_routes
from .usage import summary

PLUGINS = {
    "uz-text": "uz_text.server",
    "tg-shop": "tg_shop.server",
    "invoice-check": "invoice_check.server",
    "speaking-coach": "speaking_coach.server",
    "gpt-to-plugin": "gpt_to_plugin.server",
}


def _security() -> TransportSecuritySettings:
    """DNS-rebinding protection: only accept requests addressed to our own host.

    PUBLIC_HOST is the deployed hostname, e.g. plugins.example.com. Locally the
    check is off so tests and the MCP Inspector work on localhost.
    """
    host = os.environ.get("PUBLIC_HOST", "").strip()
    if not host:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[host, f"{host}:*"],
        allowed_origins=[f"https://{host}", "https://chatgpt.com", "https://chat.openai.com"],
    )


def add_legacy_template_meta(server) -> None:
    """Also publish the widget under ChatGPT's older `openai/outputTemplate` key.

    OpenAI's reference says `_meta.ui.resourceUri` replaces `openai/outputTemplate`;
    sending both costs nothing and keeps the widget working in clients that still
    read the old key.
    """
    for tool in server._tool_manager.list_tools():
        uri = (tool.meta or {}).get("ui", {}).get("resourceUri")
        if uri and "openai/outputTemplate" not in tool.meta:
            tool.meta["openai/outputTemplate"] = uri


def build_app(only: list[str] | None = None) -> Starlette:
    servers = {slug: import_module(mod).mcp for slug, mod in PLUGINS.items() if not only or slug in only}
    for server in servers.values():
        add_legacy_template_meta(server)
    security = _security()
    subapps = {
        slug: server.streamable_http_app(
            streamable_http_path="/mcp",
            stateless_http=True,
            json_response=True,
            transport_security=security,
        )
        for slug, server in servers.items()
    }

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with contextlib.AsyncExitStack() as stack:
            for sub in subapps.values():
                await stack.enter_async_context(sub.router.lifespan_context(sub))
            yield

    async def healthz(_: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    async def stats(request: Request) -> JSONResponse:
        token = os.environ.get("STATS_TOKEN", "")
        given = request.headers.get("x-stats-token", "")
        if not token or not hmac.compare_digest(token, given):
            return JSONResponse({"error": "forbidden"}, status_code=403)
        return JSONResponse(summary())

    routes = [Route("/healthz", healthz), Route("/stats", stats), *site_routes]
    routes += [Mount(f"/{slug}", app=sub) for slug, sub in subapps.items()]
    return Starlette(routes=routes, lifespan=lifespan)


def main() -> None:
    import uvicorn

    uvicorn.run(build_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), proxy_headers=True)


if __name__ == "__main__":
    main()
