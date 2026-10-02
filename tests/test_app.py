"""The combined web app: every plugin answers at its own path, pages and stats work."""

import json

import httpx
import pytest
from mcp import Client

from plugkit.app import PLUGINS, build_app
from plugkit.site import PLUGINS as PAGES

pytestmark = pytest.mark.anyio


def test_every_plugin_has_a_page_and_a_package():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    assert set(PAGES) == set(PLUGINS)
    for slug in PLUGINS:
        pkg = root / "plugins" / slug
        manifest = json.loads((pkg / "plugin.json").read_text())
        assert manifest["name"] == slug
        name = manifest["extensions"]["com.openai"]["interface"]["displayName"]
        assert name == PAGES[slug]["name"] and len(name) <= 30
        assert (pkg / "assets" / "icon.png").is_file()
        assert list((pkg / "skills").glob("*/SKILL.md"))
        url = json.loads((pkg / "mcp.json").read_text())["mcpServers"][slug]["url"]
        assert url.endswith(f"/{slug}/mcp")


async def test_pages_stats_and_health(monkeypatch, usage_log):
    monkeypatch.setenv("STATS_TOKEN", "secret-token")
    app = build_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            assert (await http.get("/healthz")).text == "ok"
            for path in ["/", "/privacy", "/terms", *[f"/site/{s}" for s in PLUGINS]]:
                r = await http.get(path)
                assert r.status_code == 200, path
            assert (await http.get("/site/nope")).status_code == 404
            assert (await http.get("/stats")).status_code == 403
            assert (await http.get("/stats", headers={"x-stats-token": "wrong"})).status_code == 403
            ok = await http.get("/stats", headers={"x-stats-token": "secret-token"})
            assert ok.status_code == 200 and "calls_by_plugin" in ok.json()


async def test_widget_template_meta_has_both_keys():
    from importlib import import_module

    from plugkit.app import add_legacy_template_meta

    for mod in PLUGINS.values():
        server = import_module(mod).mcp
        add_legacy_template_meta(server)
        async with Client(server, mode="legacy") as c:
            for tool in (await c.list_tools()).tools:
                assert tool.meta["openai/outputTemplate"] == tool.meta["ui"]["resourceUri"], tool.name


def test_set_host(tmp_path, monkeypatch):
    import importlib.util
    import shutil
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    for slug in PLUGINS:
        (tmp_path / "plugins" / slug).mkdir(parents=True)
        shutil.copy(root / "plugins" / slug / "mcp.json", tmp_path / "plugins" / slug / "mcp.json")
    spec = importlib.util.spec_from_file_location("set_host", root / "scripts" / "set_host.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    assert mod.main("https://plugins.example.com/") == 0
    data = json.loads((tmp_path / "plugins" / "tg-shop" / "mcp.json").read_text())
    assert data["mcpServers"]["tg-shop"]["url"] == "https://plugins.example.com/tg-shop/mcp"
    assert mod.main("bad host!") == 2
