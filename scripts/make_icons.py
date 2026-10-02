"""Draw the five 512x512 plugin icons (plugins/<slug>/assets/icon.png).

Plain geometric marks drawn in code, so there is no third-party artwork or logo
in any icon. Run: python scripts/make_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
S = 512


def base(color: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, S - 1, S - 1), radius=112, fill=color)
    return img, d


def text(d: ImageDraw.ImageDraw, xy: tuple[int, int], s: str, size: int, fill: str = "white") -> None:
    font = ImageFont.truetype(FONT, size)
    d.text(xy, s, font=font, fill=fill, anchor="mm")


def uz_text() -> Image.Image:
    img, d = base("#0E7C66")
    text(d, (180, 200), "Ў", 190)
    text(d, (340, 200), "Ö", 190)
    d.rounded_rectangle((96, 330, 416, 410), radius=24, fill="#FFFFFF")
    text(d, (256, 371), "soʻm", 64, fill="#0E7C66")
    return img


def tg_shop() -> Image.Image:
    img, d = base("#1C64D8")
    # shopping bag
    d.rounded_rectangle((126, 190, 386, 420), radius=36, fill="white")
    d.arc((186, 110, 326, 260), start=180, end=360, fill="white", width=26)
    # paper-plane mark on the bag
    d.polygon([(186, 300), (330, 250), (290, 370), (262, 320)], fill="#1C64D8")
    return img


def invoice_check() -> Image.Image:
    img, d = base("#33415C")
    d.rounded_rectangle((136, 86, 376, 426), radius=28, fill="white")
    for y in (150, 200, 250):
        d.rounded_rectangle((176, y, 336, y + 18), radius=9, fill="#C9D1E0")
    d.line([(180, 330), (232, 382), (336, 278)], fill="#1A9E55", width=34, joint="curve")
    return img


def speaking_coach() -> Image.Image:
    img, d = base("#B4441F")
    d.rounded_rectangle((96, 120, 416, 330), radius=60, fill="white")
    d.polygon([(170, 320), (150, 410), (250, 330)], fill="white")
    for i, h in enumerate((50, 90, 130, 90, 50)):
        x = 176 + i * 40
        d.rounded_rectangle((x, 225 - h // 2, x + 20, 225 + h // 2), radius=10, fill="#B4441F")
    return img


def gpt_to_plugin() -> Image.Image:
    img, d = base("#5A3FC0")
    d.rounded_rectangle((86, 150, 246, 362), radius=30, outline="white", width=22)
    d.rounded_rectangle((300, 150, 426, 362), radius=30, fill="white")
    d.polygon([(232, 220), (300, 256), (232, 292)], fill="white")
    d.rounded_rectangle((330, 210, 396, 230), radius=10, fill="#5A3FC0")
    d.rounded_rectangle((330, 250, 396, 270), radius=10, fill="#5A3FC0")
    d.rounded_rectangle((330, 290, 376, 310), radius=10, fill="#5A3FC0")
    return img


ICONS = {
    "uz-text": uz_text,
    "tg-shop": tg_shop,
    "invoice-check": invoice_check,
    "speaking-coach": speaking_coach,
    "gpt-to-plugin": gpt_to_plugin,
}

if __name__ == "__main__":
    for slug, draw in ICONS.items():
        out = ROOT / "plugins" / slug / "assets" / "icon.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        draw().save(out)
        print(out.relative_to(ROOT))
    sheet = Image.new("RGBA", (S * 5 + 40 * 6, S + 80), "#F2F3F5")
    for i, draw in enumerate(ICONS.values()):
        sheet.alpha_composite(draw(), (40 + i * (S + 40), 40))
    sheet.convert("RGB").save(ROOT / "docs" / "icons.png")
