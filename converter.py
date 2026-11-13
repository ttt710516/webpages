"""五線譜 → 簡譜 轉換模組。

目前是「假的」實作：不管上傳什麼，都產生一份固定的範例簡譜 SVG。
之後換成真正的轉換邏輯時，只要維持 `convert()` 的介面不變即可，
server.py 和前端都不需要改。

介面約定
--------
convert(input_path, output_dir) -> 輸出檔案的路徑 (pathlib.Path)

- input_path : 使用者上傳的檔案（.pdf / .png / .jpg / .musicxml / .mxl ...）
- output_dir : 可寫入的資料夾，輸出檔請放在這裡
- 回傳的檔案副檔名決定預覽方式：
    .svg / .png / .jpg  → 以圖片預覽
    .pdf                → 以內嵌 PDF 預覽
- 轉換失敗請 raise ConversionError("給使用者看的錯誤訊息")
"""

from __future__ import annotations

import html
import time
from pathlib import Path


class ConversionError(Exception):
    """轉換失敗；訊息會直接顯示給使用者。"""


def convert(input_path: Path, output_dir: Path) -> Path:
    input_path = Path(input_path)
    output_dir = Path(output_dir)

    time.sleep(1.2)  # 模擬處理時間，讓前端的「轉換中」狀態看得到

    title = input_path.stem
    out = output_dir / f"{title}-簡譜.svg"
    out.write_text(_fake_jianpu_svg(title), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# 以下只是產生假資料用，換成真正轉換器後可整段刪除
# ---------------------------------------------------------------------------

# (數字, 八度, 底線數)；"-" 表示延長線
_FAKE_LINES = [
    ["1", "1", "5", "5", "|", "6", "6", "5", "-", "|", "4", "4", "3", "3", "|", "2", "2", "1", "-", "|"],
    ["5", "5", "4", "4", "|", "3", "3", "2", "-", "|", "5", "5", "4", "4", "|", "3", "3", "2", "-", "|"],
    ["1", "1", "5", "5", "|", "6", "6", "5", "-", "|", "4", "4", "3", "3", "|", "2", "2", "1", "-", "||"],
]


def _fake_jianpu_svg(title: str) -> str:
    width, height = 794, 1123  # A4 @ 96dpi
    margin = 64
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#fff"/>',
        f'<text x="{width / 2}" y="96" font-size="28" text-anchor="middle" '
        f'font-family="serif" fill="#111">{html.escape(title)}</text>',
        f'<text x="{margin}" y="150" font-size="18" font-family="sans-serif" fill="#111">1=C  4/4</text>',
        f'<text x="{width - margin}" y="150" font-size="14" text-anchor="end" '
        f'font-family="sans-serif" fill="#888">（範例輸出 · 轉換器尚未實作）</text>',
    ]

    y = 230
    for line in _FAKE_LINES:
        step = (width - 2 * margin) / len(line)
        x = margin + step / 2
        for tok in line:
            if tok == "|":
                parts.append(f'<line x1="{x}" y1="{y - 24}" x2="{x}" y2="{y + 6}" stroke="#111" stroke-width="1.2"/>')
            elif tok == "||":
                parts.append(f'<line x1="{x - 4}" y1="{y - 24}" x2="{x - 4}" y2="{y + 6}" stroke="#111" stroke-width="1.2"/>')
                parts.append(f'<line x1="{x + 1}" y1="{y - 24}" x2="{x + 1}" y2="{y + 6}" stroke="#111" stroke-width="3.5"/>')
            elif tok == "-":
                parts.append(f'<line x1="{x - 7}" y1="{y - 8}" x2="{x + 7}" y2="{y - 8}" stroke="#111" stroke-width="2"/>')
            else:
                parts.append(f'<text x="{x}" y="{y}" font-size="24" text-anchor="middle" '
                             f'font-family="sans-serif" fill="#111">{tok}</text>')
            x += step
        y += 90

    parts.append("</svg>")
    return "\n".join(parts)
