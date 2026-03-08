#!/bin/bash
# Personal Bonus Manager - Android APK 构建脚本

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FLUTTER_DIR="$PROJECT_DIR/build/flutter"
FLET_BUILD_ARGS=(
    --project "personal_bonus_manager"
    --description "个人任务奖金管理系统"
    --product "PBM"
    --org "com.pbm"
    --build-version "1.0.0"
)

echo "=== PBM Android Build ==="
echo "项目目录: $PROJECT_DIR"

# 检查 flet 是否安装
if ! command -v flet &> /dev/null; then
    echo "错误: 未找到 flet 命令，请先安装: pip install flet"
    exit 1
fi

cd "$PROJECT_DIR"

# 修复 1: cookiecutter 对二进制文件（OTF字体等）的误判问题
# binaryornot 0.4.4 对以 ASCII 字节开头的二进制文件（如 OTF 字体 "OTTO"）误判为文本
echo "正在修复 cookiecutter 二进制文件处理..."
python3 scripts/fix_cookiecutter.py

# 如果 build/flutter/android/settings.gradle.kts 已存在，直接修复后跑 flutter build
# 避免重新执行耗时的 flet 前置步骤（创建 shell、打包 Python 等）
SETTINGS_KTS="$FLUTTER_DIR/android/settings.gradle.kts"
if [ -f "$SETTINGS_KTS" ]; then
    echo "检测到已有 Flutter 项目，修复 Gradle 配置后直接构建..."
    python3 scripts/fix_gradle_settings.py
    echo "运行 flutter build apk --release ..."
    cd "$FLUTTER_DIR"
    flutter build apk --release
    cd "$PROJECT_DIR"
else
    # 首次构建：运行完整 flet build（内部会创建 Flutter 项目并构建）
    echo "开始首次构建 APK..."
    # flet build 会因 settings.gradle.kts 失败，我们捕获后修复并重跑 flutter build
    if ! flet build apk "${FLET_BUILD_ARGS[@]}"; then
        echo ""
        echo "flet build 第一阶段完成（Gradle 错误属预期，正在自动修复...）"
        if [ -f "$SETTINGS_KTS" ]; then
            python3 scripts/fix_gradle_settings.py
            echo "运行 flutter build apk --release ..."
            cd "$FLUTTER_DIR"
            flutter build apk --release
            cd "$PROJECT_DIR"
        else
            echo "错误: 未找到生成的 Flutter 项目，构建彻底失败"
            exit 1
        fi
    fi
fi

# 找到生成的 APK
APK_PATH=$(find "$FLUTTER_DIR/build/app/outputs" -name "*.apk" 2>/dev/null | head -1)
if [ -n "$APK_PATH" ]; then
    mkdir -p "$PROJECT_DIR/build"
    cp "$APK_PATH" "$PROJECT_DIR/build/app-release.apk"
    echo ""
    echo "=== 构建完成 ==="
    echo "APK: $PROJECT_DIR/build/app-release.apk"
else
    echo "=== 构建完成 ==="
    echo "APK 文件位于 $FLUTTER_DIR/build/app/outputs/"
fi
