#!/usr/bin/env python3
"""產生整合的品牌圖（自己畫的：藍底圓＋帳單＋閃電，沒有用台電或任何商標）。

輸出：
  custom_components/taipower_estimate/brand/icon.png      256x256，透明背景
  custom_components/taipower_estimate/brand/icon@2x.png   512x512
  docs/brand/icon.svg                                      同一組座標的向量原稿

HA 2026.3 起，custom integration 把圖放在 `<整合目錄>/brand/` 就會顯示（見 CHANGELOG 0.2.5）。
只需要 Pillow：python tools/gen_brand.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
BRAND_DIR = ROOT / "custom_components" / "taipower_estimate" / "brand"
SVG_PATH = ROOT / "docs" / "brand" / "icon.svg"

GRID = 512                      # 所有座標都在 512x512 格子裡
BLUE, WHITE, GRAY, AMBER = "#1565C0", "#FFFFFF", "#B0BEC5", "#FFB300"

CIRCLE = (256, 256, 240)        # cx, cy, r
# 帳單：左右直邊，底部鋸齒
RECEIPT = [(140, 92), (372, 92), (372, 404)]
_x = 372
for _i in range(6):             # 6 個鋸齒，由右往左
    _x -= 232 / 12
    RECEIPT.append((_x, 380))
    _x -= 232 / 12
    RECEIPT.append((_x, 404))
RECEIPT = [(round(x, 2), y) for x, y in RECEIPT]
LINES = [(176, 140, 336, 158), (176, 188, 300, 206), (176, 236, 268, 254)]   # 帳單上的文字線 x0,y0,x1,y1
BOLT = [(330, 196), (232, 330), (290, 330), (262, 452), (396, 282), (332, 282), (366, 196)]
BOLT_OUTLINE = 14               # 閃電外圍的藍色描邊，讓它從白色帳單上浮出來


def draw_png(size: int) -> Image.Image:
    ss = 4                      # 超取樣，邊緣才不會鋸齒
    k = size * ss / GRID
    img = Image.new("RGBA", (size * ss, size * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def s(pts):
        return [(x * k, y * k) for x, y in pts]

    cx, cy, r = CIRCLE
    d.ellipse([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k], fill=BLUE)
    d.polygon(s(RECEIPT), fill=WHITE)
    for x0, y0, x1, y1 in LINES:
        d.rounded_rectangle([x0 * k, y0 * k, x1 * k, y1 * k], radius=9 * k, fill=GRAY)
    d.polygon(s(BOLT), fill=AMBER, outline=BLUE, width=int(BOLT_OUTLINE * k))
    d.polygon(s(BOLT), fill=AMBER)
    return img.resize((size, size), Image.LANCZOS)


def svg() -> str:
    cx, cy, r = CIRCLE
    pts = lambda p: " ".join(f"{x:g},{y:g}" for x, y in p)  # noqa: E731
    lines = "\n".join(
        f'  <rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" rx="9" fill="{GRAY}"/>'
        for x0, y0, x1, y1 in LINES
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {GRID} {GRID}" width="256" height="256">\n'
        f'  <title>Taipower Bill Estimate</title>\n'
        f'  <circle cx="{cx}" cy="{cy}" r="{r}" fill="{BLUE}"/>\n'
        f'  <polygon points="{pts(RECEIPT)}" fill="{WHITE}"/>\n{lines}\n'
        f'  <polygon points="{pts(BOLT)}" fill="{AMBER}" stroke="{BLUE}" stroke-width="{BOLT_OUTLINE}" '
        f'stroke-linejoin="round" paint-order="stroke"/>\n'
        f'</svg>\n'
    )


def main() -> None:
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    SVG_PATH.parent.mkdir(parents=True, exist_ok=True)
    draw_png(256).save(BRAND_DIR / "icon.png", optimize=True)
    draw_png(512).save(BRAND_DIR / "icon@2x.png", optimize=True)
    SVG_PATH.write_text(svg(), encoding="utf-8")
    print("wrote", BRAND_DIR / "icon.png", BRAND_DIR / "icon@2x.png", SVG_PATH)


if __name__ == "__main__":
    main()
