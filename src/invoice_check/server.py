"""Invoice Check: re-does the arithmetic of supplier proformas, quotations and invoices.

Built on invoice-lint (https://github.com/abafaboy/invoice-lint). This server adds no
checking logic of its own: it downloads the file ChatGPT hands over, writes it to a
temporary directory that is deleted straight afterwards, and runs invoice-lint on it.
"""

from __future__ import annotations

import json
import re
import tempfile
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal

import httpx
from pydantic import BaseModel, Field

from mcp.server.apps import Apps, ResourceCsp
from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult

from invoice_lint.lint import check_file, diff_files
from invoice_lint.readers import ReadError
from invoice_lint.report import (
    doc_heading,
    document_dict,
    finding_dict,
    render_diff_text,
    render_rules_json,
    render_text,
)
from invoice_lint.rules import Context
from plugkit import READ_ONLY, error, result, tracked, widget_html
from plugkit.usage import to_thread

from .widget import BODY, EXTRA_CSS, SCRIPT

PLUGIN = "invoice-check"
WIDGET = "ui://invoice-check/report.html"
MAX_BYTES = 10 * 1024 * 1024
TIMEOUT = 20.0

SUPPORTED = ("pdf", "xlsx", "csv", "json")
MIME_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "text/csv": "csv",
    "application/csv": "csv",
    "text/comma-separated-values": "csv",
    "application/json": "json",
    "text/json": "json",
}
SUPPORTED_TEXT = "PDF (with a text layer), XLSX, CSV or JSON"
NOTE = (
    "Checked arithmetic and internal consistency only, not prices against the market or legal "
    "validity. Confirm any finding with the supplier before paying."
)


# ------------------------------------------------------------------ input


class UploadedFile(BaseModel):
    """A file the user attached in ChatGPT."""

    download_url: str = Field(description="Temporary URL the file can be downloaded from.", max_length=4096)
    file_id: str = Field(description="ChatGPT's id for the file.", max_length=512)
    mime_type: str | None = Field(default=None, description="MIME type, if known.", max_length=200)
    file_name: str | None = Field(default=None, description="Original file name, if known.", max_length=512)


# ------------------------------------------------------------------ output


class LineOut(BaseModel):
    index: int
    no: str | None
    code: str | None
    description: str
    qty: str | None
    unit: str | None
    unit_price: str | None
    amount: str | None
    currency: str | None
    ref: str


class SummaryRowOut(BaseModel):
    kind: str
    label: str
    amount: str | None
    rate: str | None
    included: bool
    ref: str


class ExchangeRateOut(BaseModel):
    base: str
    quote: str
    rate: str | None


class DocumentOut(BaseModel):
    heading: str
    file_name: str | None
    type: str | None
    title: str | None
    number: str | None
    issue_date: str | None
    valid_until: str | None
    currency: str | None
    supplier: str | None
    buyer: str | None
    incoterm: str | None
    incoterm_place: str | None
    incoterms_version: str | None
    payment_terms: str | None
    delivery_time: str | None
    number_format: str | None
    exchange_rates: list[ExchangeRateOut]
    lines: list[LineOut]
    summary: list[SummaryRowOut]
    total_in_words: str | None
    notes: list[str]


class FindingOut(BaseModel):
    rule: str
    name: str | None
    severity: str
    location: str | None
    line: int | None
    field: str | None
    message: str
    expected: str | None
    actual: str | None


class Counts(BaseModel):
    error: int
    warning: int
    info: int


class CheckOut(BaseModel):
    kind: Literal["check"]
    as_of: str
    tolerance: str
    document: DocumentOut
    findings: list[FindingOut]
    counts: Counts
    note: str


class CompareOut(BaseModel):
    kind: Literal["compare"]
    old: DocumentOut
    new: DocumentOut
    changes: list[FindingOut]
    note: str


class RuleOut(BaseModel):
    id: str
    name: str
    severity: str
    mode: str
    heuristic: bool
    summary: str


class RulesOut(BaseModel):
    kind: Literal["rules"]
    rules: list[RuleOut]


# Tools and the widget are registered on `apps` first; the server is built at the
# bottom of this file because MCPServer reads an extension's tools when constructed.
apps = Apps()


# ------------------------------------------------------------------ download


class DownloadError(Exception):
    """The file could not be fetched from ChatGPT's download URL."""


def _require_https(request: httpx.Request) -> None:
    if request.url.scheme != "https":
        raise DownloadError("the download link is not https")


def _download_file(url: str) -> bytes:
    if not url.lower().startswith("https://"):
        raise DownloadError("the download link is not https")
    with httpx.Client(
        timeout=TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": "invoice-check-plugin/0.1"},
        event_hooks={"request": [_require_https]},
    ) as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            declared = resp.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > MAX_BYTES:
                raise DownloadError("the file is larger than 10 MB")
            chunks: list[bytes] = []
            size = 0
            for chunk in resp.iter_bytes():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise DownloadError("the file is larger than 10 MB")
                chunks.append(chunk)
    return b"".join(chunks)


# Replaced in tests; ChatGPT's file URLs are not reachable from the build sandbox.
download_file = _download_file


# ------------------------------------------------------------------ helpers


def _file_type(f: UploadedFile) -> str | None:
    """'pdf' / 'xlsx' / 'csv' / 'json' from the file name's extension, else the MIME type."""
    name = (f.file_name or "").strip()
    suffix = PurePosixPath(name.replace("\\", "/")).suffix.lower().lstrip(".")
    if suffix:
        return suffix if suffix in SUPPORTED else None
    mime = (f.mime_type or "").split(";")[0].strip().lower()
    return MIME_TYPES.get(mime)


def _display_name(f: UploadedFile) -> str | None:
    if not f.file_name:
        return None
    return PurePosixPath(f.file_name.replace("\\", "/")).name[:200] or None


def _clean_reason(exc: Exception, tmp: str) -> str:
    """invoice-lint prefixes messages with the file path; drop the temporary path."""
    text = str(exc).replace(tmp + "/", "").replace(tmp, "")
    text = re.sub(r"^(old|new|document)\.(pdf|xlsx|csv|json):\s*", "", text)
    text = re.sub(r"\b(old|new|document)\.(pdf|xlsx|csv|json)\b", "the file", text)
    return text.strip()[:300] or exc.__class__.__name__


class ParseError(Exception):
    """A short, path-free reason the document could not be read."""


def _with_files(files: list[tuple[str, bytes, str]], fn: Any) -> Any:
    """Write each (stem, bytes, ext) to a temporary directory, call fn(paths), delete the directory."""
    with tempfile.TemporaryDirectory(prefix="invoice-check-") as tmp:
        paths = []
        for stem, data, ext in files:
            p = Path(tmp) / f"{stem}.{ext}"
            p.write_bytes(data)
            paths.append(p)
        try:
            return fn(*paths)
        except ReadError as exc:
            raise ParseError(_clean_reason(exc, tmp)) from None
        except Exception as exc:  # any parser failure on an untrusted file
            raise ParseError(f"the file could not be parsed ({exc.__class__.__name__})") from None


def _doc(doc: Any, file_name: str | None) -> dict[str, Any]:
    d = document_dict(doc)
    d.pop("source", None)
    d["heading"] = doc_heading(doc)
    d["file_name"] = file_name
    return d


async def _fetch(f: UploadedFile, label: str) -> tuple[bytes, str] | CallToolResult:
    ext = _file_type(f)
    if ext is None:
        return error(f"The {label} is not a supported type. Supported: {SUPPORTED_TEXT}.")
    try:
        data = await to_thread(download_file, f.download_url)
    except (httpx.HTTPError, DownloadError, OSError, ValueError) as exc:
        reason = str(exc) if isinstance(exc, DownloadError) else exc.__class__.__name__
        return error(f"The {label} could not be downloaded ({reason}). Ask the user to attach it again.")
    if not data:
        return error(f"The {label} is empty.")
    return data, ext


_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


# ------------------------------------------------------------------ tools


@apps.tool(
    resource_uri=WIDGET,
    name="check_invoice",
    title="Check a proforma or invoice",
    description=(
        "Re-check a supplier proforma, quotation, invoice, счёт на оплату or коммерческое предложение "
        "(PDF with a text layer, XLSX, CSV or JSON). Re-does quantity × price, subtotal, discount, VAT, "
        "freight and grand total, reads the total in words (EN/RU/UZ), and checks currencies, number "
        "formats, validity dates and Incoterms. Returns each finding with the arithmetic it used. "
        "It does not judge whether prices are fair or whether the document is legally valid."
    ),
    annotations=READ_ONLY,
    meta={
        "openai/fileParams": ["file"],
        "openai/toolInvocation/invoking": "Checking the document…",
        "openai/toolInvocation/invoked": "Checked",
    },
)
@tracked(PLUGIN)
async def check_invoice(
    file: Annotated[UploadedFile, Field(description="The proforma, quotation or invoice the user attached.")],
    as_of: Annotated[
        str | None,
        Field(description="Date used for the 'validity expired' check, YYYY-MM-DD. Default: today.", max_length=10),
    ] = None,
    tolerance: Annotated[
        str, Field(description="Allowed rounding difference on money amounts, e.g. '0.01' or '1'.", max_length=20)
    ] = "0.01",
) -> Annotated[CallToolResult, CheckOut]:
    if as_of is None:
        as_of_date = date.today()
    else:
        try:
            if not _DATE.fullmatch(as_of):
                raise ValueError
            as_of_date = date.fromisoformat(as_of)
        except ValueError:
            return error(f"as_of must be a date in YYYY-MM-DD form, got {as_of!r}.")
    try:
        tol = Decimal(tolerance.strip())
    except InvalidOperation:
        return error(f"tolerance must be a number such as 0.01, got {tolerance!r}.")
    if not tol.is_finite() or tol < 0:
        return error("tolerance must be a non-negative number such as 0.01.")

    fetched = await _fetch(file, "file")
    if isinstance(fetched, CallToolResult):
        return fetched
    data, ext = fetched
    ctx = Context(tolerance=tol, as_of=as_of_date)
    try:
        res = await to_thread(_with_files, [("document", data, ext)], lambda p: check_file(p, ctx))
    except ParseError as exc:
        return error(f"The file could not be checked: {exc}")

    name = _display_name(file)
    res.doc.source = name or "Uploaded document"
    text = render_text([res]).rstrip() + "\n" + NOTE
    return result(
        text,
        {
            "kind": "check",
            "as_of": as_of_date.isoformat(),
            "tolerance": format(tol, "f"),
            "document": _doc(res.doc, name),
            "findings": [finding_dict(f) for f in res.findings],
            "counts": res.counts,
            "note": NOTE,
        },
    )


@apps.tool(
    resource_uri=WIDGET,
    name="compare_quotations",
    title="Compare two quotation versions",
    description=(
        "Compare two versions of the same supplier document (quotation v1 vs v2, proforma vs final "
        "invoice): lines added or removed, unit price and quantity changes, total changes, and changed "
        "terms (currency, Incoterm, payment, delivery, validity). Files: PDF with a text layer, XLSX, "
        "CSV or JSON."
    ),
    annotations=READ_ONLY,
    meta={
        "openai/fileParams": ["old_file", "new_file"],
        "openai/toolInvocation/invoking": "Comparing versions…",
        "openai/toolInvocation/invoked": "Compared",
    },
)
@tracked(PLUGIN)
async def compare_quotations(
    old_file: Annotated[UploadedFile, Field(description="The earlier version (e.g. quotation v1 or the proforma).")],
    new_file: Annotated[UploadedFile, Field(description="The later version (e.g. quotation v2 or the final invoice).")],
) -> Annotated[CallToolResult, CompareOut]:
    old = await _fetch(old_file, "old file")
    if isinstance(old, CallToolResult):
        return old
    new = await _fetch(new_file, "new file")
    if isinstance(new, CallToolResult):
        return new
    try:
        res = await to_thread(_with_files, [("old", old[0], old[1]), ("new", new[0], new[1])], diff_files)
    except ParseError as exc:
        return error(f"The files could not be compared: {exc}")

    old_name, new_name = _display_name(old_file), _display_name(new_file)
    res.old.source = old_name or "old version"
    res.new.source = new_name or "new version"
    return result(
        render_diff_text(res).rstrip() + "\n" + NOTE,
        {
            "kind": "compare",
            "old": _doc(res.old, old_name),
            "new": _doc(res.new, new_name),
            "changes": [finding_dict(f) for f in res.changes],
            "note": NOTE,
        },
    )


@apps.tool(
    resource_uri=WIDGET,
    name="list_invoice_rules",
    title="List the invoice checks",
    description=(
        "List every check the invoice checker runs (rule id such as IL101, severity and what it checks). "
        "Use when the user asks what is checked or what a rule id in a finding means."
    ),
    annotations=READ_ONLY,
)
@tracked(PLUGIN)
def list_invoice_rules() -> Annotated[CallToolResult, RulesOut]:
    rules = json.loads(render_rules_json())
    lines = [f"{r['id']}  {r['severity']:<8} {r['summary']}{' (heuristic)' if r['heuristic'] else ''}" for r in rules]
    return result("\n".join(lines), {"kind": "rules", "rules": rules})


apps.add_html_resource(
    WIDGET,
    widget_html("Invoice check", BODY, SCRIPT, EXTRA_CSS),
    title="Invoice check report",
    description="Shows the findings for a proforma or invoice, the changes between two versions, or the rule list.",
    csp=ResourceCsp(connect_domains=[], resource_domains=[]),
    prefers_border=True,
)

mcp = MCPServer(
    "invoice-check",
    title="Proforma & Invoice Checker",
    version="0.1.0",
    instructions=(
        "Re-checks supplier proformas, quotations and invoices (PDF with a text layer, XLSX, CSV, JSON) "
        "the user attaches: quantity × price, subtotal, discount, VAT, freight, grand total, the total in "
        "words (English, Russian сумма прописью, Uzbek), currencies, number formats, validity dates and "
        "Incoterms, and compares two versions of a document. Use the tools rather than re-adding figures "
        "by hand. Explain each finding with the numbers it shows. A result with no findings means nothing "
        "inconsistent was found, not that the document is correct: prices, market value and legal validity "
        "are not checked. Scanned PDFs without a text layer cannot be read."
    ),
    extensions=[apps],
)
