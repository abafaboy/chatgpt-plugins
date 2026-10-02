"""Plugin package rules and the GPT-to-package builder. Pure Python, no MCP imports.

Every rule cites the OpenAI page it comes from. Where the docs show a practice in an
example but do not state it as a rule, the rule's text says so and it is a warning.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

PLUGINS_URL = "https://developers.openai.com/plugins/build/plugins"
SKILLS_URL = "https://developers.openai.com/plugins/build/skills"
MCP_URL = "https://developers.openai.com/plugins/build/mcp-server"
GUIDELINES_URL = "https://developers.openai.com/plugins/plugin-guidelines"
SUBMISSION_URL = "https://developers.openai.com/plugins/deploy/submission"

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
PLACEHOLDER_MCP_URL = "https://YOUR-SERVER.example/mcp"

SKILL_MD_MAX_BYTES = 256 * 1024
MAX_SKILLS = 5
MAX_FILES_PER_SKILL = 100
LISTING_LIMITS = {"displayName": 30, "shortDescription": 30, "longDescription": 4000}


@dataclass(frozen=True)
class Rule:
    rule_id: str
    severity: str  # "error" | "warning"
    checks: str
    source_url: str


RULES: dict[str, Rule] = {r.rule_id: r for r in [
    Rule("P001", "error", "plugin.json exists at the package root.", PLUGINS_URL),
    Rule("P002", "error", "plugin.json is valid JSON and a JSON object.", PLUGINS_URL),
    Rule("P003", "error", "plugin.json has non-empty name, version and description at the root.", PLUGINS_URL),
    Rule("P004", "error", "name is kebab-case (lowercase letters, digits, single hyphens).", PLUGINS_URL),
    Rule("P005", "warning", "version looks like semantic versioning (e.g. 1.0.0). The docs' examples use it; "
         "they do not state it as a rule.", PLUGINS_URL),
    Rule("P006", "error", "Manifest paths (skills, apps, hooks, interface composerIcon/logo/screenshots) are "
         "relative, start with ./ and stay inside the package.", PLUGINS_URL),
    Rule("P007", "warning", "Files and folders the manifest points to are in the package (icons may be added later).",
         PLUGINS_URL),
    Rule("P008", "error", "Listing fields fit: displayName and shortDescription at most 30 characters, "
         "longDescription at most 4000.", SUBMISSION_URL),
    Rule("P009", "warning", "name and displayName do not have MCP, MCP Server or Plugin appended as a word.",
         GUIDELINES_URL),
    Rule("P010", "warning", "description and listing text do not advertise pricing, subscriptions, free trials, "
         "discounts or promotions.", GUIDELINES_URL),
    Rule("P011", "warning", "author, when present, is an object with a name.", SUBMISSION_URL),
    Rule("S001", "error", "Every SKILL.md starts with YAML frontmatter between --- lines.", SKILLS_URL),
    Rule("S002", "error", "SKILL.md frontmatter has a non-empty name and description.", SKILLS_URL),
    Rule("S003", "warning", "The skill's name matches its folder name. The docs' examples do this; they do not "
         "state it as a rule.", SKILLS_URL),
    Rule("S004", "error", "SKILL.md is at most 256 KiB (limit for skills imported from an MCP server).", MCP_URL),
    Rule("S005", "warning", "At most 5 skills (limit for skills imported from an MCP server per scan).", MCP_URL),
    Rule("S006", "warning", "At most 100 files in one skill (limit for skills imported from an MCP server).", MCP_URL),
    Rule("S007", "warning", "Skill files sit inside skills/<skill-name>/ next to a SKILL.md; skills are discovered "
         "only under the root skills/ folder.", PLUGINS_URL),
    Rule("M001", "error", "mcp.json is valid JSON with an mcpServers object.", PLUGINS_URL),
    Rule("M002", "warning", "Each MCP server has type \"streamable-http\" (the type in OpenAI's example).", PLUGINS_URL),
    Rule("M003", "error", "Each remote MCP server has an https:// URL (public HTTPS endpoint required).", MCP_URL),
    Rule("M004", "warning", "MCP server URLs are not placeholders or local (example., YOUR-, HOST, localhost).",
         MCP_URL),
]}


def rule_table() -> list[dict[str, str]]:
    return [asdict(r) for r in RULES.values()]


def _issue(rule_id: str, path: str, message: str) -> dict[str, str]:
    r = RULES[rule_id]
    return {"rule_id": rule_id, "severity": r.severity, "path": path, "message": message, "source_url": r.source_url}


# ---------------------------------------------------------------- frontmatter

def parse_frontmatter(text: str) -> dict[str, str] | None:
    """Top-level scalar keys of a YAML frontmatter block, or None if there is no block.

    Handles plain, single-quoted, double-quoted and block (| >) scalars. Nested
    mappings and lists are kept as their raw indented text. Enough for name and
    description; not a YAML implementation.
    """
    lines = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() in ("---", "..."))
    except StopIteration:
        return None
    block = lines[1:end]
    out: dict[str, str] = {}
    i = 0
    key_re = re.compile(r"^([A-Za-z0-9_.-]+)\s*:(?:\s+(.*))?$|^([A-Za-z0-9_.-]+)\s*:$")
    while i < len(block):
        line = block[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#") or line[:1] in (" ", "\t"):
            continue
        m = key_re.match(line.rstrip())
        if not m:
            continue
        key = m.group(1) or m.group(3)
        raw = (m.group(2) or "").strip()
        # Indented continuation lines belong to this key.
        cont: list[str] = []
        while i < len(block) and (not block[i].strip() or block[i][:1] in (" ", "\t")):
            cont.append(block[i])
            i += 1
        while cont and not cont[-1].strip():
            cont.pop()
        if raw[:1] in ("|", ">"):
            indent = min((len(c) - len(c.lstrip()) for c in cont if c.strip()), default=0)
            body = [c[indent:] for c in cont]
            out[key] = ("\n" if raw[0] == "|" else " ").join(body).strip()
        elif raw.startswith('"'):
            try:
                out[key] = str(json.loads(raw))
            except ValueError:
                out[key] = raw.strip('"')
        elif raw.startswith("'"):
            out[key] = raw[1:-1].replace("''", "'") if raw.endswith("'") and len(raw) > 1 else raw.strip("'")
        elif raw:
            value = re.split(r"\s+#", raw, maxsplit=1)[0].strip()
            extra = " ".join(c.strip() for c in cont if c.strip())  # folded plain scalar
            out[key] = (value + " " + extra).strip() if extra else value
        else:
            out[key] = "\n".join(cont).strip()
    return out


# ---------------------------------------------------------------- validation

KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
PROMO = [
    (re.compile(r"free\s+trial", re.I), "free trial"),
    (re.compile(r"\bdiscount", re.I), "discount"),
    (re.compile(r"\bsubscri(?:be|bes|ption|ptions)\b", re.I), "subscribe/subscription"),
    (re.compile(r"\bpric(?:e|es|ing)\b", re.I), "price"),
    (re.compile(r"\$"), "$"),
    (re.compile(r"%\s*off\b", re.I), "% off"),
    (re.compile(r"\bpromo", re.I), "promo"),
]
SUFFIX_WORDS = re.compile(r"\b(mcp|plugin|plugins)\b", re.I)


def _norm_path(path: str) -> str:
    p = path.replace("\\", "/").strip()
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def _normalise(files: list[dict[str, str]]) -> dict[str, str]:
    """Map of package-relative path -> content. A single wrapping folder is removed."""
    norm = {}
    for f in files:
        p = _norm_path(f["path"])
        if p:
            norm[p] = f["content"]
    if "plugin.json" not in norm and norm:
        tops = {p.split("/", 1)[0] for p in norm}
        if len(tops) == 1 and all("/" in p for p in norm):
            top = tops.pop() + "/"
            if top + "plugin.json" in norm:
                norm = {p[len(top):]: c for p, c in norm.items()}
    return norm


def _manifest_paths(manifest: dict[str, Any]) -> list[tuple[str, Any]]:
    """(field label, value) for every manifest field that holds a package path."""
    found: list[tuple[str, Any]] = []
    for key in ("skills", "apps", "hooks"):
        if key in manifest:
            found.append((key, manifest[key]))
    ext = manifest.get("extensions")
    oa = ext.get("com.openai") if isinstance(ext, dict) else None
    if isinstance(oa, dict):
        for key in ("apps", "hooks"):
            if key in oa:
                found.append((f"extensions.com.openai.{key}", oa[key]))
        interface = oa.get("interface")
        if isinstance(interface, dict):
            for key in ("composerIcon", "logo", "screenshots"):
                if key in interface:
                    found.append((f"extensions.com.openai.interface.{key}", interface[key]))
    flat: list[tuple[str, Any]] = []
    for label, value in found:
        if isinstance(value, list):
            flat += [(f"{label}[{i}]", v) for i, v in enumerate(value)]
        else:
            flat.append((label, value))
    return flat


def _interface(manifest: dict[str, Any]) -> dict[str, Any]:
    ext = manifest.get("extensions")
    oa = ext.get("com.openai") if isinstance(ext, dict) else None
    iface = oa.get("interface") if isinstance(oa, dict) else None
    return iface if isinstance(iface, dict) else {}


def _check_manifest(pkg: dict[str, str]) -> tuple[list[dict[str, str]], dict[str, Any] | None]:
    issues: list[dict[str, str]] = []
    if "plugin.json" not in pkg:
        return [_issue("P001", "plugin.json", "No plugin.json at the package root; every plugin needs one.")], None
    try:
        manifest = json.loads(pkg["plugin.json"])
    except ValueError as exc:
        return [_issue("P002", "plugin.json", f"plugin.json is not valid JSON: {exc}.")], None
    if not isinstance(manifest, dict):
        return [_issue("P002", "plugin.json", "plugin.json must be a JSON object.")], None

    missing = [k for k in ("name", "version", "description")
               if not isinstance(manifest.get(k), str) or not manifest[k].strip()]
    if missing:
        issues.append(_issue("P003", "plugin.json", f"Missing or empty at the root: {', '.join(missing)}."))

    name = manifest.get("name")
    if isinstance(name, str) and name.strip() and not KEBAB.match(name):
        issues.append(_issue("P004", "plugin.json", f"name \"{name}\" is not kebab-case (e.g. my-plugin)."))
    version = manifest.get("version")
    if isinstance(version, str) and version.strip() and not SEMVER.match(version):
        issues.append(_issue("P005", "plugin.json", f"version \"{version}\" is not semantic versioning (e.g. 1.0.0)."))

    for label, value in _manifest_paths(manifest):
        if not isinstance(value, str) or not value.startswith("./"):
            issues.append(_issue("P006", "plugin.json", f"{label} must be a relative path starting with ./ "
                                 f"(got {json.dumps(value, ensure_ascii=False)[:80]})."))
            continue
        if ".." in value.split("/"):
            issues.append(_issue("P006", "plugin.json", f"{label} ({value}) points outside the package."))
            continue
        target = _norm_path(value)
        present = any(p.startswith(target.rstrip("/") + "/") for p in pkg) if (
            value.endswith("/") or target in ("", "skills", "hooks")) else target in pkg
        if not present and target:
            issues.append(_issue("P007", "plugin.json", f"{label} points to {value}, which is not in the package."))

    iface = _interface(manifest)
    for key, limit in LISTING_LIMITS.items():
        val = iface.get(key)
        if isinstance(val, str) and len(val) > limit:
            issues.append(_issue("P008", "plugin.json",
                                 f"{key} is {len(val)} characters; the listing allows at most {limit}."))

    for label, val in (("name", name), ("displayName", iface.get("displayName"))):
        if isinstance(val, str):
            words = sorted({w.lower() for w in SUFFIX_WORDS.findall(val.replace("-", " "))})
            if words:
                issues.append(_issue("P009", "plugin.json",
                                     f"{label} \"{val}\" contains {', '.join(words).upper()} as a word; the guidelines "
                                     "say not to append MCP, MCP Server or Plugin to a name. Fine only if it describes "
                                     "what the plugin does."))

    for label, val in (("description", manifest.get("description")), *(
            (k, iface.get(k)) for k in ("displayName", "shortDescription", "longDescription"))):
        if isinstance(val, str):
            hits = [word for rx, word in PROMO if rx.search(val)]
            if hits:
                issues.append(_issue("P010", "plugin.json",
                                     f"{label} mentions {', '.join(hits)}; metadata must not advertise pricing, "
                                     "subscriptions, free trials, discounts or promotions."))

    if "author" in manifest:
        author = manifest["author"]
        if not isinstance(author, dict) or not isinstance(author.get("name"), str) or not author["name"].strip():
            issues.append(_issue("P011", "plugin.json", "author is present but has no name."))
    return issues, manifest


def _check_skills(pkg: dict[str, str]) -> tuple[list[dict[str, str]], list[str]]:
    issues: list[dict[str, str]] = []
    skill_dirs = sorted({p.split("/")[1] for p in pkg
                         if p.startswith("skills/") and p.count("/") == 2 and p.endswith("/SKILL.md")})
    for path in sorted(pkg):
        parts = path.split("/")
        if parts[0] == "skills":
            if len(parts) < 3 or parts[1] not in skill_dirs:
                issues.append(_issue("S007", path, "Not inside a skill folder: skill files belong in "
                                     "skills/<skill-name>/ next to its SKILL.md."))
        elif parts[-1] == "SKILL.md":
            issues.append(_issue("S007", path, "SKILL.md outside skills/: skills are discovered only under "
                                 "the root skills/<skill-name>/ folder."))

    for folder in skill_dirs:
        path = f"skills/{folder}/SKILL.md"
        content = pkg[path]
        size = len(content.encode("utf-8"))
        if size > SKILL_MD_MAX_BYTES:
            issues.append(_issue("S004", path, f"SKILL.md is {size:,} bytes; the limit is 256 KiB "
                                 f"({SKILL_MD_MAX_BYTES:,} bytes). Move detail into references/."))
        fm = parse_frontmatter(content)
        if fm is None:
            issues.append(_issue("S001", path, "No YAML frontmatter: SKILL.md must start with ---, then name: and "
                                 "description:, then ---."))
        else:
            missing = [k for k in ("name", "description") if not fm.get(k, "").strip()]
            if missing:
                issues.append(_issue("S002", path, f"Frontmatter is missing {' and '.join(missing)}."))
            if fm.get("name", "").strip() and fm["name"].strip() != folder:
                issues.append(_issue("S003", path, f"Skill name \"{fm['name'].strip()}\" differs from its folder "
                                     f"\"{folder}\"."))
        count = sum(1 for p in pkg if p.startswith(f"skills/{folder}/"))
        if count > MAX_FILES_PER_SKILL:
            issues.append(_issue("S006", f"skills/{folder}/", f"{count} files in this skill; MCP skill import "
                                 f"takes at most {MAX_FILES_PER_SKILL}."))
    if len(skill_dirs) > MAX_SKILLS:
        issues.append(_issue("S005", "skills/", f"{len(skill_dirs)} skills; MCP skill import takes at most "
                             f"{MAX_SKILLS} per scan."))
    return issues, skill_dirs


def _placeholder(url: str, host: str) -> bool:
    h = host.lower()
    return (
        "example." in h or h.endswith(".example") or "your-" in h or h in ("localhost", "127.0.0.1", "0.0.0.0", "::1")
        or host == "HOST" or h.startswith("host:") or "<" in url or "{" in url
    )


def _check_mcp(pkg: dict[str, str]) -> list[dict[str, str]]:
    if "mcp.json" not in pkg:
        return []
    try:
        data = json.loads(pkg["mcp.json"])
    except ValueError as exc:
        return [_issue("M001", "mcp.json", f"mcp.json is not valid JSON: {exc}.")]
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, dict):
        return [_issue("M001", "mcp.json", "mcp.json needs an \"mcpServers\" object.")]
    issues = []
    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            issues.append(_issue("M001", "mcp.json", f"Server \"{name}\" must be an object."))
            continue
        kind = cfg.get("type")
        if kind != "streamable-http":
            issues.append(_issue("M002", "mcp.json", f"Server \"{name}\" has type {json.dumps(kind)}; "
                                 "OpenAI's example uses \"streamable-http\"."))
        url = cfg.get("url")
        if url is None and kind != "streamable-http":
            continue  # a local (stdio) server: M002 already says it.
        if not isinstance(url, str) or urlparse(url).scheme != "https" or not urlparse(url).netloc:
            issues.append(_issue("M003", "mcp.json", f"Server \"{name}\" needs a public https:// URL "
                                 f"(got {json.dumps(url, ensure_ascii=False)[:80]})."))
            continue
        host = urlparse(url).netloc
        if _placeholder(url, host):
            issues.append(_issue("M004", "mcp.json", f"Server \"{name}\" URL {url} looks like a placeholder or a "
                                 "local address; put the deployed server's URL here."))
    return issues


def validate(files: list[dict[str, str]]) -> dict[str, Any]:
    pkg = _normalise(files)
    issues, _ = _check_manifest(pkg)
    skill_issues, skills = _check_skills(pkg)
    issues += skill_issues + _check_mcp(pkg)
    order = list(RULES)
    issues.sort(key=lambda i: (i["severity"] != "error", order.index(i["rule_id"]), i["path"]))
    errors = sum(1 for i in issues if i["severity"] == "error")
    return {
        "ok": errors == 0,
        "errors": errors,
        "warnings": len(issues) - errors,
        "file_count": len(pkg),
        "skills": skills,
        "issues": issues,
    }


# ---------------------------------------------------------------- builder

_CYR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
    # Uzbek, Kazakh, Ukrainian and other Cyrillic letters
    "ў": "o", "қ": "q", "ғ": "g", "ҳ": "h", "ә": "a", "ө": "o", "ү": "u", "ұ": "u", "і": "i", "ң": "ng",
    "һ": "h", "ї": "yi", "є": "ye", "ґ": "g", "ј": "j", "љ": "lj", "њ": "nj", "ћ": "c", "џ": "dz", "ђ": "d",
}
SLUG_MAX = 64
FALLBACK_SLUG = "converted-gpt"


def slugify(display_name: str) -> str:
    """Kebab-case ASCII name: Cyrillic transliterated, accents stripped, other scripts dropped.

    MCP and Plugin words are dropped (the guidelines say not to append them); falls back
    to a fixed name when nothing usable is left.
    """
    text = "".join(_CYR.get(ch, ch) for ch in display_name.lower())
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    words = [w for w in re.split(r"[^a-z0-9]+", text) if w and w not in ("mcp", "plugin", "plugins")]
    slug = "-".join(words)
    if len(slug) > SLUG_MAX:
        slug = slug[:SLUG_MAX]
        slug = slug.rsplit("-", 1)[0] if "-" in slug else slug
    return slug.strip("-") or FALLBACK_SLUG


def _one_line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def skill_description(display_name: str, description: str) -> str:
    """One or two sentences: what it does (from the GPT description) and when to use it."""
    desc = _one_line(description)
    sentences = re.split(r"(?<=[.!?])\s+", desc)
    what = sentences[0]
    if len(what) > 300:
        what = what[:300].rsplit(" ", 1)[0] + "…"
    if what and what[-1] not in ".!?…":
        what += "."
    when = f"Use when the user asks for what the \"{_one_line(display_name)}\" GPT was built to do."
    return f"{what} {when}".strip()


def _safe_file_name(name: str) -> str:
    base = name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    return base if base not in ("", ".", "..") else "file"


def build_package(
    display_name: str,
    description: str,
    instructions: str,
    conversation_starters: list[str] | None = None,
    knowledge_file_names: list[str] | None = None,
    action_names: list[str] | None = None,
    author_name: str | None = None,
) -> dict[str, Any]:
    starters = [_one_line(s) for s in (conversation_starters or []) if s.strip()]
    knowledge = [_safe_file_name(k) for k in (knowledge_file_names or []) if k.strip()]
    actions = [_one_line(a) for a in (action_names or []) if a.strip()]
    display = _one_line(display_name)
    slug = slugify(display)
    skill_dir = f"skills/{slug}"

    manifest: dict[str, Any] = {
        "$schema": PLUGIN_SCHEMA,
        "name": slug,
        "version": "1.0.0",
        "description": _one_line(description),
    }
    if author_name and author_name.strip():
        manifest["author"] = {"name": _one_line(author_name)}
    manifest["skills"] = "./skills/"
    manifest["extensions"] = {"com.openai": {"interface": {"displayName": display, "category": "Productivity"}}}

    fm_desc = skill_description(display, description)
    skill = [
        "---",
        f"name: {slug}",
        f"description: {json.dumps(fm_desc, ensure_ascii=False)}",
        "---",
        "",
        f"# {display}",
        "",
        "## Instructions",
        "",
        instructions.rstrip("\n"),
        "",
    ]
    if starters:
        skill += ["## Conversation starters", "", *[f"- {s}" for s in starters], ""]

    files = [
        {"path": "plugin.json", "content": json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"},
        {"path": f"{skill_dir}/SKILL.md", "content": "\n".join(skill)},
    ]

    servers: dict[str, dict[str, str]] = {}
    for action in actions:
        key = slugify(action) if slugify(action) != FALLBACK_SLUG else "action"
        base, n = key, 2
        while key in servers:
            key, n = f"{base}-{n}", n + 1
        servers[key] = {"type": "streamable-http", "url": PLACEHOLDER_MCP_URL}
    if servers:
        files.append({"path": "mcp.json", "content": json.dumps(
            {"$schema": MCP_SCHEMA, "mcpServers": servers}, ensure_ascii=False, indent=2) + "\n"})

    manual: list[str] = []
    for k in knowledge:
        manual.append(f"Copy the knowledge file \"{k}\" into {skill_dir}/references/ and mention it in "
                      f"{skill_dir}/SKILL.md (say when to read it).")
    for action, key in zip(actions, servers):
        manual.append(f"The Action \"{action}\" needs an MCP server: build or find one that does the same calls, "
                      f"deploy it at a public HTTPS URL and replace {PLACEHOLDER_MCP_URL} for \"{key}\" in mcp.json.")
    manual.append("Add icons to assets/ (square, at least 48x48 px; PNG, JPEG, WebP or SVG) and set "
                  "extensions.com.openai.interface.composerIcon and logo in plugin.json, e.g. \"./assets/icon.png\".")
    manual.append("If the GPT used ChatGPT capabilities (web search, image generation, code or data analysis), "
                  "check how the plugin will get them; this package does not record them.")
    manual.append("Test the package with OpenAI's plugin tools before submitting, and fill in the listing "
                  "(short description at most 30 characters, long description at most 4000).")

    auto = [
        f"Name \"{display}\" -> plugin.json name \"{slug}\" and displayName \"{display}\".",
        "Description -> plugin.json description and the skill's description.",
        f"Instructions -> {skill_dir}/SKILL.md, copied verbatim under \"Instructions\".",
    ]
    if starters:
        auto.append(f"{len(starters)} conversation starter(s) -> \"Conversation starters\" in SKILL.md.")
    if servers:
        auto.append(f"{len(servers)} Action(s) -> placeholder entries in mcp.json.")

    readme = [
        f"# {display}",
        "",
        "Converted from a custom GPT into a portable plugin package (plugin.json, skills/, "
        + ("mcp.json" if servers else "no mcp.json because the GPT had no Actions") + "). "
        "It is a plain folder you can keep in git. OpenAI's own \"Migrate to plugin\" "
        "button in ChatGPT is the other way to convert; this copy is one you control.",
        "",
        "## Converted automatically",
        "",
        *[f"- {a}" for a in auto],
        "",
        "## Still to do by hand",
        "",
        *[f"- [ ] {m}" for m in manual],
        "",
        "Rules: " + PLUGINS_URL + " · " + SKILLS_URL + " · " + GUIDELINES_URL,
        "",
    ]
    files.insert(1, {"path": "README.md", "content": "\n".join(readme)})

    report = validate(files)
    return {"slug": slug, "files": files, "converted": auto, "manual_steps": manual, **report}
