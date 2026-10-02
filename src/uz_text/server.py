"""UzText: Uzbek scripts, amounts in words and the central bank's exchange rates.

Built on uztext (https://github.com/abafaboy/uztext), whose 699-case golden
corpus covers the conversions. This server adds no conversion logic of its own.
"""

from __future__ import annotations

from typing import Annotated, Literal

import httpx
from pydantic import BaseModel, Field

from mcp.server.apps import Apps, ResourceCsp
from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult

import uztext
from plugkit import READ_ONLY, READ_ONLY_OPEN, error, result, tracked, widget_html

from .widget import BODY, SCRIPT

PLUGIN = "uz-text"
WIDGET = "ui://uz-text/card.html"
MAX_CHARS = 20_000
CBU_URL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"

Script = Literal["latin", "cyrillic", "new_latin"]


class Versions(BaseModel):
    latin: str
    cyrillic: str
    new_latin: str


class ScriptsOut(BaseModel):
    kind: Literal["scripts"]
    target: Script
    converted: str
    versions: Versions
    note: str


class AmountOut(BaseModel):
    kind: Literal["amount"]
    amount: str
    script: Script
    words: str


class NormalizedOut(BaseModel):
    kind: Literal["normalized"]
    original: str
    normalized: str
    search_key: str
    changed: bool


class Rate(BaseModel):
    code: str
    name_en: str | None
    name_uz: str | None
    nominal: str | None
    rate_uzs: str | None
    change: str | None
    date: str | None


class RatesOut(BaseModel):
    kind: Literal["rates"]
    source: str
    dates: list[str]
    rates: list[Rate]
    missing: list[str]

# Tools and the widget are registered on `apps` first; the server is built at the
# bottom of this file because MCPServer reads an extension's tools when constructed.
apps = Apps()

NEW_LATIN_NOTE = (
    "The new Latin alphabet (Ö Ğ Ş Ç) was approved by the Senate on 10 September 2026; "
    "check whether the law has been signed before using it in official documents."
)


def _all_scripts(text: str) -> dict[str, str]:
    return {
        "latin": uztext.to_latin(text),
        "cyrillic": uztext.to_cyrillic(text),
        "new_latin": uztext.to_new(text),
    }


@apps.tool(
    resource_uri=WIDGET,
    name="convert_uzbek_script",
    title="Convert Uzbek script",
    description=(
        "Convert Uzbek text to Cyrillic, current Latin (1995 alphabet, oʻ gʻ sh ch) or the new Latin "
        "alphabet (Ö Ğ Ş Ç). Use whenever the user wants Uzbek text transliterated or rewritten in "
        "another script. Returns the requested version and all three versions side by side."
    ),
    annotations=READ_ONLY,
    meta={"openai/toolInvocation/invoking": "Converting…", "openai/toolInvocation/invoked": "Converted"},
)
@tracked(PLUGIN)
def convert_uzbek_script(
    text: Annotated[str, Field(description="The Uzbek text, in any script.", min_length=1)],
    target: Annotated[Script, Field(description="Script to convert to.")],
) -> Annotated[CallToolResult, ScriptsOut]:
    if len(text) > MAX_CHARS:
        return error(f"The text is {len(text)} characters; the limit is {MAX_CHARS}. Split it into parts.")
    versions = _all_scripts(text)
    converted = versions[target]
    note = NEW_LATIN_NOTE if target == "new_latin" else ""
    return result(
        converted + (f"\n\n({note})" if note else ""),
        {"kind": "scripts", "target": target, "converted": converted, "versions": versions, "note": note},
    )


@apps.tool(
    resource_uri=WIDGET,
    name="write_amount_in_uzbek_words",
    title="Write an amount in Uzbek words",
    description=(
        "Write a money amount in Uzbek words, as required on invoices and contracts "
        "(summa soʻz bilan / сумма прописью). Accepts '1 250 000,50', '1250000.50' or a number. "
        "Default currency is soʻm with tiyin; pass another currency name in Uzbek if needed."
    ),
    annotations=READ_ONLY,
)
@tracked(PLUGIN)
def write_amount_in_uzbek_words(
    amount: Annotated[str, Field(description="The amount, e.g. '1 250 000,50'.", min_length=1, max_length=40)],
    script: Annotated[Script, Field(description="Script for the words.")] = "latin",
    currency: Annotated[str, Field(description="Currency name in Uzbek, e.g. soʻm, AQSH dollari, yevro.", max_length=40)] = "soʻm",
    subunit: Annotated[str, Field(description="Subunit name, e.g. tiyin, sent.", max_length=40)] = "tiyin",
) -> Annotated[CallToolResult, AmountOut]:
    lib_script = {"latin": "latin", "cyrillic": "cyrillic", "new_latin": "new"}[script]
    try:
        words = uztext.sum_words(amount, script=lib_script, currency=currency, subunit=subunit)
    except ValueError as exc:
        return error(f"Could not read that amount: {exc}.")
    return result(words, {"kind": "amount", "amount": amount, "script": script, "words": words})


@apps.tool(
    resource_uri=WIDGET,
    name="normalize_uzbek_text",
    title="Fix Uzbek apostrophes",
    description=(
        "Fix the apostrophe mess in Uzbek Latin text: ' ` ‘ ’ used for oʻ, gʻ and the tutuq belgisi are "
        "replaced with the correct characters. Also returns a search key that matches the same word in "
        "any script, useful for de-duplicating names."
    ),
    annotations=READ_ONLY,
)
@tracked(PLUGIN)
def normalize_uzbek_text(
    text: Annotated[str, Field(description="Uzbek text with mixed apostrophes.", min_length=1)],
) -> Annotated[CallToolResult, NormalizedOut]:
    if len(text) > MAX_CHARS:
        return error(f"The text is {len(text)} characters; the limit is {MAX_CHARS}.")
    fixed = uztext.normalize(text)
    return result(
        fixed,
        {"kind": "normalized", "original": text, "normalized": fixed, "search_key": uztext.search_key(text),
         "changed": fixed != text},
    )


def _fetch_cbu() -> list[dict]:
    with httpx.Client(timeout=10.0, headers={"User-Agent": "uz-text-plugin/0.1"}) as client:
        resp = client.get(CBU_URL)
        resp.raise_for_status()
        data = resp.json()
    if not isinstance(data, list):
        raise ValueError("unexpected response shape")
    return data


# Replaced in tests; the live feed is not reachable from the build sandbox.
fetch_rates = _fetch_cbu


@apps.tool(
    resource_uri=WIDGET,
    name="get_uzbek_exchange_rates",
    title="Central Bank of Uzbekistan rates",
    description=(
        "Today's official exchange rates of the Central Bank of Uzbekistan (soʻm per unit of currency), "
        "read live from cbu.uz. Use for converting prices, invoices or salaries to or from soʻm. "
        "Returns the date the bank set the rates; only the current rates are available."
    ),
    annotations=READ_ONLY_OPEN,
)
@tracked(PLUGIN)
def get_uzbek_exchange_rates(
    currencies: Annotated[
        list[str] | None,
        Field(description="ISO codes such as USD, EUR, RUB, KZT, CNY. Omit for the most used ones."),
    ] = None,
) -> Annotated[CallToolResult, RatesOut]:
    wanted = [c.strip().upper() for c in (currencies or ["USD", "EUR", "RUB", "KZT", "CNY", "GBP", "TRY"])][:30]
    try:
        rows = fetch_rates()
    except (httpx.HTTPError, ValueError) as exc:
        return error(f"The Central Bank's rate feed could not be read ({exc.__class__.__name__}). Try again later.")
    by_code = {str(r.get("Ccy", "")).upper(): r for r in rows}
    rates, missing = [], []
    for code in wanted:
        row = by_code.get(code)
        if not row:
            missing.append(code)
            continue
        rates.append({
            "code": code,
            "name_en": row.get("CcyNm_EN"),
            "name_uz": row.get("CcyNm_UZ"),
            "nominal": row.get("Nominal"),
            "rate_uzs": row.get("Rate"),
            "change": row.get("Diff"),
            "date": row.get("Date"),
        })
    dates = sorted({r["date"] for r in rates if r["date"]})
    lines = [f"{r['nominal']} {r['code']} = {r['rate_uzs']} soʻm" for r in rates]
    text = (f"Central Bank of Uzbekistan rates set for {', '.join(dates)}:\n" if dates else "") + "\n".join(lines)
    if missing:
        text += f"\nNot published by the bank: {', '.join(missing)}."
    return result(text, {"kind": "rates", "source": "cbu.uz", "dates": dates, "rates": rates, "missing": missing})


apps.add_html_resource(
    WIDGET,
    widget_html("UzText", BODY, SCRIPT),
    title="UzText card",
    description="Shows Uzbek text in three scripts, an amount in words, or the central bank's rates.",
    csp=ResourceCsp(connect_domains=[], resource_domains=[]),
    prefers_border=True,
)

mcp = MCPServer(
    "uz-text",
    title="UzText: Uzbek Scripts & Sums",
    version="0.1.0",
    instructions=(
        "Converts Uzbek text between Cyrillic, the current Latin alphabet (1995) and the new Latin "
        "alphabet approved by the Senate on 10 September 2026, writes amounts in Uzbek words for "
        "invoices, fixes apostrophe variants, and reads the Central Bank of Uzbekistan's official "
        "exchange rates. Use the tools instead of converting Uzbek by hand: the conversions have "
        "edge cases (ts/s, ye/e, the tutuq belgisi) that are easy to get wrong."
    ),
    extensions=[apps],
)
