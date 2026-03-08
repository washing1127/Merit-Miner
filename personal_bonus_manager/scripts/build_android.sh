#!/bin/bash
# Personal Bonus Manager - Android APK 构建脚本
# 使用 flet pack 打包为 APK

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== PBM Android Build ==="
echo "项目目录: $PROJECT_DIR"

# 检查 flet 是否安装
if ! command -v flet &> /dev/null; then
    echo "错误: 未找到 flet 命令，请先安装: pip install flet"
    exit 1
fi

cd "$PROJECT_DIR"

# 修复 cookiecutter 对二进制文件（OTF字体等）的误判问题
# binaryornot 0.4.4 对以 ASCII 字节开头的二进制文件（如 OTF 字体 "OTTO"）误判为文本
echo "正在修复 cookiecutter 二进制文件处理..."
python3 scripts/fix_cookiecutter.py

# 构建 APK
echo "开始构建 APK..."
flet build apk \
    --project "personal_bonus_manager" \
    --description "个人任务奖金管理系统" \
    --product "PBM" \
    --org "com.pbm" \
    --build-version "1.0.0"

echo "=== 构建完成 ==="
echo "APK 文件位于 build/ 目录"
