#!/usr/bin/env python3
"""
修复 flet build 生成的 Flutter Android 项目中的 Gradle 构建错误。

根本原因：
  Gradle 8.11+ / 8.14 对复合构建（includeBuild）中的 maven 仓库命名引入了
  更严格的检查。Flutter Gradle 工具包（通过 includeBuild 引入）内部会添加
  未命名的 maven { url } 仓库（默认名称 'maven'），在新版 Gradle 的
  PREFER_SETTINGS 模式下触发 "Error resolving plugin" 错误。

修复策略（双重修复）：
  1. 降级 gradle-wrapper.properties 中的 Gradle 版本到 8.10
     （AGP 8.11.1 要求最低 8.9，8.10 是经过充分验证的稳定版本）
  2. 在 settings.gradle.kts 中替换 gradlePluginPortal() 为带显式名称的
     maven 块，避免默认名称 'maven' 冲突
"""

import re
import shutil
import sys
from pathlib import Path

# ── Gradle wrapper 目标版本 ──────────────────────────────────────────────────
TARGET_GRADLE = "8.10"
TARGET_GRADLE_URL = (
    f"https\\://services.gradle.org/distributions/"
    f"gradle-{TARGET_GRADLE}-all.zip"
)

# ── settings.gradle.kts 补丁标记 ─────────────────────────────────────────────
SETTINGS_MARKER = "// pbm-gradle-fix-v2"

SETTINGS_PATCH = """\

// pbm-gradle-fix-v2: 替换 gradlePluginPortal() 为显式命名 maven，避免默认 'maven' 命名冲突
"""


def find_android_dir(project_dir: Path) -> Path | None:
    """找到生成的 Flutter 项目的 android/ 目录。"""
    candidates = [
        project_dir / "build" / "flutter" / "android",
        project_dir / "build" / "android",
    ]
    for p in candidates:
        if p.is_dir():
            return p
    found = list(project_dir.glob("build/**/android"))
    return found[0] if found else None


# ── 修复 1：Gradle wrapper 版本 ──────────────────────────────────────────────

def fix_gradle_wrapper(android_dir: Path) -> bool:
    wrapper_props = android_dir / "gradle" / "wrapper" / "gradle-wrapper.properties"
    if not wrapper_props.exists():
        print(f"警告: 未找到 {wrapper_props}，跳过 wrapper 修复")
        return True

    content = wrapper_props.read_text(encoding='utf-8')

    # 提取当前版本
    m = re.search(r'distributionUrl=.*gradle-([0-9.]+)-', content)
    current = m.group(1) if m else "unknown"

    if current == TARGET_GRADLE:
        print(f"✓ Gradle wrapper 已是 {TARGET_GRADLE}，跳过")
        return True

    # 备份
    backup = wrapper_props.with_suffix('.properties.orig')
    if not backup.exists():
        shutil.copy2(wrapper_props, backup)

    new_content = re.sub(
        r'distributionUrl=.*',
        f'distributionUrl={TARGET_GRADLE_URL}',
        content,
    )
    wrapper_props.write_text(new_content, encoding='utf-8')
    print(f"✓ Gradle wrapper: {current} → {TARGET_GRADLE}  ({wrapper_props})")
    return True


# ── 修复 2：settings.gradle.kts pluginManagement 仓库 ────────────────────────

def fix_settings_gradle(android_dir: Path) -> bool:
    settings_file = android_dir / "settings.gradle.kts"
    if not settings_file.exists():
        print(f"错误: 未找到 {settings_file}", file=sys.stderr)
        return False

    content = settings_file.read_text(encoding='utf-8')

    if SETTINGS_MARKER in content:
        print(f"✓ settings.gradle.kts 已应用补丁，跳过")
        return True

    # 把 gradlePluginPortal() 替换为显式命名的 maven 仓库
    # 这样就不会产生默认名 'maven'，而是明确叫 'GradlePluginPortal'
    if 'gradlePluginPortal()' not in content:
        print("警告: 未找到 gradlePluginPortal()，跳过 settings 修复")
        return True

    new_content = content.replace(
        'gradlePluginPortal()',
        'maven {\n'
        '            name = "GradlePluginPortal"\n'
        '            url = uri("https://plugins.gradle.org/m2/")\n'
        '        }',
    )
    new_content += SETTINGS_PATCH

    # 备份
    backup = settings_file.with_suffix('.kts.orig')
    if not backup.exists():
        shutil.copy2(settings_file, backup)
        print(f"✓ 已备份到 {backup.name}")

    settings_file.write_text(new_content, encoding='utf-8')
    print(f"✓ settings.gradle.kts: 替换 gradlePluginPortal() 为显式命名 maven")
    return True


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    print("=== 修复 Flutter Android Gradle 构建错误 ===\n")

    project_dir = Path(__file__).resolve().parent.parent
    android_dir = find_android_dir(project_dir)

    if not android_dir:
        print("错误: 未找到 android/ 目录", file=sys.stderr)
        print("请先运行 flet build apk（即使失败也会生成 build/ 目录）", file=sys.stderr)
        sys.exit(1)

    print(f"Android 目录: {android_dir}\n")

    ok1 = fix_gradle_wrapper(android_dir)
    ok2 = fix_settings_gradle(android_dir)

    if not (ok1 and ok2):
        sys.exit(1)

    print("\n✓ 修复完成！现在运行：")
    flutter_dir = android_dir.parent
    print(f"  cd {flutter_dir}")
    print("  flutter build apk --release")


if __name__ == '__main__':
    main()
