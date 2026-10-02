# chatgpt-plugins

Five ChatGPT plugins, built to find out which one people actually use. Each plugin is an MCP
server with a widget and a skill; all five run in one web process, and every tool call is
counted (without recording what anyone typed) so the winner can be picked from data.

| Plugin | What it does | Built on |
|---|---|---|
| **UzText: Uzbek Scripts & Sums** (`uz-text`) | Cyrillic ↔ Latin ↔ new Latin, amounts in Uzbek words, apostrophe fixes, Central Bank of Uzbekistan rates | [uztext](https://github.com/abafaboy/uztext) |
| **Shops from Telegram Channels** (`tg-shop`) | Search tg-storefront shop catalogues; link to the shop's own product page | [tg-storefront](https://github.com/abafaboy/tg-storefront) |
| **Proforma & Invoice Checker** (`invoice-check`) | Re-check the arithmetic of proformas, quotations and invoices; diff two versions | [invoice-lint](https://github.com/abafaboy/invoice-lint) |
| **Speaking Band Coach** (`speaking-coach`) | IELTS-style speaking mock test, transcript statistics, criterion feedback | 200 original practice questions |
| **GPT to Plugin Packager** (`gpt-to-plugin`) | Turn a custom GPT's configuration into a plugin folder; validate plugin folders | OpenAI's plugin docs |

Screenshots of every widget, light and dark, rendered from real tool output:
[`docs/widgets/`](docs/widgets/).

## What has been tested, and what hasn't

Tested here:
- 148 automated tests (`pytest`): every tool's results and refusals, annotations, output schemas,
  widget resources, usage logging, the public pages, `/stats` access control.
- All five servers answer over HTTP (`initialize` with protocol 2025-06-18, `tools/list`,
  `tools/call`) in both the legacy and the newer connection mode.
- Every widget view rendered in headless Chromium through the MCP Apps message protocol, with no
  console errors (`scripts/render_widgets.py`).
- `pip install .` into a clean environment.

**Not tested yet:**
- Inside ChatGPT itself. Nothing has been connected to ChatGPT; that needs a public HTTPS URL.
- The live data sources from a deployed server: cbu.uz and the demo shop's products.json were
  unreachable from the build sandbox, so those calls ran against saved copies of the real responses.
- File download from a real ChatGPT file link (invoice checker).
- The Docker image build (no Docker daemon in the build sandbox; the same `pip install .` was tested).

## Run locally

```sh
pip install -e ".[dev]"
python -m pytest -q
chatgpt-plugins              # http://localhost:8000/<slug>/mcp, pages at http://localhost:8000/
npx @modelcontextprotocol/inspector   # connect to http://localhost:8000/uz-text/mcp
```

## Deploy (one service for all five)

1. Create a web service from this repo (Render: `render.yaml` is a Blueprint; any Docker host works).
   Render's free instances sleep after 15 idle minutes and take about a minute to wake, which is
   likely too slow for ChatGPT, so the Blueprint uses a paid plan and a 1 GB disk for the usage log.
2. Set `PUBLIC_HOST` to the service's hostname (turns on Host/Origin checks) and keep the generated
   `STATS_TOKEN` secret.
3. `python scripts/set_host.py <hostname>` and commit, so each `plugins/<slug>/mcp.json` points at
   the live server.
4. Check `https://<host>/healthz`, `/privacy`, `/terms`, `/site/<slug>`.

## Connect, test, submit

1. In ChatGPT, enable developer mode and add `https://<host>/<slug>/mcp` for each plugin. Run the test
   cases in [`docs/SUBMISSION.md`](docs/SUBMISSION.md).
2. Complete individual or business verification in the OpenAI Platform dashboard.
3. Submit each plugin with the values in [`docs/SUBMISSION.md`](docs/SUBMISSION.md).

## Measuring

```sh
curl -H "x-stats-token: $STATS_TOKEN" https://<host>/stats
```

Calls per plugin, per tool and per day, and error counts. Each event is also printed to the log
stream with the prefix `usage `.

## Layout

```
src/plugkit/        shared: usage counting, widget bridge, web app, public pages
src/<plugin>/       one MCP server per plugin (server.py, widget.py)
plugins/<slug>/     the plugin package: plugin.json, mcp.json, skills/, assets/icon.png
tests/              pytest suite and fixtures
scripts/            make_icons.py, render_widgets.py, set_host.py
docs/               CONVENTIONS.md (how a plugin is built), SUBMISSION.md, widget screenshots
```

MIT licence.
