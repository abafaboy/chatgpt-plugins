"""Render every widget view in headless Chromium and save screenshots to docs/widgets/.

Each widget is loaded in an iframe inside a small host page that speaks the MCP
Apps protocol: it answers `ui/initialize`, waits for `ui/notifications/initialized`,
then sends `ui/notifications/tool-result` with a REAL tool result produced by
calling the server in-process (network-dependent tools use the test fixtures).

Run: python scripts/render_widgets.py   (needs `pip install playwright`; Chromium
is found via PLAYWRIGHT_BROWSERS_PATH or /opt/pw-browsers/chromium).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import Client

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
OUT = ROOT / "docs" / "widgets"
DEMO_IMG = Path(os.environ.get("TG_DEMO_SITE", "/home/claude/gh/tg-storefront/examples/demo-shop/site"))

HOST_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;background:%(bg)s;font-family:system-ui;padding:16px}
iframe{width:%(w)spx;border:1px solid #ccc;border-radius:12px;background:transparent;display:block}
</style></head><body><iframe id="f" sandbox="allow-scripts"></iframe><script>
const result = %(result)s;
const f = document.getElementById('f');
window.addEventListener('message', (e) => {
  const m = e.data || {};
  if (m.method === 'ui/initialize') {
    f.contentWindow.postMessage({jsonrpc:'2.0', id:m.id, result:{protocolVersion:'2026-01-26', hostCapabilities:{}, hostInfo:{name:'render-test',version:'1'}, hostContext:{theme:'%(theme)s', displayMode:'inline'}}}, '*');
  } else if (m.method === 'ui/notifications/initialized') {
    f.contentWindow.postMessage({jsonrpc:'2.0', method:'ui/notifications/tool-result', params: result}, '*');
  } else if (m.method === 'ui/notifications/size-changed') {
    f.style.height = (m.params.height + 2) + 'px';
    document.title = 'sized';
  }
});
f.srcdoc = %(html)s;
</script></body></html>"""


def js(value: object) -> str:
    """JSON for embedding inside a <script> block ("</script>" in data must not close it)."""
    return json.dumps(value).replace("</", "<\\/")


def b64file(name: str) -> dict:
    return {"download_url": f"https://files.example/{name}", "file_id": "file_" + name, "file_name": name}


async def tool_results() -> list[tuple[str, str, str, dict]]:
    """(slug, view name, widget uri, CallToolResult as dict) for every view."""
    import invoice_check.server as inv
    import speaking_coach.server as sc
    import tg_shop.server as shop
    import uz_text.server as uz
    import gpt_to_plugin.server as g2p

    uz.fetch_rates = lambda: [
        {"Ccy": "USD", "CcyNm_EN": "US Dollar", "CcyNm_UZ": "AQSH dollari", "Nominal": "1", "Rate": "11808.76", "Diff": "-12.42", "Date": "01.10.2026"},
        {"Ccy": "EUR", "CcyNm_EN": "Euro", "CcyNm_UZ": "EVRO", "Nominal": "1", "Rate": "13404.12", "Diff": "-15.28", "Date": "01.10.2026"},
        {"Ccy": "RUB", "CcyNm_EN": "Russian Ruble", "CcyNm_UZ": "Rossiya rubli", "Nominal": "1", "Rate": "142.16", "Diff": "1.72", "Date": "01.10.2026"},
    ]
    catalogue = json.loads((FIX / "tg_shop" / "products.json").read_text(encoding="utf-8"))
    shop.fetch_catalogue = lambda base_url: catalogue
    inv.download_file = lambda url: (FIX / "invoice_check" / url.rsplit("/", 1)[1]).read_bytes()

    plan = [
        ("uz-text", "scripts", uz, "convert_uzbek_script", {"text": "Toshkent shahri, Oʻzbekiston Respublikasi", "target": "cyrillic"}),
        ("uz-text", "amount", uz, "write_amount_in_uzbek_words", {"amount": "1 250 000,50"}),
        ("uz-text", "rates", uz, "get_uzbek_exchange_rates", {}),
        ("uz-text", "normalized", uz, "normalize_uzbek_text", {"text": "O`zbekiston san'at g‘alaba"}),
        ("tg-shop", "shops", shop, "list_shops", {}),
        ("tg-shop", "search", shop, "search_products", {"limit": 6}),
        ("tg-shop", "product", shop, "get_product", {"shop": "demo-shop", "product_id": catalogue["products"][0]["id"]}),
        ("invoice-check", "check", inv, "check_invoice", {"file": b64file("01_proforma_en.pdf"), "as_of": "2026-09-25"}),
        ("invoice-check", "compare", inv, "compare_quotations", {"old_file": b64file("03_quotation_v1.xlsx"), "new_file": b64file("03_quotation_v2.xlsx")}),
        ("invoice-check", "rules", inv, "list_invoice_rules", {}),
        ("speaking-coach", "test", sc, "start_speaking_test", {"part": "full", "seed": 3}),
        ("speaking-coach", "analysis", sc, "analyse_speaking_transcript", {"part": "2", "duration_seconds": 95, "transcript": (
            "Well, I'd like to talk about a market near my house. Um, it's a big covered bazaar where my family buys "
            "vegetables every weekend. However, what I like most is the bread section, because the bakers work right "
            "in front of you. For example, last Saturday I watched them bake round flatbread in a clay oven. In addition, "
            "the sellers know my grandmother, so we often get a small discount. You know, it feels more like a community "
            "than a shop. As a result, I always look forward to going there.")}),
        ("speaking-coach", "score", sc, "record_speaking_scores", {
            "fluency_coherence": 7, "lexical_resource": 6, "grammatical_range_accuracy": 7, "pronunciation": None,
            "strengths": ["Clear structure with signposting (however, for example, as a result)", "Relevant personal detail"],
            "improvements": ["Use less common vocabulary for food and places", "Extend answers with a reason and a contrast"],
            "better_answer_example": "The bazaar is a sprawling covered market where the smell of freshly baked non hits you first…"}),
        ("gpt-to-plugin", "build", g2p, "build_plugin_from_gpt", {
            "display_name": "Sales Email Coach", "description": "Helps sales managers write short follow-up emails.",
            "instructions": "You help sales managers write follow-up emails. Keep them under 120 words.",
            "conversation_starters": ["Write a follow-up after a demo"], "knowledge_file_names": ["price-list.pdf"],
            "action_names": ["crm_lookup"]}),
        ("gpt-to-plugin", "validate", g2p, "validate_plugin_package", {"files": [
            {"path": "plugin.json", "content": '{"name": "My Plugin", "version": "1", "description": "Best price, free trial!"}'},
            {"path": "skills/helper/SKILL.md", "content": "No frontmatter here."}]}),
        ("gpt-to-plugin", "rules", g2p, "explain_plugin_rules", {}),
    ]
    out = []
    for slug, view, mod, tool, args in plan:
        async with Client(mod.mcp, mode="legacy") as c:
            r = await c.call_tool(tool, args)
            if r.is_error:
                raise SystemExit(f"{slug}/{tool} returned an error: {r.content[0].text}")
            uri = next(t.meta["ui"]["resourceUri"] for t in (await c.list_tools()).tools if t.name == tool)
            html = (await c.read_resource(uri)).contents[0].text
            out.append((slug, view, html, r.model_dump(by_alias=True, exclude_none=True, mode="json")))
    return out


async def main() -> int:
    from playwright.async_api import async_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    results = await tool_results()
    # Prefer an explicit binary: a pip-installed Playwright may expect a newer
    # browser build than the one already on the machine.
    exe = os.environ.get("CHROMIUM") or ("/opt/pw-browsers/chromium" if Path("/opt/pw-browsers/chromium").exists() else None)
    console_errors: list[str] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=exe)
        for theme in ("light", "dark"):
            ctx = await browser.new_context(color_scheme=theme, viewport={"width": 760, "height": 2000}, device_scale_factor=1)

            async def route(r):
                name = r.request.url.split("/img/")[-1]
                f = DEMO_IMG / "img" / name
                if f.exists():
                    await r.fulfill(path=str(f))
                else:
                    await r.fulfill(status=404)

            await ctx.route("https://abafaboy.github.io/**/img/**", route)
            for slug, view, html, res in results:
                page = await ctx.new_page()
                page.on("console", lambda m, s=slug, v=view: m.type == "error" and console_errors.append(f"{s}/{v}: {m.text}"))
                page.on("pageerror", lambda e, s=slug, v=view: console_errors.append(f"{s}/{v}: {e}"))
                await page.set_content(HOST_PAGE % {
                    "bg": "#ffffff" if theme == "light" else "#0f1012", "w": 720, "theme": theme,
                    "result": js(res), "html": js(html)})
                try:
                    await page.wait_for_function("document.title === 'sized'", timeout=8000)
                except Exception:
                    console_errors.append(f"{slug}/{view}: widget never reported its size (did it render?)")
                await page.wait_for_timeout(600)
                path = OUT / f"{slug}--{view}--{theme}.png"
                await page.locator("#f").screenshot(path=str(path))
                await page.close()
            await ctx.close()
        await browser.close()
    print("\n".join(sorted(str(x.relative_to(ROOT)) for x in OUT.glob("*.png"))))
    if console_errors:
        print("CONSOLE ERRORS:\n" + "\n".join(console_errors))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
