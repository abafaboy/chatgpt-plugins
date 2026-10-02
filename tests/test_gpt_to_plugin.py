import json
from pathlib import Path

import pytest
from mcp import Client

import gpt_to_plugin.server as srv
from gpt_to_plugin import rules

pytestmark = pytest.mark.anyio

PLUGINS_DIR = Path(__file__).resolve().parent.parent / "plugins"

GPT = {
    "display_name": "Sales Coach PRO",
    "description": "Coaches sales reps through cold calls and objection handling. Gives feedback on scripts.",
    "instructions": "You are a sales coach.\n---\nAlways ask for the product first.\n\n# Rules\n- Be brief.",
    "conversation_starters": ["Review my cold call script", "How do I handle 'too expensive'?"],
}


@pytest.fixture
async def client():
    async with Client(srv.mcp, mode="legacy") as c:
        yield c


def _manifest(**over):
    m = {
        "$schema": rules.PLUGIN_SCHEMA,
        "name": "good-tool",
        "version": "1.0.0",
        "description": "Does one clear thing.",
        "skills": "./skills/",
        "extensions": {"com.openai": {"interface": {"displayName": "Good Tool", "category": "Productivity"}}},
    }
    m.update(over)
    return m


SKILL = "---\nname: good-tool\ndescription: Use when the user wants the good thing done.\n---\n\n# Body\n"


def _pkg(manifest=None, skill=SKILL, extra=None, raw_manifest=None):
    files = [{"path": "plugin.json", "content": raw_manifest if raw_manifest is not None
              else json.dumps(manifest if manifest is not None else _manifest())}]
    if skill is not None:
        files.append({"path": "skills/good-tool/SKILL.md", "content": skill})
    return files + (extra or [])


def _mcp(servers):
    return {"path": "mcp.json", "content": json.dumps({"$schema": rules.MCP_SCHEMA, "mcpServers": servers})}


def _iface(**fields):
    return {"com.openai": {"interface": {"displayName": "Good Tool", **fields}}}


BAD_PACKAGES = {
    "P001": [{"path": "skills/good-tool/SKILL.md", "content": SKILL}],
    "P002": _pkg(raw_manifest="{not json"),
    "P003": _pkg(manifest={k: v for k, v in _manifest().items() if k != "version"}),
    "P004": _pkg(manifest=_manifest(name="Good_Tool")),
    "P005": _pkg(manifest=_manifest(version="v1")),
    "P006": _pkg(manifest=_manifest(skills="skills/")),
    "P007": _pkg(manifest=_manifest(extensions=_iface(composerIcon="./assets/icon.png"))),
    "P008": _pkg(manifest=_manifest(extensions=_iface(displayName="A display name that is far too long"))),
    "P009": _pkg(manifest=_manifest(name="good-tool-mcp")),
    "P010": _pkg(manifest=_manifest(description="Start your free trial today, 20% off.")),
    "P011": _pkg(manifest=_manifest(author={"email": "team@example.com"})),
    "S001": _pkg(skill="# No frontmatter here\n"),
    "S002": _pkg(skill="---\nname: good-tool\n---\nbody\n"),
    "S003": _pkg(skill=SKILL.replace("name: good-tool", "name: other-name")),
    "S004": _pkg(skill=SKILL + "x" * (256 * 1024)),
    "S005": _pkg(extra=[{"path": f"skills/s{i}/SKILL.md", "content": SKILL.replace("good-tool", f"s{i}")}
                        for i in range(5)]),
    "S006": _pkg(extra=[{"path": f"skills/good-tool/references/r{i}.md", "content": "r"} for i in range(100)]),
    "S007": _pkg(extra=[{"path": "skills/notes.md", "content": "loose"}]),
    "M001": _pkg(extra=[{"path": "mcp.json", "content": "[1, 2"}]),
    "M002": _pkg(extra=[_mcp({"srv": {"type": "sse", "url": "https://api.acme.io/mcp"}})]),
    "M003": _pkg(extra=[_mcp({"srv": {"type": "streamable-http", "url": "http://api.acme.io/mcp"}})]),
    "M004": _pkg(extra=[_mcp({"srv": {"type": "streamable-http", "url": "https://HOST/x/mcp"}})]),
}


def test_good_package_is_clean():
    rep = rules.validate(_pkg(extra=[_mcp({"srv": {"type": "streamable-http", "url": "https://api.acme.io/mcp"}})]))
    assert rep["issues"] == [] and rep["ok"] is True and rep["skills"] == ["good-tool"]


def test_every_rule_has_a_bad_package():
    assert set(BAD_PACKAGES) == set(rules.RULES)


@pytest.mark.parametrize("rule_id", sorted(BAD_PACKAGES))
def test_rule_triggers(rule_id):
    rep = rules.validate(BAD_PACKAGES[rule_id])
    ids = {i["rule_id"] for i in rep["issues"]}
    assert rule_id in ids, rep["issues"]
    hit = next(i for i in rep["issues"] if i["rule_id"] == rule_id)
    assert hit["severity"] == rules.RULES[rule_id].severity
    assert hit["source_url"].startswith("https://developers.openai.com/plugins/")
    assert rep["ok"] is (rep["errors"] == 0)
    if rules.RULES[rule_id].severity == "error":
        assert rep["ok"] is False


def test_wrapping_folder_is_ignored():
    files = [{"path": "my-plugin/" + f["path"], "content": f["content"]} for f in _pkg()]
    assert rules.validate(files)["issues"] == []


@pytest.mark.parametrize("text,expected", [
    ("---\nname: a\ndescription: \"quoted: with colon\"\n---\n", "quoted: with colon"),
    ("---\nname: a\ndescription: 'it''s fine'\n---\n", "it's fine"),
    ("---\nname: a\ndescription: >\n  folded\n  text\n---\n", "folded text"),
    ("---\nname: a\ndescription: |\n  line one\n  line two\n---\n", "line one\nline two"),
    ("---\r\nname: a\r\ndescription: plain # comment\r\n---\r\n", "plain"),
])
def test_frontmatter_parser(text, expected):
    assert rules.parse_frontmatter(text) == {"name": "a", "description": expected}


def test_frontmatter_unclosed_is_none():
    assert rules.parse_frontmatter("---\nname: a\n") is None


@pytest.mark.parametrize("name,slug", [
    ("Sales Coach PRO", "sales-coach-pro"),
    ("Мой Помощник 2!", "moy-pomoshchnik-2"),
    ("Oʻzbek tili yordamchisi", "ozbek-tili-yordamchisi"),
    ("Café Menu Plugin", "cafe-menu"),
    ("学习助手", rules.FALLBACK_SLUG),
    ("!!!", rules.FALLBACK_SLUG),
])
def test_slugify(name, slug):
    assert rules.slugify(name) == slug
    assert rules.KEBAB.match(rules.slugify(name))


def test_slug_is_capped_at_64():
    s = rules.slugify("word " * 40)
    assert len(s) <= 64 and rules.KEBAB.match(s)


async def test_tools_are_read_only_and_bound_to_widget(client):
    tools = (await client.list_tools()).tools
    assert {t.name for t in tools} == {"build_plugin_from_gpt", "validate_plugin_package", "explain_plugin_rules"}
    for t in tools:
        a = t.annotations
        assert a.read_only_hint is True and a.destructive_hint is False and a.open_world_hint is False
        assert t.meta["ui"]["resourceUri"] == srv.WIDGET
        assert t.output_schema is not None, t.name
        assert t.title


async def test_build_produces_a_valid_package(client):
    r = await client.call_tool("build_plugin_from_gpt", {**GPT, "knowledge_file_names": ["price list.pdf"],
                                                        "author_name": "Acme Sales"})
    assert not r.is_error
    sc = r.structured_content
    paths = [f["path"] for f in sc["files"]]
    assert paths == ["plugin.json", "README.md", "skills/sales-coach-pro/SKILL.md"]
    assert sc["errors"] == 0 and sc["ok"] is True
    # The report is the validator's verdict on the same files.
    assert rules.validate(sc["files"])["issues"] == sc["issues"]
    files = {f["path"]: f["content"] for f in sc["files"]}
    manifest = json.loads(files["plugin.json"])
    assert manifest["name"] == "sales-coach-pro" and manifest["version"] == "1.0.0"
    assert manifest["skills"] == "./skills/" and manifest["author"] == {"name": "Acme Sales"}
    iface = manifest["extensions"]["com.openai"]["interface"]
    assert iface == {"displayName": "Sales Coach PRO", "category": "Productivity"}
    skill = files["skills/sales-coach-pro/SKILL.md"]
    fm = rules.parse_frontmatter(skill)
    assert fm["name"] == "sales-coach-pro"
    assert fm["description"].startswith("Coaches sales reps through cold calls and objection handling.")
    assert "Use when" in fm["description"]
    assert GPT["instructions"] in skill  # verbatim
    assert "- How do I handle 'too expensive'?" in skill
    readme = files["README.md"]
    assert "price list.pdf" in readme and "skills/sales-coach-pro/references/" in readme
    assert "assets/" in readme and "Migrate to plugin" in readme
    assert "Ready: no errors" in r.content[0].text


async def test_mcp_json_only_when_actions_given(client):
    r = await client.call_tool("build_plugin_from_gpt", GPT)
    assert "mcp.json" not in [f["path"] for f in r.structured_content["files"]]
    r = await client.call_tool("build_plugin_from_gpt", {**GPT, "action_names": ["CRM lookup", "Send quote"]})
    sc = r.structured_content
    files = {f["path"]: f["content"] for f in sc["files"]}
    servers = json.loads(files["mcp.json"])["mcpServers"]
    assert set(servers) == {"crm-lookup", "send-quote"}
    assert all(s == {"type": "streamable-http", "url": rules.PLACEHOLDER_MCP_URL} for s in servers.values())
    assert sc["errors"] == 0 and {i["rule_id"] for i in sc["issues"]} == {"M004"}
    assert "CRM lookup" in files["README.md"]


async def test_build_with_cyrillic_name(client):
    r = await client.call_tool("build_plugin_from_gpt", {**GPT, "display_name": "Мой Помощник 2!"})
    sc = r.structured_content
    assert sc["slug"] == "moy-pomoshchnik-2" and sc["errors"] == 0
    assert json.loads(sc["files"][0]["content"])["extensions"]["com.openai"]["interface"]["displayName"] \
        == "Мой Помощник 2!"


@pytest.mark.parametrize("args", [
    {**GPT, "display_name": "x" * 31},
    {**GPT, "description": "x" * 501},
    {**GPT, "instructions": "x" * 50_001},
    {**GPT, "conversation_starters": ["s"] * 11},
    {**GPT, "action_names": ["a"] * 21},
    {**GPT, "instructions": "   "},
])
async def test_oversized_or_blank_build_input_is_refused(client, args):
    r = await client.call_tool("build_plugin_from_gpt", args)
    assert r.is_error


async def test_validate_tool(client):
    r = await client.call_tool("validate_plugin_package", {"files": BAD_PACKAGES["P004"]})
    assert not r.is_error
    sc = r.structured_content
    assert sc["ok"] is False and sc["errors"] == 1
    assert r.content[0].text.startswith("Fix 1 error")
    assert "ERROR P004 plugin.json:" in r.content[0].text


@pytest.mark.parametrize("files", [
    [{"path": "a", "content": "x"}] * 201,
    [{"path": "p" * 301, "content": "x"}],
    [{"path": "plugin.json", "content": "x" * 300_001}],
    [],
])
async def test_oversized_validate_input_is_refused(client, files):
    r = await client.call_tool("validate_plugin_package", {"files": files})
    assert r.is_error


async def test_total_size_cap(client, monkeypatch):
    monkeypatch.setattr(srv, "MAX_TOTAL", 10)
    r = await client.call_tool("validate_plugin_package", {"files": [{"path": "plugin.json", "content": "x" * 11}]})
    assert r.is_error and "limit" in r.content[0].text


async def test_explain_rules(client):
    r = await client.call_tool("explain_plugin_rules", {})
    rows = r.structured_content["rules"]
    assert [x["rule_id"] for x in rows] == list(rules.RULES)
    assert all(x["source_url"].startswith("https://developers.openai.com/plugins/") for x in rows)


async def test_widget_resource(client):
    rr = await client.read_resource(srv.WIDGET)
    html = rr.contents[0].text
    assert rr.contents[0].mime_type == "text/html;profile=mcp-app"
    assert "plugkit" in html and "ui/notifications/tool-result" in html
    assert "innerHTML" not in srv.SCRIPT


async def test_usage_is_logged_without_content(client, usage_log):
    await client.call_tool("build_plugin_from_gpt", {**GPT, "instructions": "secret instruction text"})
    ev = json.loads(usage_log.read_text().splitlines()[-1])
    assert ev["plugin"] == "gpt-to-plugin" and ev["tool"] == "build_plugin_from_gpt" and ev["ok"] is True
    log = usage_log.read_text()
    assert "secret" not in log and "Sales Coach" not in log


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""  # binary (icons): only its presence matters


@pytest.mark.parametrize("plugin_dir", sorted(d for d in PLUGINS_DIR.iterdir() if d.is_dir()), ids=lambda d: d.name)
def test_repo_plugins_validate(plugin_dir):
    if not (plugin_dir / "plugin.json").exists():
        pytest.skip(f"plugins/{plugin_dir.name} has no plugin.json yet")
    files = [{"path": p.relative_to(plugin_dir).as_posix(), "content": _read(p)}
             for p in sorted(plugin_dir.rglob("*")) if p.is_file()]
    rep = rules.validate(files)
    # Icons are added later (P007); warnings such as the HOST placeholder are expected.
    blocking = [i for i in rep["issues"] if i["severity"] == "error" and i["rule_id"] != "P007"]
    assert not blocking, blocking


def test_own_package_exists():
    assert (PLUGINS_DIR / "gpt-to-plugin" / "plugin.json").exists()
