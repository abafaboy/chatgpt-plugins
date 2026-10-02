import json

import httpx
import pytest
from mcp import Client

import tg_shop.server as srv
from pathlib import Path

pytestmark = pytest.mark.anyio

# Copy of https://github.com/abafaboy/tg-storefront examples/demo-shop/site/products.json (fictional sample shop).
DEMO = json.loads((Path(__file__).parent / "fixtures" / "tg_shop" / "products.json").read_text(encoding="utf-8"))
BASE = "https://abafaboy.github.io/tg-storefront/"


@pytest.fixture
def fetches(monkeypatch):
    calls = []

    def fake(base_url):
        calls.append(base_url)
        return DEMO

    srv._cache.clear()
    monkeypatch.setattr(srv, "fetch_catalogue", fake)
    yield calls
    srv._cache.clear()


@pytest.fixture
async def client(fetches):
    async with Client(srv.mcp, mode="legacy") as c:
        yield c


async def search(client, **args):
    r = await client.call_tool("search_products", args)
    assert not r.is_error, r.content[0].text
    return r


def ids(r):
    return [p["id"] for p in r.structured_content["products"]]


async def test_tools_are_read_only_open_and_bound_to_widget(client):
    tools = (await client.list_tools()).tools
    assert {t.name for t in tools} == {"list_shops", "search_products", "get_product"}
    for t in tools:
        a = t.annotations
        assert a.read_only_hint is True and a.destructive_hint is False and a.open_world_hint is True
        assert t.meta["ui"]["resourceUri"] == srv.WIDGET
        assert t.output_schema is not None, t.name
        assert t.title


def test_registered_shops():
    assert [s["slug"] for s in srv.SHOPS] == ["demo-shop"]
    s = srv.SHOPS[0]
    assert s["base_url"] == BASE and s["demo"] is True and s["name"] == "Demo Shop (sample data)"
    assert srv.SHOP_ORIGINS == ["https://abafaboy.github.io"]


async def test_list_shops_counts(client):
    r = await client.call_tool("list_shops", {})
    shop = r.structured_content["shops"][0]
    assert shop["product_count"] == 12 and shop["available_count"] == 11 and shop["error"] is None
    assert "12 products" in r.content[0].text


async def test_search_latin_word(client):
    r = await search(client, query="choynak")
    assert ids(r) == [8]
    assert "Chinni choynak toʻplami «Lola» — 350\u00a0000\u00a0soʻm — " + BASE + "p/8.html" in r.content[0].text


async def test_cyrillic_query_finds_latin_title(client):
    r = await search(client, query="гилам Бухоро")
    assert ids(r) == [5]
    r = await search(client, query="чарм ҳамён")
    assert ids(r) == [21]


async def test_title_hits_rank_above_description_hits(client):
    # "paxta" is in the title of 4 (towels) and only in the description of 8 (teapot set).
    r = await search(client, query="paxta")
    assert ids(r) == [4, 8]


async def test_category_filter(client):
    r = await search(client, category="idishlar")
    assert set(ids(r)) == {8, 3}
    r = await search(client, category="идишлар")
    assert set(ids(r)) == {8, 3}


async def test_max_price_excludes_unpriced_and_dearer(client):
    r = await search(client, max_price=100000, currency="UZS")
    assert set(ids(r)) == {16, 3}
    r = await search(client, max_price=100000)
    assert set(ids(r)) == {16, 3, 13}  # 45 USD compares on amount only
    assert 20 not in ids(r)  # no price listed


async def test_unpriced_items_rank_last_without_max_price(client):
    r = await search(client, category="uy")
    assert ids(r)[-1] == 20
    assert "Stol soati «Retro» — price not listed" in r.content[0].text


async def test_sold_excluded_then_included(client):
    r = await search(client, query="bolalar")
    assert ids(r) == []
    r = await search(client, query="bolalar", include_sold=True)
    assert ids(r) == [14]
    assert r.structured_content["products"][0]["sold"] is True
    assert "(sold)" in r.content[0].text


async def test_limit_and_total(client):
    r = await search(client, limit=3)
    assert len(ids(r)) == 3 and r.structured_content["total"] == 11
    assert ids(r) == [21, 18, 17]  # newest first when browsing
    r = await client.call_tool("search_products", {"limit": 31})
    assert r.is_error


async def test_unknown_shop_lists_valid_slugs(client):
    r = await client.call_tool("search_products", {"shop": "nope"})
    assert r.is_error and "demo-shop" in r.content[0].text
    r = await client.call_tool("get_product", {"shop": "nope", "product_id": 8})
    assert r.is_error and "demo-shop" in r.content[0].text


async def test_get_product_absolute_urls(client):
    r = await client.call_tool("get_product", {"shop": "demo-shop", "product_id": 8})
    p = r.structured_content["product"]
    assert p["images"] == [BASE + "img/8-1.jpg", BASE + "img/8-2.jpg", BASE + "img/8-3.jpg"]
    assert p["product_page"] == BASE + "p/8.html"
    assert p["telegram_post"] == "https://t.me/tgstorefront_demo/8"
    assert p["price"] == {"amount": 350000, "currency": "UZS", "display": "350\u00a0000\u00a0soʻm"}  # as the shop wrote it
    assert p["shop"] == "demo-shop" and p["shop_name"] == "Demo Shop (sample data)"


async def test_get_product_unknown_id(client):
    r = await client.call_tool("get_product", {"shop": "demo-shop", "product_id": 999})
    assert r.is_error and "999" in r.content[0].text


async def test_null_images_dropped_and_paths_cannot_leave_the_site(client, monkeypatch):
    data = {"products": [{
        "id": 1, "title": "X", "images": [None, "img/1-1.jpg", "https://evil.example/a.jpg", "../x.jpg", "//evil.example/b.jpg"],
        "page": "https://evil.example/p.html", "description": "d" * 700, "price": None, "url": "javascript:alert(1)",
    }]}
    srv._cache.clear()
    monkeypatch.setattr(srv, "fetch_catalogue", lambda base: data)
    r = await client.call_tool("get_product", {"shop": "demo-shop", "product_id": 1})
    p = r.structured_content["product"]
    assert p["images"] == [BASE + "img/1-1.jpg"]
    assert p["product_page"] == BASE
    assert p["telegram_post"] is None
    assert len(p["description"]) == 600 and p["description"].endswith("…")


async def test_order_url_never_exposed(client):
    assert all("order_url" in p for p in DEMO["products"])  # the source has it
    results = [
        await client.call_tool("list_shops", {}),
        await client.call_tool("search_products", {"include_sold": True, "limit": 30}),
        await client.call_tool("get_product", {"shop": "demo-shop", "product_id": 8}),
    ]
    order_urls = [p["order_url"] for p in DEMO["products"]]
    for r in results:
        blob = json.dumps(r.structured_content, ensure_ascii=False) + r.content[0].text
        assert "order_url" not in blob
        assert "?text=" not in blob
        assert not any(u in blob for u in order_urls)


async def test_catalogue_cached(client, fetches):
    await client.call_tool("list_shops", {})
    await client.call_tool("search_products", {"query": "termos"})
    await client.call_tool("get_product", {"shop": "demo-shop", "product_id": 17})
    assert fetches == [BASE]


async def test_catalogue_failure_handled(client, monkeypatch):
    def boom(base):
        raise httpx.ConnectError("down")
    srv._cache.clear()
    monkeypatch.setattr(srv, "fetch_catalogue", boom)
    r = await client.call_tool("list_shops", {})
    assert not r.is_error
    shop = r.structured_content["shops"][0]
    assert shop["product_count"] is None and "could not be read" in shop["error"]
    r = await client.call_tool("search_products", {"query": "termos"})
    assert r.is_error
    r = await client.call_tool("get_product", {"shop": "demo-shop", "product_id": 17})
    assert r.is_error


async def test_malformed_catalogue_handled(client, monkeypatch):
    srv._cache.clear()
    monkeypatch.setattr(srv, "fetch_catalogue", lambda base: {"products": "nope"})
    r = await client.call_tool("search_products", {})
    assert r.is_error


def test_real_fetch_refuses_oversized_and_wrong_shape(monkeypatch):
    real = httpx.Client

    def serve(body: bytes):
        transport = httpx.MockTransport(lambda req: httpx.Response(200, content=body))
        monkeypatch.setattr(srv.httpx, "Client", lambda **kw: real(transport=transport, **kw))

    serve(json.dumps(DEMO).encode())
    assert len(srv._fetch_catalogue(BASE)["products"]) == 12
    serve(b"[1, 2]")
    with pytest.raises(ValueError):
        srv._fetch_catalogue(BASE)
    serve(b" " * (srv.MAX_BYTES + 1))
    with pytest.raises(ValueError, match="5 MB"):
        srv._fetch_catalogue(BASE)


async def test_widget_resource(client):
    rr = await client.read_resource(srv.WIDGET)
    content = rr.contents[0]
    assert content.mime_type == "text/html;profile=mcp-app"
    assert "plugkit" in content.text and "ui/notifications/tool-result" in content.text
    assert "innerHTML" not in content.text.split("<script>", 2)[2]
    assert "https://abafaboy.github.io" in content.meta["ui"]["csp"]["resourceDomains"]
    assert content.meta["ui"]["csp"]["connectDomains"] == []


async def test_usage_is_logged_without_query(client, usage_log):
    await client.call_tool("search_products", {"query": "secretword gilam"})
    ev = json.loads(usage_log.read_text().splitlines()[-1])
    assert ev["plugin"] == "tg-shop" and ev["tool"] == "search_products" and ev["ok"] is True
    assert "secretword" not in usage_log.read_text()
