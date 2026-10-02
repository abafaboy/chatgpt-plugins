"""GPT to Plugin Packager: turn a custom GPT's configuration into a portable plugin
package, and check plugin packages against OpenAI's published packaging rules.

All logic is in rules.py; this file only exposes it as MCP tools.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from mcp.server.apps import Apps, ResourceCsp
from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult

from plugkit import READ_ONLY, error, result, tracked, widget_html

from . import rules
from .widget import BODY, EXTRA_CSS, SCRIPT

PLUGIN = "gpt-to-plugin"
WIDGET = "ui://gpt-to-plugin/card.html"
MAX_FILES = 200
MAX_PATH = 300
MAX_CONTENT = 300_000
MAX_TOTAL = 8_000_000  # all files together, characters

Severity = Literal["error", "warning"]


class Issue(BaseModel):
    rule_id: str
    severity: Severity
    path: str
    message: str
    source_url: str


class PackageFile(BaseModel):
    path: Annotated[str, Field(description="Path inside the package, e.g. plugin.json or skills/x/SKILL.md.",
                               min_length=1, max_length=MAX_PATH)]
    content: Annotated[str, Field(description="The file's full text.", max_length=MAX_CONTENT)]


class BuildOut(BaseModel):
    kind: Literal["build"]
    slug: str
    files: list[PackageFile]
    converted: list[str]
    manual_steps: list[str]
    ok: bool
    errors: int
    warnings: int
    file_count: int
    skills: list[str]
    issues: list[Issue]


class ValidateOut(BaseModel):
    kind: Literal["validate"]
    ok: bool
    errors: int
    warnings: int
    file_count: int
    skills: list[str]
    issues: list[Issue]


class RuleRow(BaseModel):
    rule_id: str
    severity: Severity
    checks: str
    source_url: str


class RulesOut(BaseModel):
    kind: Literal["rules"]
    rules: list[RuleRow]


# Tools and the widget are registered on `apps` first; the server is built at the
# bottom of this file because MCPServer reads an extension's tools when constructed.
apps = Apps()


def _issue_lines(issues: list[dict]) -> list[str]:
    return [f"{i['severity'].upper()} {i['rule_id']} {i['path']}: {i['message']}" for i in issues]


def _summary(report: dict) -> str:
    if report["ok"]:
        head = "Ready: no errors"
    else:
        head = f"Fix {report['errors']} error{'s' if report['errors'] != 1 else ''}"
    return f"{head}, {report['warnings']} warning{'s' if report['warnings'] != 1 else ''} " \
           f"({report['file_count']} files, {len(report['skills'])} skill(s))."


@apps.tool(
    resource_uri=WIDGET,
    name="build_plugin_from_gpt",
    title="Build a plugin package from a GPT",
    description=(
        "Turn a custom GPT's configuration (name, description, instructions, conversation starters, "
        "knowledge file names, Action names) into a portable plugin package: plugin.json, a skill whose "
        "SKILL.md holds the instructions verbatim, a README with the manual steps that remain, and an "
        "mcp.json with placeholder servers only if the GPT had Actions. Returns every file's content and a "
        "validation report. Knowledge files and Actions are not converted: they are listed as manual steps."
    ),
    annotations=READ_ONLY,
    meta={"openai/toolInvocation/invoking": "Packaging…", "openai/toolInvocation/invoked": "Packaged"},
)
@tracked(PLUGIN)
def build_plugin_from_gpt(
    display_name: Annotated[str, Field(description="The GPT's name; becomes the plugin's display name "
                                       "(at most 30 characters).", min_length=1, max_length=30)],
    description: Annotated[str, Field(description="The GPT's description.", min_length=1, max_length=500)],
    instructions: Annotated[str, Field(description="The GPT's full instructions, pasted as they are.",
                                       min_length=1, max_length=50_000)],
    conversation_starters: Annotated[
        list[Annotated[str, Field(max_length=500)]],
        Field(description="The GPT's conversation starters.", max_length=10)] = [],
    knowledge_file_names: Annotated[
        list[Annotated[str, Field(max_length=255)]],
        Field(description="File names of the GPT's knowledge files (names only, not contents).", max_length=50)] = [],
    action_names: Annotated[
        list[Annotated[str, Field(max_length=100)]],
        Field(description="Names of the GPT's Actions (custom API connections).", max_length=20)] = [],
    author_name: Annotated[str | None, Field(description="Author or team name for plugin.json.",
                                             max_length=120)] = None,
) -> Annotated[CallToolResult, BuildOut]:
    if not display_name.strip() or not description.strip() or not instructions.strip():
        return error("display_name, description and instructions must not be blank.")
    pkg = rules.build_package(display_name, description, instructions, conversation_starters,
                              knowledge_file_names, action_names, author_name)
    lines = [f"Built package \"{pkg['slug']}\": " + ", ".join(f["path"] for f in pkg["files"]) + ".",
             _summary(pkg), *_issue_lines(pkg["issues"]),
             "Manual steps:", *[f"- {m}" for m in pkg["manual_steps"]]]
    return result("\n".join(lines), {"kind": "build", **pkg})


@apps.tool(
    resource_uri=WIDGET,
    name="validate_plugin_package",
    title="Check a plugin package",
    description=(
        "Check a plugin folder (plugin.json, skills/*/SKILL.md, mcp.json and any other files) against OpenAI's "
        "published packaging rules and guidelines before submitting. Pass every file's path and text. Returns "
        "errors and warnings, each with the rule and the documentation page it comes from."
    ),
    annotations=READ_ONLY,
    meta={"openai/toolInvocation/invoking": "Checking…", "openai/toolInvocation/invoked": "Checked"},
)
@tracked(PLUGIN)
def validate_plugin_package(
    files: Annotated[list[PackageFile], Field(description="Every file in the package.", min_length=1,
                                              max_length=MAX_FILES)],
) -> Annotated[CallToolResult, ValidateOut]:
    total = sum(len(f.content) for f in files)
    if total > MAX_TOTAL:
        return error(f"The files total {total:,} characters; the limit is {MAX_TOTAL:,}. "
                     "Leave out large reference files; they are not checked beyond their count.")
    report = rules.validate([f.model_dump() for f in files])
    return result("\n".join([_summary(report), *_issue_lines(report["issues"])]), {"kind": "validate", **report})


@apps.tool(
    resource_uri=WIDGET,
    name="explain_plugin_rules",
    title="List the plugin package rules",
    description=(
        "List every rule validate_plugin_package checks: id, severity, what it checks and the OpenAI "
        "documentation page it comes from."
    ),
    annotations=READ_ONLY,
)
@tracked(PLUGIN)
def explain_plugin_rules() -> Annotated[CallToolResult, RulesOut]:
    table = rules.rule_table()
    text = "\n".join(f"{r['rule_id']} ({r['severity']}): {r['checks']} {r['source_url']}" for r in table)
    return result(text, {"kind": "rules", "rules": table})


apps.add_html_resource(
    WIDGET,
    widget_html("GPT to Plugin Packager", BODY, SCRIPT, EXTRA_CSS),
    title="GPT to Plugin Packager card",
    description="Shows a generated plugin package's files, a package check report, or the rule table.",
    csp=ResourceCsp(connect_domains=[], resource_domains=[]),
    prefers_border=True,
)

mcp = MCPServer(
    "gpt-to-plugin",
    title="GPT to Plugin Packager",
    version="0.1.0",
    instructions=(
        "Converts a custom GPT's configuration into a portable plugin package (plugin.json, a skill with the "
        "GPT's instructions, a README of manual steps, and mcp.json only when the GPT had Actions), and checks "
        "plugin packages against OpenAI's published packaging rules. Knowledge files and Actions cannot be "
        "converted automatically; say so plainly and point to the manual steps. ChatGPT's own \"Migrate to "
        "plugin\" button is the quickest path inside ChatGPT; these tools give a copy the user controls and a "
        "check before submission."
    ),
    extensions=[apps],
)
