"""Point every plugins/<slug>/mcp.json at the deployed server.

    python scripts/set_host.py chatgpt-plugins.onrender.com

Rewrites the "HOST" placeholder (or a previous host) in each mcp.json to
https://<host>/<slug>/mcp. Run it once after the first deploy, then commit.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(host: str) -> int:
    host = host.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
    if not re.fullmatch(r"[A-Za-z0-9.-]+(:\d+)?", host):
        print(f"not a hostname: {host!r}", file=sys.stderr)
        return 2
    for path in sorted(ROOT.glob("plugins/*/mcp.json")):
        slug = path.parent.name
        data = json.loads(path.read_text(encoding="utf-8"))
        for server in data["mcpServers"].values():
            server["url"] = f"https://{host}/{slug}/mcp"
        path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{path.relative_to(ROOT)} -> https://{host}/{slug}/mcp")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
