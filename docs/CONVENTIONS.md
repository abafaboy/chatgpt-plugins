# How a plugin is built in this repo

Every plugin follows `src/uz_text/` exactly. Read `src/uz_text/server.py`,
`src/uz_text/widget.py` and `tests/test_uz_text.py` before writing a new one.

## Server (`src/<pkg>/server.py`)

- Python MCP SDK **2.x** (`mcp>=2.2`). It is not 1.x: there is no `FastMCP`;
  the class is `mcp.server.mcpserver.MCPServer`.
- Register tools on an `Apps()` instance (`from mcp.server.apps import Apps, ResourceCsp`)
  with `@apps.tool(resource_uri=WIDGET, name=..., title=..., description=..., annotations=...)`,
  then `@tracked(PLUGIN)` directly under it.
- Build `mcp = MCPServer(name, title=..., version=..., instructions=..., extensions=[apps])`
  at the **bottom** of the file. MCPServer reads the extension's tools when it is
  constructed; tools registered afterwards silently do not exist.
- Register the widget with `apps.add_html_resource(WIDGET, widget_html(title, BODY, SCRIPT), ...)`.
  `WIDGET` is `ui://<slug>/<name>.html`. Every UI-bound tool needs its resource registered.
- Annotations: `READ_ONLY` (computes/reads local data) or `READ_ONLY_OPEN` (reads the
  public internet). No tool in this repo writes, deletes or sends anything.
- Return type: `Annotated[CallToolResult, OutModel]` where `OutModel` is a pydantic
  `BaseModel`. This publishes an output schema and validates `structured_content`.
  Return `result(text_for_model, data_dict)` or `error(text)` from `plugkit`.
- Text returned to the model is short and factual. Data for the widget goes in the dict.
- Inputs are untrusted: bound every string (`max_length`) and list, and refuse oversized input
  with `error(...)` rather than raising.
- Anything that touches the network is a module-level function (`fetch_x = _fetch_x`) so
  tests can monkeypatch it. The build sandbox has no access to most of the internet.

## Widget (`src/<pkg>/widget.py`)

- `BODY` (HTML string) and `SCRIPT` (JS string). `plugkit.onData(cb)` delivers
  `structuredContent`; `plugkit.el(tag, attrs, children)` builds DOM. Never use
  `innerHTML` with tool data. `plugkit.callTool`, `plugkit.openLink` (https only),
  `plugkit.followUp` are available.
- Base styles are in `src/plugkit/static/base.css` (cards, tables, pills, light/dark).

## Tests (`tests/test_<pkg>.py`)

- `pytestmark = pytest.mark.anyio`; connect with `async with Client(srv.mcp, mode="legacy") as c`.
- Test: tool list (names, annotations, `meta["ui"]["resourceUri"]`, `output_schema`, `title`),
  every tool's happy path, every refusal path, the widget resource MIME type, and that the
  usage log records the call without any user content.

## Plugin package (`plugins/<slug>/`)

```
plugins/<slug>/
  plugin.json      portable manifest (agent-plugins.org schema)
  mcp.json         streamable-http URL https://HOST/<slug>/mcp (HOST filled by scripts/set_host.py)
  skills/<skill>/SKILL.md
  assets/icon.png  512x512
```

Names: display name at most 30 characters, kebab-case `name`, no "Plugin" or "MCP"
in names, no pricing or promotion anywhere in metadata.
