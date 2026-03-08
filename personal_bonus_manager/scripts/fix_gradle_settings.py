#!/usr/bin/env python3
"""
修复 flet build 生成的 Flutter Android 项目中的 Gradle 构建错误。

根本原因（已确认）：
  Flutter 工具包 packages/flutter_tools/gradle/settings.gradle.kts 设置了
  RepositoriesMode.FAIL_ON_PROJECT_REPOS。
  当 dev.flutter.flutter-plugin-loader 插件在 settings 上下文中运行时，
  它（通过 native_plugin_loader.gradle.kts 或子项目引入）会添加一个
  maven { url } 仓库。FAIL_ON_PROJECT_REPOS 触发 repoMutationDisallowedOnProject，
  Gradle 将其报告为 "settings file 添加了 'maven' 仓库" 错误。

修复策略：
  将 Flutter 工具包 settings.gradle.kts 中的 FAIL_ON_PROJECT_REPOS 改为
  PREFER_SETTINGS，允许插件在 settings 上下文中添加仓库而不抛出异常。
"""

import re
import shutil
import sys
from pathlib import Path

GRADLE_VERSION = "8.13"


def find_flutter_sdk(android_dir: Path) -> Path | None:
    """从 local.properties 中提取 Flutter SDK 路径。"""
    local_props = android_dir / "local.properties"
    if not local_props.exists():
        return None
    for line in local_props.read_text(encoding='utf-8').splitlines():
        if line.startswith('flutter.sdk='):
            return Path(line.split('=', 1)[1].strip())
    return None


def find_android_dir(project_dir: Path) -> Path | None:
    candidates = [
        project_dir / "build" / "flutter" / "android",
        project_dir / "build" / "android",
    ]
    for p in candidates:
        if p.is_dir():
            return p
    found = list(project_dir.glob("build/**/android"))
    return found[0] if found else None


# ── 核心修复：Flutter 工具包 settings.gradle.kts ─────────────────────────────

def fix_flutter_tools_settings(flutter_sdk: Path) -> bool:
    tools_settings = flutter_sdk / "packages" / "flutter_tools" / "gradle" / "settings.gradle.kts"

    if not tools_settings.exists():
        print(f"警告: 未找到 {tools_settings}，跳过")
        return True

    content = tools_settings.read_text(encoding='utf-8')

    if 'FAIL_ON_PROJECT_REPOS' not in content:
        if 'PREFER_SETTINGS' in content or 'PREFER_PROJECT' in content:
            print(f"✓ Flutter 工具包 settings 已修复，跳过")
        else:
            print(f"✓ Flutter 工具包 settings 无 FAIL_ON_PROJECT_REPOS，跳过")
        return True

    backup = tools_settings.with_suffix('.kts.orig')
    if not backup.exists():
        shutil.copy2(tools_settings, backup)
        print(f"✓ Flutter 工具包 settings 已备份到 {backup.name}")

    new_content = content.replace(
        'RepositoriesMode.FAIL_ON_PROJECT_REPOS',
        'RepositoriesMode.PREFER_SETTINGS',
    )
    tools_settings.write_text(new_content, encoding='utf-8')
    print(f"✓ Flutter 工具包 settings: FAIL_ON_PROJECT_REPOS → PREFER_SETTINGS")
    print(f"  ({tools_settings})")
    return True


# ── 修复 Gradle Wrapper 版本 ──────────────────────────────────────────────────

def fix_gradle_wrapper(android_dir: Path) -> bool:
    wrapper_props = android_dir / "gradle" / "wrapper" / "gradle-wrapper.properties"
    if not wrapper_props.exists():
        print(f"警告: 未找到 {wrapper_props}，跳过")
        return True

    content = wrapper_props.read_text(encoding='utf-8')

    # 找当前版本号
    match = re.search(r'gradle-(\d+\.\d+(?:\.\d+)?)-(?:bin|all)\.zip', content)
    if not match:
        print(f"警告: gradle-wrapper.properties 中未找到 distributionUrl，跳过")
        return True

    current = match.group(1)
    if current == GRADLE_VERSION:
        print(f"✓ Gradle wrapper 已是 {GRADLE_VERSION}，跳过")
        return True

    new_content = re.sub(
        r'(gradle-)[\d.]+(-(?:bin|all)\.zip)',
        rf'\g<1>{GRADLE_VERSION}\2',
        content,
    )
    wrapper_props.write_text(new_content, encoding='utf-8')
    print(f"✓ Gradle wrapper: {current} → {GRADLE_VERSION}")
    return True


# ── 还原之前错误的 settings.gradle.kts 补丁 ──────────────────────────────────

def restore_app_settings(android_dir: Path) -> bool:
    settings_file = android_dir / "settings.gradle.kts"
    backup = settings_file.with_suffix('.kts.orig')

    if not backup.exists():
        # 没有备份，可能已经是原始文件
        return True

    # 恢复为原始文件（移除之前的错误补丁）
    shutil.copy2(backup, settings_file)
    print(f"✓ settings.gradle.kts 已从备份恢复（移除之前的无效补丁）")
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

    print(f"Android 目录: {android_dir}")

    flutter_sdk = find_flutter_sdk(android_dir)
    if not flutter_sdk:
        print("错误: 无法从 local.properties 读取 flutter.sdk 路径", file=sys.stderr)
        sys.exit(1)

    print(f"Flutter SDK: {flutter_sdk}\n")

    # 步骤 1: 还原 settings.gradle.kts（移除之前的错误补丁）
    ok1 = restore_app_settings(android_dir)

    # 步骤 2: 修复 Flutter 工具包的 settings.gradle.kts（核心修复）
    ok2 = fix_flutter_tools_settings(flutter_sdk)

    # 步骤 3: 升级 Gradle wrapper 版本
    ok3 = fix_gradle_wrapper(android_dir)

    if not (ok1 and ok2 and ok3):
        sys.exit(1)

    print("\n✓ 修复完成！现在运行：")
    flutter_dir = android_dir.parent
    print(f"  cd {flutter_dir}")
    print("  flutter build apk --release")
    print()
    print("注意：此修复改动了 Flutter SDK 文件。")
    print(f"如需还原，运行：")
    tools_settings = flutter_sdk / "packages" / "flutter_tools" / "gradle" / "settings.gradle.kts"
    print(f"  cp {tools_settings}.orig {tools_settings}")


if __name__ == '__main__':
    main()
