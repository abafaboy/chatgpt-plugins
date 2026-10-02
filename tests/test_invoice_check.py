import json
import tempfile

import httpx
import pytest
from mcp import Client

import invoice_check.server as srv
from conftest import FIXTURES

pytestmark = pytest.mark.anyio

DOCS = FIXTURES / "invoice_check"


def upload(name: str, mime: str | None = None) -> dict:
    f = {"download_url": f"https://files.example/{name}", "file_id": f"file-{name}", "file_name": name}
    if mime:
        f["mime_type"] = mime
    return f


def fake_download(url: str) -> bytes:
    """Serve the sample documents by the last path segment of the URL."""
    name = url.rsplit("/", 1)[-1]
    path = DOCS / name
    if not path.is_file():
        raise httpx.HTTPStatusError("404", request=httpx.Request("GET", url), response=httpx.Response(404))
    return path.read_bytes()


@pytest.fixture
async def client(monkeypatch, tmp_path):
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp))
    monkeypatch.setattr(srv, "download_file", fake_download)
    async with Client(srv.mcp, mode="legacy") as c:
        c.tmp = tmp
        yield c


def codes(r, severity=None):
    return [f["rule"] for f in r.structured_content["findings"] if severity in (None, f["severity"])]


async def test_tools_are_read_only_and_bound_to_widget(client):
    tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {"check_invoice", "compare_quotations", "list_invoice_rules"}
    for t in tools.values():
        a = t.annotations
        assert a.read_only_hint is True and a.destructive_hint is False and a.open_world_hint is False
        assert t.meta["ui"]["resourceUri"] == srv.WIDGET
        assert t.output_schema is not None, t.name
        assert t.title
    assert tools["check_invoice"].meta["openai/fileParams"] == ["file"]
    assert tools["compare_quotations"].meta["openai/fileParams"] == ["old_file", "new_file"]
    assert "openai/fileParams" not in tools["list_invoice_rules"].meta


async def test_uploaded_file_schema_requires_url_and_id(client):
    tools = {t.name: t for t in (await client.list_tools()).tools}
    for name, params in (("check_invoice", ["file"]), ("compare_quotations", ["old_file", "new_file"])):
        schema = tools[name].input_schema
        assert set(params) <= set(schema["required"])
        for p in params:
            ref = schema["properties"][p]["$ref"].rsplit("/", 1)[-1]
            uploaded = schema["$defs"][ref]
            assert sorted(uploaded["required"]) == ["download_url", "file_id"]
            assert {"download_url", "file_id", "mime_type", "file_name"} == set(uploaded["properties"])


async def test_check_finds_planted_errors(client):
    r = await client.call_tool("check_invoice", {"file": upload("01_proforma_en.pdf"), "as_of": "2026-09-25"})
    assert not r.is_error
    sc = r.structured_content
    assert codes(r, "error") == ["IL101", "IL104"]
    assert "IL701" in codes(r, "warning")
    assert sc["counts"] == {"error": 2, "warning": 1, "info": 0}
    assert sc["document"]["number"] == "PI-2026-0417"
    assert sc["document"]["currency"] == "USD"
    assert sc["document"]["file_name"] == "01_proforma_en.pdf"
    assert "source" not in sc["document"]
    assert sc["as_of"] == "2026-09-25" and sc["tolerance"] == "0.01"
    text = r.content[0].text
    assert "IL101  Line 3 (Final drive travel motor): 2 × 6,180.00 = 12,360.00" in text
    assert "2 errors, 1 warning, 0 info" in text
    assert "not prices against the market" in text


async def test_clean_document_has_no_errors(client):
    r = await client.call_tool("check_invoice", {"file": upload("07_proforma_clean.pdf"), "as_of": "2026-09-25"})
    assert not r.is_error
    assert r.structured_content["counts"]["error"] == 0
    assert "no problems found" in r.content[0].text


async def test_csv_and_json(client):
    r = await client.call_tool("check_invoice", {"file": upload("05_proforma_mixed_formats.csv"), "as_of": "2026-09-25"})
    assert not r.is_error and "IL402" in codes(r, "error")
    r = await client.call_tool("check_invoice", {"file": upload("06_proforma.json"), "as_of": "2026-09-25"})
    assert not r.is_error and {"IL103", "IL302"} <= set(codes(r, "error"))


async def test_type_from_mime_when_name_has_no_extension(client, monkeypatch):
    data = (DOCS / "06_proforma.json").read_bytes()
    monkeypatch.setattr(srv, "download_file", lambda url: data)
    f = {"download_url": "https://files.example/x", "file_id": "file-x", "mime_type": "application/json; charset=utf-8"}
    r = await client.call_tool("check_invoice", {"file": f})
    assert not r.is_error and r.structured_content["document"]["file_name"] is None


async def test_compare_versions(client):
    r = await client.call_tool("compare_quotations", {
        "old_file": upload("03_quotation_v1.xlsx"), "new_file": upload("03_quotation_v2.xlsx")})
    assert not r.is_error
    changes = r.structured_content["changes"]
    assert len(changes) >= 1
    assert any(c["rule"] == "IL903" for c in changes)
    assert "change" in r.content[0].text


async def test_unsupported_type_is_refused(client):
    r = await client.call_tool("check_invoice", {"file": upload("contract.docx")})
    assert r.is_error and "PDF" in r.content[0].text and "XLSX" in r.content[0].text
    r = await client.call_tool("check_invoice", {"file": {"download_url": "https://x.example/a", "file_id": "f",
                                                           "mime_type": "image/png"}})
    assert r.is_error


async def test_download_failure_is_an_error(client, monkeypatch):
    def boom(url):
        raise httpx.ConnectError("unreachable")
    monkeypatch.setattr(srv, "download_file", boom)
    r = await client.call_tool("check_invoice", {"file": upload("01_proforma_en.pdf")})
    assert r.is_error and "could not be downloaded" in r.content[0].text


async def test_real_downloader_refuses_http():
    with pytest.raises(srv.DownloadError):
        srv._download_file("http://files.example/a.pdf")


async def test_unparseable_file_is_an_error_without_temp_path(client, monkeypatch):
    monkeypatch.setattr(srv, "download_file", lambda url: b"%PDF-1.4 not really a pdf")
    r = await client.call_tool("check_invoice", {"file": upload("broken.pdf")})
    assert r.is_error and r.content[0].text.startswith("The file could not be checked")
    assert "invoice-check-" not in r.content[0].text and str(client.tmp) not in r.content[0].text


async def test_scanned_pdf_is_refused_with_reason(client, monkeypatch):
    import io

    canvas = pytest.importorskip("reportlab.pdfgen.canvas")
    buf = io.BytesIO()
    cv = canvas.Canvas(buf)
    cv.rect(10, 10, 100, 100)  # a page with drawing but no text layer
    cv.save()
    monkeypatch.setattr(srv, "download_file", lambda url: buf.getvalue())
    r = await client.call_tool("check_invoice", {"file": upload("scan.pdf")})
    assert r.is_error and "no text layer" in r.content[0].text


async def test_bad_as_of_and_tolerance(client):
    for as_of in ("25.09.2026", "2026-13-01", "20260925"):
        r = await client.call_tool("check_invoice", {"file": upload("01_proforma_en.pdf"), "as_of": as_of})
        assert r.is_error and "YYYY-MM-DD" in r.content[0].text
    for tol in ("abc", "-1", "NaN"):
        r = await client.call_tool("check_invoice", {"file": upload("01_proforma_en.pdf"), "tolerance": tol})
        assert r.is_error and "tolerance" in r.content[0].text


async def test_list_rules(client):
    r = await client.call_tool("list_invoice_rules", {})
    rules = r.structured_content["rules"]
    assert len(rules) > 10
    assert {"IL101", "IL104", "IL201"} <= {x["id"] for x in rules}
    assert "IL101" in r.content[0].text


async def test_widget_resource(client):
    rr = await client.read_resource(srv.WIDGET)
    html = rr.contents[0].text
    assert rr.contents[0].mime_type == "text/html;profile=mcp-app"
    assert "plugkit" in html and "ui/notifications/tool-result" in html
    assert "innerHTML" not in html.split("<script>", 2)[-1]


async def test_usage_is_logged_without_content(client, usage_log):
    await client.call_tool("check_invoice", {"file": upload("01_proforma_en.pdf"), "as_of": "2026-09-25"})
    await client.call_tool("check_invoice", {"file": upload("contract.docx")})
    lines = [json.loads(x) for x in usage_log.read_text().splitlines()]
    assert [(e["plugin"], e["tool"], e["ok"]) for e in lines[-2:]] == [
        ("invoice-check", "check_invoice", True), ("invoice-check", "check_invoice", False)]
    log = usage_log.read_text()
    for secret in ("01_proforma_en", "contract", "PI-2026-0417", "Example Supplier", "files.example", "file-"):
        assert secret not in log


async def test_temp_files_are_deleted(client, monkeypatch):
    made = []
    real = tempfile.TemporaryDirectory

    def spy(*a, **kw):
        td = real(*a, **kw)
        made.append(td.name)
        return td

    monkeypatch.setattr(tempfile, "TemporaryDirectory", spy)
    await client.call_tool("check_invoice", {"file": upload("01_proforma_en.pdf"), "as_of": "2026-09-25"})
    await client.call_tool("compare_quotations", {
        "old_file": upload("03_quotation_v1.xlsx"), "new_file": upload("03_quotation_v2.xlsx")})
    monkeypatch.setattr(srv, "download_file", lambda url: b"%PDF-1.4 not really a pdf")
    r = await client.call_tool("check_invoice", {"file": upload("broken.pdf")})
    assert r.is_error
    assert len(made) == 3 and all(name.startswith(str(client.tmp)) for name in made)
    assert list(client.tmp.iterdir()) == []
