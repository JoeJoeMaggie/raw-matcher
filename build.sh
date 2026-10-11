#!/usr/bin/env bash
# 打包成 macOS 单文件 .app —— 必须在 macOS 上运行（PyInstaller 不能跨平台编译）
# 用法：bash build.sh
set -euo pipefail
cd "$(dirname "$0")"

NAME="RAWMatcher"          # .app 名字（改成中文可用 Finder 重命名）
BUNDLE_ID="local.rawmatcher"

python3 -m pip install --upgrade -r requirements.txt

ICON_ARGS=()
[ -f icon.icns ] && ICON_ARGS=(--icon icon.icns)

# 图标另需随包分发一份，供运行时设置窗口图标（macOS 下 --add-data 用 : 分隔）
DATA_ARGS=()
[ -f icon.png ] && DATA_ARGS+=(--add-data "icon.png:.")

python3 -m PyInstaller \
  --noconfirm --clean --onefile --windowed \
  --name "$NAME" \
  --osx-bundle-identifier "$BUNDLE_ID" \
  --collect-all tkinterdnd2 \
  "${ICON_ARGS[@]}" "${DATA_ARGS[@]}" \
  main.py

echo
echo "打包完成：dist/$NAME.app"
echo "首次打开若提示“无法验证开发者”：右键 -> 打开，或到 系统设置 -> 隐私与安全性 点“仍要打开”。"
echo "若提示“已损坏”：xattr -dr com.apple.quarantine \"dist/$NAME.app\""
