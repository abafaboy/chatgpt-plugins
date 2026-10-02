"""The public pages OpenAI's submission form asks for, served by the same process.

    /                      index of the five plugins
    /site/<slug>           website URL for one plugin
    /privacy               privacy policy (one policy, sections per plugin)
    /terms                 terms of service
Support URL: the GitHub issues page (SUPPORT_URL below).

Every statement here describes what the code in this repository actually does.
If the code changes, change this file in the same commit.
"""

from __future__ import annotations

import html
from datetime import date

from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.routing import Route

OPERATOR = "Abdulfayyod Mukhamedov (Tashkent, Uzbekistan)"
REPO_URL = "https://github.com/abafaboy/chatgpt-plugins"
SUPPORT_URL = REPO_URL + "/issues"
UPDATED = date(2026, 10, 2)

PLUGINS: dict[str, dict] = {
    "uz-text": {
        "name": "UzText: Uzbek Scripts & Sums",
        "what": "Converts Uzbek text between Cyrillic, the 1995 Latin alphabet and the new Latin alphabet "
                "(Ö Ğ Ş Ç, approved by the Senate on 10 September 2026), writes amounts in Uzbek words for "
                "invoices, fixes apostrophe variants, and shows the Central Bank of Uzbekistan's official "
                "exchange rates.",
        "try": ["Write “Oʻzbekiston Respublikasi” in Cyrillic.",
                "Write 1 250 000,50 soʻm in words for an invoice.",
                "What is today's official USD rate in Uzbekistan?"],
        "receives": "the text or amount you ask it to convert, and the currency codes you ask about",
        "third_parties": "To show exchange rates the server requests the public rate list from cbu.uz "
                         "(the Central Bank of Uzbekistan). That request contains no information about you.",
    },
    "tg-shop": {
        "name": "Shops from Telegram Channels",
        "what": "Searches the catalogues of small shops that sell through public Telegram channels and links "
                "each product to the page on the shop's own website. It does not take orders or payments.",
        "try": ["Show me gifts under 200 000 soʻm.", "Find a thermos.", "Which shops can I browse?"],
        "receives": "your search words and filters (shop, category, maximum price)",
        "third_parties": "The server downloads each registered shop's public products.json from that shop's "
                         "website. Those requests contain no information about you. Orders happen on the "
                         "shop's own site or Telegram chat and are between you and the shop.",
    },
    "invoice-check": {
        "name": "Proforma & Invoice Checker",
        "what": "Re-checks the arithmetic and consistency of supplier proformas, quotations and invoices "
                "(PDF with a text layer, XLSX, CSV, JSON): line amounts, subtotal, discount, VAT, freight, "
                "total, total in words, currencies, number formats, validity dates and Incoterms, and "
                "compares two versions of a quotation. It checks arithmetic and consistency only.",
        "try": ["Check this proforma before I pay it. (attach a PDF)",
                "What changed between these two quotations? (attach both)",
                "Which checks do you run?"],
        "receives": "the document files you attach, which ChatGPT passes to the server as temporary download links",
        "third_parties": "The server downloads the file from the temporary link ChatGPT provides, saves it "
                         "under a generic name in a temporary folder, checks it, and deletes the folder "
                         "when the check finishes. Files and their contents are not kept.",
    },
    "speaking-coach": {
        "name": "Speaking Band Coach",
        "what": "IELTS-style English speaking practice: a three-part mock test with a Part 2 timer, word and "
                "fluency statistics for your answers, and feedback on the four speaking criteria. Scores are "
                "practice estimates. Not affiliated with or endorsed by IELTS, the British Council, IDP or "
                "Cambridge University Press & Assessment.",
        "try": ["Give me a full speaking mock test.", "Give me a Part 2 cue card about travel.",
                "Assess my answer to this question."],
        "receives": "the transcript of your answers when ChatGPT asks for statistics, and the criterion "
                    "scores and feedback ChatGPT writes",
        "third_parties": "None. The question bank is stored on the server; nothing is sent elsewhere.",
    },
    "gpt-to-plugin": {
        "name": "GPT to Plugin Packager",
        "what": "Turns a custom GPT's name, description, instructions and conversation starters into a "
                "portable plugin folder (plugin.json, a skill, a README of the remaining manual steps), and "
                "checks plugin folders against the rules in OpenAI's plugin documentation.",
        "try": ["Turn my custom GPT into a plugin package. (paste its instructions)",
                "Check this plugin.json and SKILL.md before I submit.",
                "Which rules do you check?"],
        "receives": "the GPT configuration or the plugin files you paste",
        "third_parties": "None.",
    },
}

CSS = """
:root{color-scheme:light dark;--fg:#16181d;--bg:#fff;--muted:#5b6270;--line:#e3e6eb;--accent:#0b6bcb}
@media (prefers-color-scheme:dark){:root{--fg:#eceef2;--bg:#17181b;--muted:#a3a9b5;--line:#2d3036;--accent:#6cb4ff}}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:760px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:28px;line-height:1.25;margin:0 0 8px}h2{font-size:19px;margin:32px 0 8px}
a{color:var(--accent)}.muted{color:var(--muted);font-size:14px}
nav{display:flex;gap:16px;flex-wrap:wrap;font-size:14px;margin-bottom:24px}
.card{border:1px solid var(--line);border-radius:12px;padding:16px;margin:12px 0}
img.icon{width:56px;height:56px;border-radius:14px;vertical-align:middle;margin-right:12px}
li{margin:4px 0}
"""


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    nav = (f'<nav><a href="/">All plugins</a><a href="/privacy">Privacy</a><a href="/terms">Terms</a>'
           f'<a href="{SUPPORT_URL}">Support</a><a href="{REPO_URL}">Source code</a></nav>')
    return HTMLResponse(
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head>"
        f"<body><main>{nav}{body}</main></body></html>",
        status_code=status,
    )


def _e(s: str) -> str:
    return html.escape(s)


async def index(_: Request) -> Response:
    cards = "".join(
        f'<div class="card"><h2 style="margin-top:0"><a href="/site/{slug}">{_e(p["name"])}</a></h2>'
        f'<p>{_e(p["what"])}</p></div>'
        for slug, p in PLUGINS.items()
    )
    return _page("ChatGPT plugins by Abdulfayyod Mukhamedov",
                 f"<h1>ChatGPT plugins</h1><p class=\"muted\">Built and run by {_e(OPERATOR)}. "
                 f"The source code is public.</p>{cards}")


async def plugin_page(request: Request) -> Response:
    slug = request.path_params["slug"]
    p = PLUGINS.get(slug)
    if not p:
        return _page("Not found", "<h1>Not found</h1>", status=404)
    tries = "".join(f"<li>{_e(t)}</li>" for t in p["try"])
    return _page(p["name"], (
        f"<h1>{_e(p['name'])}</h1><p>{_e(p['what'])}</p>"
        f"<h2>Try asking</h2><ul>{tries}</ul>"
        f"<h2>What it sends to our server</h2><p>Only {_e(p['receives'])}. "
        f"See the <a href=\"/privacy#{slug}\">privacy policy</a>.</p>"
        f"<h2>Help</h2><p>Report a problem or ask a question on "
        f"<a href=\"{SUPPORT_URL}\">GitHub issues</a>.</p>"
    ))


async def privacy(_: Request) -> Response:
    sections = "".join(
        f'<h2 id="{slug}">{_e(p["name"])}</h2>'
        f"<p><strong>What the server receives:</strong> {_e(p['receives'])}.</p>"
        f"<p><strong>Other services involved:</strong> {_e(p['third_parties'])}</p>"
        for slug, p in PLUGINS.items()
    )
    body = f"""
<h1>Privacy policy</h1>
<p class="muted">Last updated {UPDATED:%d %B %Y}. Operator: {_e(OPERATOR)}. Contact: <a href="{SUPPORT_URL}">GitHub issues</a>.</p>
<p>This policy covers the five ChatGPT plugins listed on this site. They run on one server whose
source code is public at <a href="{REPO_URL}">{REPO_URL}</a>.</p>

<h2>What we collect</h2>
<ul>
<li><strong>What you ask the plugin to work on.</strong> When ChatGPT uses one of these plugins, it sends the
server the tool input described for each plugin below. The server uses it to produce the answer and does
not store it.</li>
<li><strong>Usage counts.</strong> For each tool call the server writes one line: the time, the plugin, the tool,
whether it succeeded and how long it took. It does not record what you typed, uploaded or received, and
it does not record who you are. We use these counts only to see which plugins are used.</li>
<li><strong>Hosting logs.</strong> The hosting provider may keep standard request logs (IP address, time,
requested path) for security and operations.</li>
</ul>
<p>We do not have accounts, do not ask for your name, email or payment details, do not use cookies on the
plugin server, do not sell data, and do not use your inputs to train models.</p>

<h2>How long we keep it</h2>
<p>Inputs and uploaded files are discarded when the tool call finishes. Usage counts are kept while the
plugins are running and deleted when they are shut down.</p>

<h2>Plugin by plugin</h2>
{sections}

<h2>Children</h2>
<p>The plugins are meant for general audiences aged 13 and over and are not directed at children under 13.</p>

<h2>Your choices</h2>
<p>You can stop using a plugin at any time by disconnecting it in ChatGPT. Because we do not store your
inputs or identify you, there is no personal data to access or delete; ask on
<a href="{SUPPORT_URL}">GitHub issues</a> if you have a question.</p>

<h2>Changes</h2>
<p>We will update this page, and its date, if what the plugins collect changes.</p>
"""
    return _page("Privacy policy", body)


async def terms(_: Request) -> Response:
    body = f"""
<h1>Terms of service</h1>
<p class="muted">Last updated {UPDATED:%d %B %Y}. Operator: {_e(OPERATOR)}.</p>
<p>By using these plugins you agree to the following.</p>
<h2>What you get</h2>
<p>The plugins are provided free of charge and “as is”, without warranties of any kind. They may change
or stop working without notice.</p>
<h2>Check the results yourself</h2>
<ul>
<li><strong>Proforma & Invoice Checker</strong> re-checks arithmetic and consistency only. It does not judge
prices, legal validity or the supplier. Confirm findings with the supplier before paying.</li>
<li><strong>Speaking Band Coach</strong> gives practice estimates, not official scores, and is not affiliated
with or endorsed by IELTS, the British Council, IDP or Cambridge University Press & Assessment.</li>
<li><strong>UzText</strong> shows the Central Bank of Uzbekistan's published rates; check the date shown.
The new Latin alphabet was approved by the Senate on 10 September 2026; check its legal status before
using it in official documents.</li>
<li><strong>Shops from Telegram Channels</strong> shows what shops publish. Orders, payment and delivery are
between you and the shop.</li>
<li><strong>GPT to Plugin Packager</strong> checks the rules listed on its rules page; passing those checks
does not guarantee that OpenAI will approve a plugin.</li>
</ul>
<h2>Acceptable use</h2>
<p>Do not use the plugins to break the law, to overload the server, or to process documents you are not
allowed to share.</p>
<h2>Liability</h2>
<p>To the extent the law allows, the operator is not liable for losses arising from use of the plugins or
their results.</p>
<h2>Contact</h2>
<p><a href="{SUPPORT_URL}">GitHub issues</a>.</p>
"""
    return _page("Terms of service", body)


routes = [
    Route("/", index),
    Route("/site/{slug}", plugin_page),
    Route("/privacy", privacy),
    Route("/terms", terms),
]
