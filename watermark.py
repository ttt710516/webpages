"""產生加浮水印的預覽檔。

- SVG：在最上層疊一層斜向重複文字
- PNG / JPG：用 Pillow（有裝才支援）降解析度並疊上浮水印，輸出 PNG
- 其他格式：不提供預覽
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import config


class PreviewUnsupported(Exception):
    pass


def make_preview(src: Path, dest_dir: Path) -> Path:
    ext = src.suffix.lower()
    if ext == ".svg":
        out = dest_dir / "preview.svg"
        out.write_text(_watermark_svg(src.read_text(encoding="utf-8")), encoding="utf-8")
        return out
    if ext in (".png", ".jpg", ".jpeg"):
        out = dest_dir / "preview.png"
        _watermark_raster(src, out)
        return out
    raise PreviewUnsupported(f"無法為 {ext} 產生預覽")


# ---------------------------------------------------------------------------

def _svg_size(svg: str) -> tuple[float, float]:
    m = re.search(r'viewBox="\s*([-\d.]+)[\s,]+([-\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)', svg)
    if m:
        return float(m.group(3)), float(m.group(4))
    w = re.search(r'<svg[^>]*\swidth="([\d.]+)', svg)
    h = re.search(r'<svg[^>]*\sheight="([\d.]+)', svg)
    return (float(w.group(1)) if w else 800), (float(h.group(1)) if h else 1100)


def _watermark_svg(svg: str) -> str:
    w, h = _svg_size(svg)
    text = html.escape(config.WATERMARK_TEXT)
    step_x, step_y = 260, 150
    rows = []
    y = -h * 0.5
    i = 0
    while y < h * 1.5:
        x = -w * 0.5 + (step_x / 2 if i % 2 else 0)
        while x < w * 1.5:
            rows.append(f'<text x="{x:.0f}" y="{y:.0f}">{text}</text>')
            x += step_x
        y += step_y
        i += 1
    layer = (
        f'<g transform="rotate(-30 {w / 2:.0f} {h / 2:.0f})" fill="#b5452f" fill-opacity="0.22" '
        f'font-size="34" font-family="sans-serif" font-weight="bold" '
        f'text-anchor="middle" pointer-events="none">'
        + "".join(rows) + "</g>"
    )
    idx = svg.rfind("</svg>")
    if idx < 0:
        raise PreviewUnsupported("SVG 格式不正確")
    return svg[:idx] + layer + svg[idx:]


def _watermark_raster(src: Path, out: Path) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as e:
        raise PreviewUnsupported("需要安裝 Pillow 才能預覽圖片格式") from e

    img = Image.open(src).convert("RGBA")
    img.thumbnail((900, 900 * 4))  # 預覽降解析度
    layer = Image.new("RGBA", (img.width * 2, img.height * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    text = config.WATERMARK_TEXT
    try:
        font = ImageFont.truetype("NotoSansCJK-Bold.ttc", 32)
    except OSError:
        font = ImageFont.load_default(size=32)
        text = "PREVIEW"  # 預設字型沒有中文字
    for yy in range(0, layer.height, 140):
        for xx in range(0, layer.width, 320):
            draw.text((xx, yy), text, fill=(181, 69, 47, 70), font=font)
    layer = layer.rotate(30, center=(layer.width / 2, layer.height / 2))
    left, top = img.width // 2, img.height // 2
    layer = layer.crop((left, top, left + img.width, top + img.height))
    Image.alpha_composite(img, layer).convert("RGB").save(out, "PNG")
