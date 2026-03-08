#!/usr/bin/env python3
"""
修复 flet build 生成的 Flutter Android 项目中 settings.gradle.kts 的
Gradle 仓库冲突问题。

真正根因：
  settings.gradle.kts 通过 includeBuild("$flutterSdkPath/packages/flutter_tools/gradle")
  引入了 Flutter Gradle 工具包。Flutter Gradle 工具包在自己的 settings 里会添加
  未命名的 maven 仓库（如 storage.flutter-io.cn 镜像），Gradle 将未命名 maven 块
  默认命名为 'maven'。当 Gradle 以 PREFER_SETTINGS 模式运行时，发现 settings 文件
  里有这个 'maven' 仓库，就报 "Error resolving plugin" 错误。

修复策略：
  在 settings.gradle.kts 末尾追加 dependencyResolutionManagement 块，
  使用 PREFER_PROJECT 模式，允许 Flutter SDK 自由添加项目级仓库，
  同时显式声明 google() / mavenCentral() 作为主要依赖来源。
"""

import shutil
import sys
from pathlib import Path


PATCH_MARKER = '// pbm-gradle-fix: PREFER_PROJECT'

PATCH_BLOCK = """\

// pbm-gradle-fix: PREFER_PROJECT
// 修复 Flutter includeBuild 的 maven 仓库命名冲突（Gradle 8.x + PREFER_SETTINGS 不兼容）
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.PREFER_PROJECT)
    repositories {
        google()
        mavenCentral()
    }
}
"""


def find_settings_gradle(project_dir: Path) -> Path | None:
    candidates = [
        project_dir / "build" / "flutter" / "android" / "settings.gradle.kts",
        project_dir / "build" / "android" / "settings.gradle.kts",
    ]
    for p in candidates:
        if p.exists():
            return p
    found = list(project_dir.glob("build/**/android/settings.gradle.kts"))
    return found[0] if found else None


def fix_settings_gradle(settings_file: Path) -> bool:
    content = settings_file.read_text(encoding='utf-8')

    if PATCH_MARKER in content:
        print(f"✓ {settings_file.name} 已应用补丁，跳过")
        return True

    # 备份
    backup = settings_file.with_suffix('.kts.orig')
    if not backup.exists():
        shutil.copy2(settings_file, backup)
        print(f"✓ 已备份到 {backup.name}")

    settings_file.write_text(content + PATCH_BLOCK, encoding='utf-8')
    print(f"✓ 已修复 {settings_file}")
    return True


def main():
    print("=== 修复 Flutter Android settings.gradle.kts ===\n")

    project_dir = Path(__file__).resolve().parent.parent
    settings_file = find_settings_gradle(project_dir)

    if not settings_file:
        print("错误: 未找到 settings.gradle.kts", file=sys.stderr)
        print("请先运行 flet build apk（即使失败也会生成 build/ 目录）", file=sys.stderr)
        sys.exit(1)

    print(f"找到文件: {settings_file}\n")

    if not fix_settings_gradle(settings_file):
        sys.exit(1)

    print("\n✓ 修复完成！可以直接用 flutter 构建（跳过重复的 flet 前置步骤）：")
    flutter_dir = settings_file.parent.parent
    print(f"  cd {flutter_dir}")
    print("  flutter build apk --release")


if __name__ == '__main__':
    main()
