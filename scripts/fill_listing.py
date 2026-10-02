"""Fill the listing fields of every plugins/<slug>/plugin.json (idempotent).

Field names follow OpenAI's plugin packaging docs (developers.openai.com/plugins/build/plugins):
root `homepage`, `repository`, `license`, `keywords`; and under extensions.com.openai.interface
`shortDescription`, `longDescription`, `developerName`, `capabilities`, `websiteURL`,
`privacyPolicyURL`, `termsOfServiceURL`, `defaultPrompt`.

Run: python scripts/fill_listing.py <hostname>
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "https://github.com/abafaboy/chatgpt-plugins"
DEVELOPER = "Abdulfayyod Mukhamedov"

LISTING = {
    "uz-text": {
        "short": "Uzbek scripts and sums",
        "keywords": ["uzbek", "transliteration", "cyrillic", "latin", "exchange rates", "invoices"],
        "prompts": ["Write «Ўзбекистон Республикаси» in Latin.",
                    "Write 1 250 000,50 soʻm in words for an invoice.",
                    "What is the official USD rate in Uzbekistan today?"],
    },
    "tg-shop": {
        "short": "Telegram shop catalogues",
        "keywords": ["telegram", "shopping", "uzbekistan", "catalogue"],
        "prompts": ["Which shops can I browse?", "Find a thermos.", "Show gifts under 200 000 soʻm."],
    },
    "invoice-check": {
        "short": "Re-check proforma arithmetic",
        "keywords": ["invoice", "proforma", "quotation", "procurement", "arithmetic"],
        "prompts": ["Check the arithmetic of this proforma.", "What changed between these two quotations?",
                    "Which checks do you run?"],
    },
    "speaking-coach": {
        "short": "Speaking practice and feedback",
        "keywords": ["ielts", "english", "speaking", "practice", "education"],
        "prompts": ["Give me a full speaking mock test.", "Give me a Part 2 cue card about a decision.",
                    "Analyse my answer, it took 95 seconds."],
    },
    "gpt-to-plugin": {
        "short": "Custom GPT to plugin folder",
        "keywords": ["custom gpt", "migration", "plugin", "packaging", "validation"],
        "prompts": ["Turn my custom GPT into a plugin package.", "Check this plugin.json before I submit it.",
                    "Which packaging rules do you check?"],
    },
}


def main(host: str) -> None:
    base = f"https://{host}"
    for slug, info in LISTING.items():
        path = ROOT / "plugins" / slug / "plugin.json"
        m = json.loads(path.read_text(encoding="utf-8"))
        assert len(info["short"]) <= 30, slug
        site = f"{base}/site/{slug}"
        m["homepage"] = site
        m["repository"] = REPO
        m["license"] = "MIT"
        m["keywords"] = info["keywords"]
        iface = m.setdefault("extensions", {}).setdefault("com.openai", {}).setdefault("interface", {})
        iface.update({
            "shortDescription": info["short"],
            "longDescription": m["description"],
            "developerName": DEVELOPER,
            "capabilities": ["Read"],
            "websiteURL": site,
            "privacyPolicyURL": f"{base}/privacy",
            "termsOfServiceURL": f"{base}/terms",
            "defaultPrompt": info["prompts"],
        })
        # Keep a stable, readable key order: schema, identity, then the rest.
        order = ["$schema", "name", "version", "description", "author", "homepage", "repository",
                 "license", "keywords", "skills", "extensions"]
        m = {k: m[k] for k in order if k in m} | {k: v for k, v in m.items() if k not in order}
        path.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("updated", path.relative_to(ROOT))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "chatgpt-plugins-oqk9.onrender.com")
