#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成应用图标：icon.png（窗口图标）、icon.ico（Windows）、icon.icns（macOS 打包用）。

只需运行一次，产物已随仓库提供；改了设计再跑：
    python3 make_icon.py
依赖 Pillow（仅生成图标时需要，程序运行不需要）。
"""

from __future__ import annotations

import io
import struct
import sys
from pathlib import Path

from PIL import Image, ImageDraw

S = 1024                      # 主图尺寸
ICON_BG = "#fcfcfc"           # 图标底色（取自参考图）
TEAL = "#00b8a7"              # 机身颜色（取自参考图）

# 以下几何按参考图比例等比放大：机身 65×42、顶部取景器凸起 30/17 梯形、
# 镜头环外径 13.5、环粗 3（参考图坐标 ×≈9.77 得到 1024 画布上的数值）。
CAM_LEFT, CAM_RIGHT = 195, 830        # 机身左右
BODY_TOP, BODY_BOTTOM = 360, 771      # 机身上下
HUMP_TOP = 262                        # 凸起顶部
HUMP_HALF_TOP, HUMP_HALF_BOTTOM = 83, 146
LENS_CX, LENS_CY = 512, 566           # 镜头中心
LENS_R, LENS_W = 117.5, 29            # 镜头环半径与线宽（外径 = R + W/2 ≈ 132）


def make_master() -> Image.Image:
    """绘制 1024x1024 主图：浅底圆角方块 + 青绿色相机（白色镜头环）。"""
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 底板
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.2237), fill=ICON_BG)

    # 顶部取景器凸起：上半是圆角矩形，下半用两块斜边三角补出「下宽上窄」的梯形
    d.rounded_rectangle([512 - HUMP_HALF_TOP, HUMP_TOP, 512 + HUMP_HALF_TOP, 400],
                        radius=30, fill=TEAL)
    for side in (-1, 1):
        x = 512 + side * HUMP_HALF_TOP
        d.polygon([(x, 292), (512 + side * HUMP_HALF_BOTTOM, 400), (x, 400)], fill=TEAL)

    # 机身
    d.rounded_rectangle([CAM_LEFT, BODY_TOP, CAM_RIGHT, BODY_BOTTOM], radius=60, fill=TEAL)

    # 凸起上的白色取景槽
    d.rounded_rectangle([512 - 42, 288, 512 + 42, 328], radius=20, fill="white")

    # 镜头环（空心圆，描边即环）
    d.ellipse([LENS_CX - LENS_R, LENS_CY - LENS_R, LENS_CX + LENS_R, LENS_CY + LENS_R],
              outline="white", width=LENS_W)
    return img


def save_icns(master: Image.Image, path: Path) -> None:
    """手写 icns：文件头 + 若干 PNG 块（Pillow 不生成 icns）。"""
    entries = [
        (b"icp4", 16), (b"icp5", 32), (b"ic11", 32), (b"ic12", 64),
        (b"ic07", 128), (b"ic13", 256), (b"ic08", 256),
        (b"ic14", 512), (b"ic09", 512), (b"ic10", 1024),
    ]
    blocks = b""
    for tag, size in entries:
        buf = io.BytesIO()
        master.resize((size, size), Image.LANCZOS).save(buf, format="PNG")
        data = buf.getvalue()
        blocks += tag + struct.pack(">I", len(data) + 8) + data
    path.write_bytes(b"icns" + struct.pack(">I", len(blocks) + 8) + blocks)


def main() -> None:
    out = Path(__file__).resolve().parent
    master = make_master()
    master.save(out / "icon.png")
    master.save(out / "icon.ico",
                sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    save_icns(master, out / "icon.icns")
    for name in ("icon.png", "icon.ico", "icon.icns"):
        print(f"{name}: {(out / name).stat().st_size} bytes")


if __name__ == "__main__":
    sys.exit(main())
