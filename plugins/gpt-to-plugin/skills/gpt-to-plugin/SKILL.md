---
name: gpt-to-plugin
description: Use when the user wants to turn one of their custom GPTs into a plugin, keep a portable copy of a GPT's setup, or check a plugin folder (plugin.json, skills, mcp.json) before submitting it to OpenAI.
---

# Packaging a custom GPT as a plugin, and checking plugin folders

## Which tool

- Converting a GPT: call `build_plugin_from_gpt`.
- Checking an existing plugin folder: call `validate_plugin_package`.
- The user asks what is checked, or what a rule id such as P006 or S003 means: call `explain_plugin_rules`.

## Converting a GPT

1. Say first that ChatGPT has its own "Migrate to plugin" button, which is the
   quickest way inside ChatGPT. This tool is for a portable copy the user controls (a plain folder
   they can keep in git and reuse in Codex) and for checking a package before submission.
2. Ask the user to paste, from the GPT editor's Configure tab:
   - the GPT's name (at most 30 characters; ask for a shorter one if it is longer),
   - its description,
   - its full instructions, exactly as written,
   - its conversation starters, if any,
   - the file names of its knowledge files (names only; the files themselves are not needed),
   - the names of its Actions, if any.
   Do not invent or rewrite any of these. If the user does not have the instructions, stop: the
   package is built from them.
3. Call `build_plugin_from_gpt` with what the user gave. Pass `author_name` only if the user gave one.
4. Present the files: name each path and say what it holds. The card shows every file with a Copy
   button; outside the card, show plugin.json and SKILL.md in code blocks.
5. Go through "Still to do by hand" honestly, one line per item:
   - Knowledge files are not in the package. Each one has to be copied into the skill's
     `references/` folder and mentioned in SKILL.md.
   - Actions are not converted. Each one needs an MCP server at a public HTTPS URL; mcp.json only
     holds placeholders until then.
   - Icons are not included and have to be added to `assets/`.
   - Anything the GPT got from ChatGPT capabilities (web search, image generation, data analysis)
     is not recorded in the package.
6. Report the validation result the tool returned. Errors must be fixed before submission;
   warnings are things to look at.

## Checking a plugin folder

1. Ask the user to paste every file in the folder with its path (plugin.json, mcp.json, each
   skills/<name>/SKILL.md, and the paths of other files). For large reference files the path and
   a short placeholder text are enough: only their presence and count are checked.
2. Call `validate_plugin_package`.
3. Go through errors first, then warnings. For each, give the file, what is wrong and the fix, and
   mention the documentation page the rule cites.

## What not to claim

- Never say a package "will be approved" or "is compliant". With no errors, say that no problems
  were found against the rules this tool checks.
- The tool does not test the plugin, run its MCP servers, check icons' pixel sizes or review the
  wording of the instructions. Say so if the user asks.
