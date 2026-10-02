# Submitting each plugin to OpenAI

OpenAI's submission form (developers.openai.com/plugins/deploy/submission) asks, for a plugin
with an MCP server, for: a website URL, a support URL, a privacy policy URL, a terms of service URL,
an icon, a display name (≤30 characters), a short description (≤30 characters), a long description
(≤4000 characters), **five positive test cases**, **three negative test cases**, and a video
walkthrough. Identity verification (individual or business) must be done first in the OpenAI
Platform dashboard. The values below are ready to paste. Replace `chatgpt-plugins-oqk9.onrender.com` with the deployed hostname.

Common to all five:

| Field | Value |
|---|---|
| Support URL | https://github.com/abafaboy/chatgpt-plugins/issues |
| Privacy policy URL | https://chatgpt-plugins-oqk9.onrender.com/privacy |
| Terms of service URL | https://chatgpt-plugins-oqk9.onrender.com/terms |
| Icon | `plugins/<slug>/assets/icon.png` (512×512) |
| Login needed | No (no demo account required) |

---

## 1. UzText: Uzbek Scripts & Sums (`uz-text`)

- MCP URL: `https://chatgpt-plugins-oqk9.onrender.com/uz-text/mcp` · Website: `https://chatgpt-plugins-oqk9.onrender.com/site/uz-text`
- Short description: `Uzbek scripts and sums` (22)

Positive tests
1. "Write «Ўзбекистон Республикаси» in Latin." → `convert_uzbek_script(target=latin)` → "Oʻzbekiston Respublikasi".
2. "Convert 'Toshkent shahri' to the new Latin alphabet." → `convert_uzbek_script(target=new_latin)` → "Toşkent şahri" plus the note that the law awaits signature.
3. "Write 1 250 000,50 soʻm in words for an invoice." → `write_amount_in_uzbek_words` → "bir million ikki yuz ellik ming soʻm ellik tiyin".
4. "Fix the apostrophes: O`zbekiston san'at" → `normalize_uzbek_text` → "Oʻzbekiston sanʼat".
5. "What is the official USD and EUR rate in Uzbekistan?" → `get_uzbek_exchange_rates(["USD","EUR"])` → rates with the Central Bank's date.

Negative tests
1. "What was the USD rate in Uzbekistan on 1 January 2020?" → explains only current rates are available; no invented figure.
2. "Translate this Uzbek paragraph into English." → translation is not transliteration; the tool is not used.
3. "Write minus 500 soʻm in words." → tool returns an error (negative amounts); the model explains.

## 2. Shops from Telegram Channels (`tg-shop`)

- MCP URL: `https://chatgpt-plugins-oqk9.onrender.com/tg-shop/mcp` · Website: `https://chatgpt-plugins-oqk9.onrender.com/site/tg-shop`
- Short description: `Telegram shop catalogues` (24)

Positive tests (demo shop is labelled sample data)
1. "Which shops can I browse?" → `list_shops` → Demo Shop (sample data), product counts.
2. "Find a thermos." → `search_products(query="termos")` (the skill tells the model to search in the shop's language; the English word alone matches nothing) → "Termos 0,75 l", price and shop page link.
3. "Show gifts under 200 000 soʻm." → `search_products(category, max_price=200000, currency="UZS")`.
4. "Show me sneakers" written in Cyrillic ("кроссовкалари") → script-insensitive match on the Latin title.
5. "Tell me more about the leather wallet." → `get_product` → all photos and the product page.

Negative tests
1. "Buy it for me and pay with my card." → the plugin does not order or take payment; points to the shop's page.
2. "Find iPhones on Amazon." → not a registered shop; the plugin is not used or says no match.
3. "When will it be delivered?" → no delivery data; must not invent terms.

## 3. Proforma & Invoice Checker (`invoice-check`)

- MCP URL: `https://chatgpt-plugins-oqk9.onrender.com/invoice-check/mcp` · Website: `https://chatgpt-plugins-oqk9.onrender.com/site/invoice-check`
- Short description: `Re-check proforma arithmetic` (28)
- Test files: `tests/fixtures/invoice_check/` (invented documents with planted errors).

Positive tests
1. Attach `01_proforma_en.pdf`: "Check this proforma." → errors IL101 (line 3: 2 × 6,180.00 = 12,360.00, not 12,630.00) and IL104 (total off by 900.00).
2. Attach `07_proforma_clean.pdf`: "Is the arithmetic right?" → no errors.
3. Attach `03_quotation_v1.xlsx` and `03_quotation_v2.xlsx`: "What changed?" → `compare_quotations` → price, quantity, lines, terms changes.
4. Attach `05_proforma_mixed_formats.csv`: "Check it." → number-format findings.
5. "Which checks do you run?" → `list_invoice_rules`.

Negative tests
1. Attach a .docx: → error naming supported types (PDF, XLSX, CSV, JSON).
2. "Is this supplier's price fair?" → explains only arithmetic and consistency are checked.
3. Attach a scanned image-only PDF → error: no text layer.

## 4. Speaking Band Coach (`speaking-coach`)

- MCP URL: `https://chatgpt-plugins-oqk9.onrender.com/speaking-coach/mcp` · Website: `https://chatgpt-plugins-oqk9.onrender.com/site/speaking-coach`
- Short description: `Speaking practice and feedback` (30)

Positive tests
1. "Give me a full speaking mock test." → `start_speaking_test(full)`; one question at a time.
2. "Give me a Part 2 cue card about a decision." → `start_speaking_test(part=2, topic="decision")`.
3. Paste an answer: "Analyse my answer, it took 95 seconds." → `analyse_speaking_transcript` (word count, fillers, linking words, words per minute).
4. After a typed test: "Score me." → `record_speaking_scores` with pronunciation omitted → "not assessed", no band.
5. After a voice-mode test: "Score me." → four criteria, practice estimate, disclaimer.

Negative tests
1. "Give me my official IELTS score." → explains it gives practice estimates only.
2. "Write my IELTS essay for me." → writing tasks are out of scope.
3. "Give me the real questions from next week's exam." → refuses; questions are original practice questions.

## 5. GPT to Plugin Packager (`gpt-to-plugin`)

- MCP URL: `https://chatgpt-plugins-oqk9.onrender.com/gpt-to-plugin/mcp` · Website: `https://chatgpt-plugins-oqk9.onrender.com/site/gpt-to-plugin`
- Short description: `Custom GPT to plugin folder` (27)

Positive tests
1. Paste a GPT's name, description and instructions: "Make a plugin package." → `build_plugin_from_gpt` → plugin.json, SKILL.md, README, "no errors".
2. Same with two actions listed → mcp.json with placeholders and the manual-steps checklist.
3. Paste a plugin.json with `"name": "My Plugin"` → `validate_plugin_package` → P004 error.
4. Paste a SKILL.md without frontmatter → S001 error.
5. "Which rules do you check?" → `explain_plugin_rules` with source links.

Negative tests
1. "Publish my plugin to the directory for me." → cannot submit; explains the submission steps.
2. "Migrate my GPT automatically from its link." → cannot read GPTs; asks the user to paste the configuration and mentions OpenAI's own "Migrate to plugin" button.
3. "Guarantee my plugin will be approved." → explains passing the checks does not guarantee approval.

---

## Video walkthrough

One short screen recording per plugin, in ChatGPT with the plugin connected in developer mode,
running positive tests 1–3. Upload unlisted (e.g. YouTube) and paste the link.
