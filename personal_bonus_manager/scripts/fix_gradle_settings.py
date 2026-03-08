#!/usr/bin/env python3
"""
修复 flet build 生成的 Flutter Android 项目中 settings.gradle.kts 的
Gradle 仓库冲突问题。

错误原因：
  Flutter 3.x 在 settings.gradle.kts 里将 dependencyResolutionManagement 设为
  FAIL_ON_PROJECT_REPOS，但同时又在 settings 文件中声明了 maven 仓库，
  Gradle 8.x 对此严格报错。

修复策略：
  将 FAIL_ON_PROJECT_REPOS 改为 PREFER_SETTINGS，允许 settings 文件
  额外声明仓库而不报错。
"""

import re
import shutil
import sys
from pathlib import Path


def find_settings_gradle(project_dir: Path) -> Path | None:
    """找到生成的 Flutter 项目里的 settings.gradle.kts。"""
    candidates = [
        project_dir / "build" / "flutter" / "android" / "settings.gradle.kts",
        project_dir / "build" / "android" / "settings.gradle.kts",
    ]
    for p in candidates:
        if p.exists():
            return p
    # 宽泛查找
    found = list(project_dir.glob("build/**/android/settings.gradle.kts"))
    return found[0] if found else None


def fix_settings_gradle(settings_file: Path) -> bool:
    """修复 repositoriesMode 冲突。"""
    content = settings_file.read_text(encoding='utf-8')

    # 检查是否已修复
    if 'PREFER_SETTINGS' in content and 'FAIL_ON_PROJECT_REPOS' not in content:
        print(f"✓ {settings_file.name} 已是正确配置，跳过")
        return True

    original = content

    # 修复 1：将 FAIL_ON_PROJECT_REPOS 改为 PREFER_SETTINGS
    content = content.replace(
        'RepositoriesMode.FAIL_ON_PROJECT_REPOS',
        'RepositoriesMode.PREFER_SETTINGS',
    )

    # 修复 2：处理 Groovy 风格的 repositoriesMode 设置（有些版本用不同写法）
    content = re.sub(
        r'repositoriesMode\.set\s*\(\s*RepositoriesMode\.FAIL_ON_PROJECT_REPOS\s*\)',
        'repositoriesMode.set(RepositoriesMode.PREFER_SETTINGS)',
        content,
    )

    if content == original:
        print(f"警告: 未找到 FAIL_ON_PROJECT_REPOS，检查文件内容...")
        # 打印关键行辅助诊断
        for i, line in enumerate(content.splitlines(), 1):
            if any(kw in line for kw in ['repositoriesMode', 'maven', 'FAIL', 'PREFER']):
                print(f"  L{i}: {line}")
        return False

    # 备份
    backup = settings_file.with_suffix('.kts.orig')
    if not backup.exists():
        shutil.copy2(settings_file, backup)
        print(f"✓ 已备份到 {backup.name}")

    settings_file.write_text(content, encoding='utf-8')
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

    print("\n✓ 修复完成！")
    print("现在可以直接运行 Gradle 构建（无需重新生成项目）：")
    flutter_dir = settings_file.parent.parent
    print(f"  cd {flutter_dir}")
    print("  flutter build apk --release")


if __name__ == '__main__':
    main()
