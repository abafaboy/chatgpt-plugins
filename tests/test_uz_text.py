import json

import pytest
from mcp import Client

import uz_text.server as srv

pytestmark = pytest.mark.anyio

CBU_SAMPLE = [
    {"id": 68, "Code": "840", "Ccy": "USD", "CcyNm_RU": "Доллар США", "CcyNm_UZ": "AQSH dollari",
     "CcyNm_UZC": "АҚШ доллари", "CcyNm_EN": "US Dollar", "Nominal": "1", "Rate": "11808.76",
     "Diff": "-12.42", "Date": "01.10.2026"},
    {"id": 20, "Code": "978", "Ccy": "EUR", "CcyNm_RU": "Евро", "CcyNm_UZ": "EVRO", "CcyNm_UZC": "ЕВРО",
     "CcyNm_EN": "Euro", "Nominal": "1", "Rate": "13404.12", "Diff": "-15.28", "Date": "01.10.2026"},
]  # shape copied from the live feed on 2 Oct 2026


@pytest.fixture
async def client(monkeypatch):
    monkeypatch.setattr(srv, "fetch_rates", lambda: CBU_SAMPLE)
    async with Client(srv.mcp, mode="legacy") as c:
        yield c


async def test_tools_are_read_only_and_bound_to_widget(client):
    tools = (await client.list_tools()).tools
    assert {t.name for t in tools} == {
        "convert_uzbek_script", "write_amount_in_uzbek_words", "normalize_uzbek_text", "get_uzbek_exchange_rates"}
    for t in tools:
        a = t.annotations
        assert a.read_only_hint is True and a.destructive_hint is False and a.open_world_hint is not None
        assert t.meta["ui"]["resourceUri"] == srv.WIDGET
        assert t.output_schema is not None, t.name
        assert t.title


async def test_convert_all_three_scripts(client):
    r = await client.call_tool("convert_uzbek_script", {"text": "Ўзбекистон Республикаси", "target": "latin"})
    assert not r.is_error
    assert r.structured_content["converted"] == "Oʻzbekiston Respublikasi"
    assert r.structured_content["versions"]["new_latin"] == "Özbekiston Respublikasi"
    assert r.structured_content["note"] == ""


async def test_new_latin_carries_the_unsigned_law_note(client):
    r = await client.call_tool("convert_uzbek_script", {"text": "Toshkent shahri", "target": "new_latin"})
    assert r.structured_content["converted"] == "Toşkent şahri"
    assert "Senate" in r.structured_content["note"]


async def test_too_long_text_is_refused(client):
    r = await client.call_tool("convert_uzbek_script", {"text": "a" * (srv.MAX_CHARS + 1), "target": "latin"})
    assert r.is_error


async def test_amount_in_words(client):
    r = await client.call_tool("write_amount_in_uzbek_words", {"amount": "1 250 000,50"})
    assert r.structured_content["words"] == "bir million ikki yuz ellik ming soʻm ellik tiyin"
    r = await client.call_tool("write_amount_in_uzbek_words", {"amount": "1992", "script": "cyrillic"})
    assert r.structured_content["words"].startswith("бир минг")


async def test_bad_amount_is_an_error_not_a_crash(client):
    r = await client.call_tool("write_amount_in_uzbek_words", {"amount": "-5"})
    assert r.is_error and r.content[0].text.startswith("Could not read that amount")


async def test_normalize(client):
    r = await client.call_tool("normalize_uzbek_text", {"text": "O`zbekiston san'at"})
    assert r.structured_content["normalized"] == "Oʻzbekiston sanʼat"
    assert r.structured_content["changed"] is True


async def test_rates_filter_and_missing(client):
    r = await client.call_tool("get_uzbek_exchange_rates", {"currencies": ["usd", "XYZ"]})
    sc = r.structured_content
    assert [x["code"] for x in sc["rates"]] == ["USD"]
    assert sc["missing"] == ["XYZ"]
    assert sc["dates"] == ["01.10.2026"]
    assert "11808.76" in r.content[0].text


async def test_rates_feed_down(client, monkeypatch):
    def boom():
        raise ValueError("unexpected response shape")
    monkeypatch.setattr(srv, "fetch_rates", boom)
    r = await client.call_tool("get_uzbek_exchange_rates", {})
    assert r.is_error


async def test_widget_resource(client):
    rr = await client.read_resource(srv.WIDGET)
    html = rr.contents[0].text
    assert rr.contents[0].mime_type == "text/html;profile=mcp-app"
    assert "plugkit" in html and "ui/notifications/tool-result" in html


async def test_usage_is_logged_without_content(client, usage_log):
    await client.call_tool("convert_uzbek_script", {"text": "secret words", "target": "latin"})
    lines = usage_log.read_text().splitlines()
    ev = json.loads(lines[-1])
    assert ev["plugin"] == "uz-text" and ev["tool"] == "convert_uzbek_script" and ev["ok"] is True
    assert "secret" not in usage_log.read_text()
