"""Shops from Telegram Channels: search tg-storefront catalogues and open products on the shop's site.

Each registered shop publishes `products.json` (the tg-storefront output format) at
its base URL. The plugin reads it, searches it script-insensitively (an Uzbek query
in Cyrillic finds a Latin title and the other way round, via uztext.search_key) and
links only to the product's informational page on the shop's own site. The shop's
prefilled Telegram order link (`order_url`) is deliberately never passed on.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from importlib import resources
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, Field

from mcp.server.apps import Apps, ResourceCsp
from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult

import uztext
from plugkit import READ_ONLY_OPEN, error, result, tracked, widget_html

from .widget import BODY, CSS, SCRIPT

PLUGIN = "tg-shop"
WIDGET = "ui://tg-shop/catalogue.html"
MAX_BYTES = 5 * 1024 * 1024
CACHE_SECONDS = 600
DESCRIPTION_CHARS = 600


# --- registered shops -------------------------------------------------------------


def _load_shops() -> list[dict[str, Any]]:
    raw = resources.files("tg_shop").joinpath("data", "shops.json").read_text(encoding="utf-8")
    shops = json.loads(raw)
    seen: set[str] = set()
    for s in shops:
        base = s["base_url"]
        if not (base.startswith("https://") and base.endswith("/")):
            raise ValueError(f"shop {s['slug']!r}: base_url must be https and end with '/'")
        if s["slug"] in seen:
            raise ValueError(f"duplicate shop slug {s['slug']!r}")
        seen.add(s["slug"])
    return shops


SHOPS: list[dict[str, Any]] = _load_shops()
SHOPS_BY_SLUG = {s["slug"]: s for s in SHOPS}


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


SHOP_ORIGINS = sorted({_origin(s["base_url"]) for s in SHOPS})


# --- output models ------------------------------------------------------------------


class Price(BaseModel):
    amount: int | float | None
    currency: str | None
    display: str | None


class Product(BaseModel):
    shop: str
    shop_name: str
    demo: bool
    id: int
    title: str
    description: str
    price: Price | None
    categories: list[str]
    images: list[str]
    product_page: str
    telegram_post: str | None
    sold: bool
    date: str | None


class ShopInfo(BaseModel):
    slug: str
    name: str
    base_url: str
    city: str
    language: str
    demo: bool
    product_count: int | None
    available_count: int | None
    error: str | None


class ShopsOut(BaseModel):
    kind: Literal["shops"]
    shops: list[ShopInfo]


class SearchOut(BaseModel):
    kind: Literal["search"]
    query: str | None
    total: int
    products: list[Product]
    unavailable_shops: list[str]


class ProductOut(BaseModel):
    kind: Literal["product"]
    product: Product


# Tools and the widget are registered on `apps` first; the server is built at the
# bottom of this file because MCPServer reads an extension's tools when constructed.
apps = Apps()


# --- catalogue fetching -------------------------------------------------------------


def _fetch_catalogue(base_url: str) -> dict:
    """GET <base_url>products.json, refusing bodies over 5 MB and non-catalogue JSON."""
    url = base_url + "products.json"
    with httpx.Client(timeout=10.0, headers={"User-Agent": "tg-shop-plugin/0.1"}) as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            declared = resp.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > MAX_BYTES:
                raise ValueError("catalogue larger than 5 MB")
            body = bytearray()
            for chunk in resp.iter_bytes():
                body.extend(chunk)
                if len(body) > MAX_BYTES:
                    raise ValueError("catalogue larger than 5 MB")
    data = json.loads(bytes(body))
    if not isinstance(data, dict) or not isinstance(data.get("products"), list):
        raise ValueError("not a tg-storefront products.json")
    return data


# Replaced in tests; the shops' sites are not reachable from the build sandbox.
fetch_catalogue = _fetch_catalogue

_cache: dict[str, tuple[float, list[dict]]] = {}


class CatalogueError(Exception):
    pass


def _catalogue(shop: dict[str, Any]) -> list[dict]:
    """The shop's products, cached for 10 minutes. Failures are not cached."""
    slug = shop["slug"]
    hit = _cache.get(slug)
    now = time.monotonic()
    if hit and now - hit[0] < CACHE_SECONDS:
        return hit[1]
    try:
        data = fetch_catalogue(shop["base_url"])
    except (httpx.HTTPError, ValueError, OSError) as exc:
        raise CatalogueError(f"{shop['name']}'s catalogue could not be read ({exc.__class__.__name__})") from exc
    if not isinstance(data, dict) or not isinstance(data.get("products"), list):
        raise CatalogueError(f"{shop['name']}'s catalogue is not in the expected format")
    products = [p for p in data["products"] if isinstance(p, dict) and isinstance(p.get("id"), int)]
    _cache[slug] = (now, products)
    return products


# --- shaping products ---------------------------------------------------------------


def _relative_url(base_url: str, rel: Any) -> str | None:
    """base_url + a relative path from products.json; anything that could leave the shop's site is dropped."""
    if not isinstance(rel, str) or not rel or len(rel) > 500:
        return None
    if rel.startswith(("/", "\\")) or "://" in rel or ":" in rel.split("/", 1)[0]:
        return None
    if any(part == ".." for part in rel.replace("\\", "/").split("/")):
        return None
    return base_url + rel


def _price(p: dict) -> dict | None:
    pr = p.get("price")
    if not isinstance(pr, dict):
        return None
    amount = pr.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        amount = None
    currency = pr.get("currency") if isinstance(pr.get("currency"), str) else None
    display = pr.get("display") if isinstance(pr.get("display"), str) else None
    if amount is None and display is None:
        return None
    return {"amount": amount, "currency": currency, "display": display}


def _truncate(text: str, limit: int = DESCRIPTION_CHARS) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _shape(shop: dict[str, Any], p: dict) -> dict[str, Any]:
    """Only the informational fields; `order_url` is never copied."""
    base = shop["base_url"]
    post = p.get("url")
    return {
        "shop": shop["slug"],
        "shop_name": shop["name"],
        "demo": bool(shop.get("demo")),
        "id": p["id"],
        "title": str(p.get("title") or "Untitled"),
        "description": _truncate(str(p.get("description") or "")),
        "price": _price(p),
        "categories": [str(c) for c in (p.get("categories") or []) if isinstance(c, str)][:20],
        "images": [u for u in (_relative_url(base, i) for i in (p.get("images") or [])) if u][:20],
        "product_page": _relative_url(base, p.get("page")) or base,
        "telegram_post": post if isinstance(post, str) and post.startswith("https://t.me/") else None,
        "sold": bool(p.get("sold")),
        "date": p.get("date") if isinstance(p.get("date"), str) else None,
    }


def _price_text(prod: dict[str, Any]) -> str:
    pr = prod["price"]
    if pr and pr["display"]:
        return pr["display"]
    if pr and pr["amount"] is not None:
        return f"{pr['amount']:g} {pr['currency'] or ''}".strip()
    return "price not listed"


def _line(prod: dict[str, Any]) -> str:
    sold = " (sold)" if prod["sold"] else ""
    return f"{prod['title']}{sold} — {_price_text(prod)} — {prod['product_page']}"


def _unknown_shop(slug: str) -> CallToolResult:
    return error(f"Unknown shop {slug!r}. Registered shops: {', '.join(SHOPS_BY_SLUG)}.")


# --- searching ------------------------------------------------------------------------


def _tokens(text: str) -> list[str]:
    words = re.findall(r"\w+", uztext.search_key(text))
    longer = [w for w in words if len(w) > 1]
    return longer or words


def _score(p: dict, tokens: list[str]) -> int:
    """0 means no match. Every word must appear; title hits outrank category and description hits."""
    title = uztext.search_key(str(p.get("title") or ""))
    cats = uztext.search_key(" ".join(c for c in (p.get("categories") or []) if isinstance(c, str)))
    desc = uztext.search_key(str(p.get("description") or ""))
    score = 0
    for t in tokens:
        if t in title:
            score += 100
        elif t in cats:
            score += 10
        elif t in desc:
            score += 1
        else:
            return 0
    return score


# --- tools ------------------------------------------------------------------------------


@apps.tool(
    resource_uri=WIDGET,
    name="list_shops",
    title="List shops",
    description=(
        "List the small shops that sell through Telegram channels and are registered with this plugin: "
        "name, city, catalogue language and how many products each currently lists. Use when the user "
        "asks which shops are available or before searching a particular shop."
    ),
    annotations=READ_ONLY_OPEN,
    meta={"openai/toolInvocation/invoking": "Loading shops…", "openai/toolInvocation/invoked": "Shops loaded"},
)
@tracked(PLUGIN)
def list_shops() -> Annotated[CallToolResult, ShopsOut]:
    out, lines = [], []
    for s in SHOPS:
        info = {k: s[k] for k in ("slug", "name", "base_url", "city", "language")}
        info["demo"] = bool(s.get("demo"))
        try:
            products = _catalogue(s)
            info.update(product_count=len(products), available_count=sum(1 for p in products if not p.get("sold")),
                        error=None)
            lines.append(f"{s['name']} [{s['slug']}] — {s['city']} — {len(products)} products — {s['base_url']}")
        except CatalogueError as exc:
            info.update(product_count=None, available_count=None, error=str(exc))
            lines.append(f"{s['name']} [{s['slug']}] — {s['city']} — catalogue unavailable right now")
        out.append(info)
    return result("\n".join(lines), {"kind": "shops", "shops": out})


@apps.tool(
    resource_uri=WIDGET,
    name="search_products",
    title="Search products",
    description=(
        "Search products across shops that sell through Telegram channels. Matches the title, categories and "
        "description; Uzbek queries work in Cyrillic or Latin (a Cyrillic query finds a Latin title). Omit "
        "query to browse the newest products. Sold items are hidden unless include_sold is true. Returns each "
        "product's price exactly as the shop wrote it and a link to the product page on the shop's site."
    ),
    annotations=READ_ONLY_OPEN,
    meta={"openai/toolInvocation/invoking": "Searching shops…", "openai/toolInvocation/invoked": "Search done"},
)
@tracked(PLUGIN)
def search_products(
    query: Annotated[str | None, Field(description="Words to look for, in any language or script.", max_length=200)] = None,
    shop: Annotated[str | None, Field(description="Shop slug from list_shops, to search one shop only.", max_length=64)] = None,
    category: Annotated[str | None, Field(description="Category as the shop names it, e.g. 'uy', 'kiyim'.", max_length=64)] = None,
    max_price: Annotated[
        float | None,
        Field(description="Highest price, in the product's own currency. Products without a listed price are excluded.", ge=0),
    ] = None,
    currency: Annotated[
        str | None,
        Field(description="Only products priced in this ISO currency, e.g. UZS or USD. Use with max_price.", max_length=8),
    ] = None,
    include_sold: Annotated[bool, Field(description="Include items the shop marked as sold.")] = False,
    limit: Annotated[int, Field(description="How many products to return.", ge=1, le=30)] = 12,
) -> Annotated[CallToolResult, SearchOut]:
    if shop is not None and shop not in SHOPS_BY_SLUG:
        return _unknown_shop(shop)
    targets = [SHOPS_BY_SLUG[shop]] if shop else SHOPS
    tokens = _tokens(query) if query and query.strip() else []
    cat_key = uztext.search_key(category).strip() if category and category.strip() else ""
    cur = currency.strip().upper() if currency and currency.strip() else ""

    hits: list[tuple[tuple, dict[str, Any]]] = []
    unavailable: list[str] = []
    for s in targets:
        try:
            products = _catalogue(s)
        except CatalogueError:
            unavailable.append(s["slug"])
            continue
        for p in products:
            if p.get("sold") and not include_sold:
                continue
            if cat_key and not any(
                isinstance(c, str) and cat_key in uztext.search_key(c) for c in (p.get("categories") or [])
            ):
                continue
            prod = _shape(s, p)
            amount = prod["price"]["amount"] if prod["price"] else None
            if cur and (not prod["price"] or (prod["price"]["currency"] or "").upper() != cur):
                continue
            if max_price is not None and (amount is None or amount > max_price):
                continue
            score = _score(p, tokens) if tokens else 1
            if not score:
                continue
            # Priced before unpriced, then relevance, then newest first.
            hits.append(((amount is None, -score, _neg_date(prod["date"])), prod))

    if unavailable and len(unavailable) == len(targets):
        names = ", ".join(SHOPS_BY_SLUG[u]["name"] for u in unavailable)
        return error(f"The catalogue of {names} could not be read right now. Try again later.")

    hits.sort(key=lambda h: h[0])
    products_out = [h[1] for h in hits[:limit]]
    if products_out:
        head = f"{len(hits)} matching product{'s' if len(hits) != 1 else ''}" + (f", showing {len(products_out)}" if len(hits) > len(products_out) else "")
        text = head + ":\n" + "\n".join(_line(p) for p in products_out)
    else:
        text = "No matching products."
    if any(p["demo"] for p in products_out):
        text += "\nDemo Shop is sample data, not a real shop."
    if unavailable:
        text += f"\nNot searched (catalogue unavailable): {', '.join(unavailable)}."
    return result(text, {
        "kind": "search", "query": query, "total": len(hits), "products": products_out,
        "unavailable_shops": unavailable,
    })


def _neg_date(date: str | None) -> float:
    """Sort key that puts newer dates first when sorted ascending; undated items last."""
    try:
        return -datetime.fromisoformat(date).timestamp() if date else float("inf")
    except ValueError:
        return float("inf")


@apps.tool(
    resource_uri=WIDGET,
    name="get_product",
    title="Show a product",
    description=(
        "Show one product from a shop with all its photos, full description (up to 600 characters), price as "
        "the shop wrote it, and the link to its page on the shop's site, where the shop's own order button is."
    ),
    annotations=READ_ONLY_OPEN,
    meta={"openai/toolInvocation/invoking": "Opening product…", "openai/toolInvocation/invoked": "Product shown"},
)
@tracked(PLUGIN)
def get_product(
    shop: Annotated[str, Field(description="Shop slug, as returned by search_products or list_shops.", max_length=64)],
    product_id: Annotated[int, Field(description="Product id from search_products.", ge=0)],
) -> Annotated[CallToolResult, ProductOut]:
    s = SHOPS_BY_SLUG.get(shop)
    if s is None:
        return _unknown_shop(shop)
    try:
        products = _catalogue(s)
    except CatalogueError as exc:
        return error(f"{exc}. Try again later.")
    p = next((x for x in products if x["id"] == product_id), None)
    if p is None:
        return error(f"{s['name']} has no product with id {product_id}. Use search_products to find current ids.")
    prod = _shape(s, p)
    text = _line(prod)
    if prod["description"]:
        text += "\n" + prod["description"]
    if prod["demo"]:
        text += "\n(Demo Shop is sample data, not a real shop.)"
    return result(text, {"kind": "product", "product": prod})


apps.add_html_resource(
    WIDGET,
    widget_html("Shops from Telegram", BODY, SCRIPT, extra_css=CSS),
    title="Telegram shop catalogue",
    description="Product cards from shops that sell through Telegram channels, with links to each shop's site.",
    csp=ResourceCsp(connect_domains=[], resource_domains=SHOP_ORIGINS),
    prefers_border=True,
)

mcp = MCPServer(
    "tg-shop",
    title="Shops from Telegram Channels",
    version="0.1.0",
    instructions=(
        "Searches the catalogues of small shops that sell through public Telegram channels (catalogues built "
        "with tg-storefront). Use search_products to find items (Uzbek works in Cyrillic or Latin, Russian and "
        "English titles are matched as written), get_product for one item's photos and details, and list_shops "
        "to see which shops are registered. Quote prices exactly as returned; the tools do not know stock, "
        "delivery or payment terms beyond what the shop wrote in the description. To order, send the user to "
        "the product_page link on the shop's own site. 'Demo Shop (sample data)' is a fictional sample shop."
    ),
    extensions=[apps],
)
