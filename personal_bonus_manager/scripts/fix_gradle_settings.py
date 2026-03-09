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

import hashlib
import re
import shutil
import stat
import sys
from pathlib import Path


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


# ── 恢复 gradlew 原始 wrapper + 降级 AGP ─────────────────────────────────────

# AGP 8.8.0 需要 Gradle >= 8.10.2（对 8.14.x 无上限限制）
_TARGET_AGP = "8.8.0"
# 系统无合适 Gradle 时的回退版本（flet 0.81.0 原始生成值，让 wrapper 从网络下载）
_TARGET_GRADLE = "8.13"
# 接受系统 Gradle 的最低版本（元组，用于版本比较）
_MIN_GRADLE_VERSION = (8, 10)

# 系统 Gradle 安装路径候选（按优先级）
_SYSTEM_GRADLE_CANDIDATES = [
    Path("/opt/gradle-8.14.3"),
    Path("/opt/gradle-8.14"),
    Path("/opt/gradle-8.13"),
    Path("/opt/gradle"),
    Path("/usr/local/gradle"),
    Path("/usr/share/gradle"),
]


def _parse_version(version_str: str) -> tuple[int, ...]:
    """将 '8.14.3' 解析为 (8, 14, 3)。"""
    try:
        return tuple(int(x) for x in version_str.split("."))
    except ValueError:
        return (0,)


def _get_system_gradle() -> tuple[Path, str] | None:
    """返回 (Gradle安装路径, 版本号)，仅当版本 >= _MIN_GRADLE_VERSION 时返回。"""
    import subprocess
    for candidate in _SYSTEM_GRADLE_CANDIDATES:
        gradle_bin = candidate / "bin" / "gradle"
        if not gradle_bin.is_file():
            continue
        try:
            result = subprocess.run(
                [str(gradle_bin), "--version"],
                capture_output=True, text=True, timeout=15,
            )
            m = re.search(r'Gradle\s+([\d.]+)', result.stdout)
            if not m:
                continue
            version = m.group(1)
            if _parse_version(version)[:2] >= _MIN_GRADLE_VERSION:
                return candidate, version
            # 版本太旧，跳过
        except Exception:
            pass
    return None


def _gradle_dist_hash(url: str) -> str:
    """复现 Gradle PathAssembler 的哈希算法：MD5 → BigInteger → base36。"""
    digest = hashlib.md5(url.encode('ascii')).digest()
    num = int.from_bytes(digest, 'big')
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    if num == 0:
        return "0"
    result = ""
    while num:
        result = chars[num % 36] + result
        num //= 36
    return result


def setup_local_gradle_cache(gradle_home: Path, gradle_version: str, dist_type: str) -> bool:
    """
    构造 ~/.gradle/wrapper/dists/ 缓存目录，使 Gradle Wrapper 直接使用
    系统安装的 Gradle，无需下载。

    缓存结构与 Gradle 内部一致：
      ~/.gradle/wrapper/dists/gradle-VERSION-TYPE/HASH/gradle-VERSION/  ← 符号链接
      ~/.gradle/wrapper/dists/gradle-VERSION-TYPE/HASH/gradle-VERSION-TYPE.zip.ok
    """
    dist_url = (
        f"https://services.gradle.org/distributions/"
        f"gradle-{gradle_version}-{dist_type}.zip"
    )
    hash_str = _gradle_dist_hash(dist_url)

    gradle_user_home = Path.home() / ".gradle"
    dist_name = f"gradle-{gradle_version}-{dist_type}"
    hash_dir = gradle_user_home / "wrapper" / "dists" / dist_name / hash_str
    extracted_dir = hash_dir / f"gradle-{gradle_version}"

    if extracted_dir.exists() or extracted_dir.is_symlink():
        print(f"✓ Gradle {gradle_version} wrapper 缓存已存在，跳过")
        return True

    hash_dir.mkdir(parents=True, exist_ok=True)
    extracted_dir.symlink_to(gradle_home)

    # Gradle wrapper 检查 .ok 标记文件
    ok_file = hash_dir / f"{dist_name}.zip.ok"
    ok_file.touch()

    print(
        f"✓ 已建立 Gradle {gradle_version} 本地缓存：\n"
        f"  {extracted_dir} → {gradle_home}"
    )
    return True


# 标准 Gradle Wrapper shell 脚本（与 Gradle 版本无关）
_GRADLEW_CONTENT = r"""#!/bin/sh
#
# Copyright © 2015-2021 the original authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

app_path=$0
while
  APP_HOME=${app_path%"${app_path##*/}"}
  [ -h "$app_path" ]
do
  ls=$( ls -ld "$app_path" )
  link=${ls#*' -> '}
  case $link in
    /*)   app_path=$link ;;
    *)    app_path=$APP_HOME$link ;;
  esac
done
APP_HOME=$( cd "${APP_HOME:-./}" && pwd -P ) || exit
APP_NAME="Gradle"
APP_BASE_NAME=${0##*/}

DEFAULT_JVM_OPTS='"-Xmx64m" "-Xms64m"'

MAX_FD=maximum

warn () { echo "$*"; }
die () { echo; echo "$*"; echo; exit 1; }

cygwin=false
msys=false
darwin=false
nonstop=false
case "$( uname )" in
  CYGWIN* )        cygwin=true  ;;
  Darwin* )        darwin=true  ;;
  MSYS* | MINGW* ) msys=true    ;;
  NONSTOP* )       nonstop=true ;;
esac

CLASSPATH=$APP_HOME/gradle/wrapper/gradle-wrapper.jar

if [ -n "$JAVA_HOME" ] ; then
  if [ -x "$JAVA_HOME/jre/sh/java" ] ; then
    JAVACMD=$JAVA_HOME/jre/sh/java
  else
    JAVACMD=$JAVA_HOME/bin/java
  fi
  if [ ! -x "$JAVACMD" ] ; then
    die "ERROR: JAVA_HOME is set to an invalid directory: $JAVA_HOME"
  fi
else
  JAVACMD=java
  which java >/dev/null 2>&1 || die "ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH."
fi

if ! "$cygwin" && ! "$darwin" && ! "$nonstop" ; then
  case $MAX_FD in
    max*) MAX_FD=$( ulimit -H -n ) || warn "Could not query maximum file descriptor limit" ;;
  esac
  case $MAX_FD in
    '' | soft) ;;
    *) ulimit -n "$MAX_FD" || warn "Could not set maximum file descriptor limit to $MAX_FD" ;;
  esac
fi

eval set -- $DEFAULT_JVM_OPTS $JAVA_OPTS $GRADLE_OPTS "\"-Dorg.gradle.appname=$APP_BASE_NAME\"" -classpath "\"$CLASSPATH\"" org.gradle.wrapper.GradleWrapperMain '"$@"'

exec "$JAVACMD" "$@"
"""


def restore_gradlew(android_dir: Path) -> bool:
    """恢复 gradlew 为标准 Gradle Wrapper 脚本（从备份或重建）。"""
    gradlew = android_dir / "gradlew"
    backup = gradlew.with_suffix('.orig')
    if backup.exists():
        shutil.copy2(backup, gradlew)
        print(f"✓ gradlew: 已从备份恢复")
    else:
        # 检查是否是被破坏的脚本（只有一两行，不是标准 wrapper）
        if gradlew.exists():
            content = gradlew.read_text(encoding='utf-8', errors='replace')
            if len(content.splitlines()) < 10:
                gradlew.write_text(_GRADLEW_CONTENT.lstrip(), encoding='utf-8')
                print(f"✓ gradlew: 检测到破损脚本，已重写为标准 Gradle Wrapper")
            else:
                print(f"✓ gradlew: 内容正常，保持原样")
        else:
            gradlew.write_text(_GRADLEW_CONTENT.lstrip(), encoding='utf-8')
            print(f"✓ gradlew: 已重建标准 Gradle Wrapper 脚本")
    gradlew.chmod(gradlew.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return True


def fix_gradle_wrapper_version(android_dir: Path) -> bool:
    """将 gradle-wrapper.properties 更新为系统安装的 Gradle 版本，并建立本地缓存。
    若无本地 Gradle，将 distributionUrl 改为国内镜像以避免超时。"""
    wrapper_props = android_dir / "gradle" / "wrapper" / "gradle-wrapper.properties"
    if not wrapper_props.exists():
        return True
    content = wrapper_props.read_text(encoding='utf-8')
    m = re.search(r'gradle-([\d.]+)-(bin|all)\.zip', content)
    if not m:
        return True
    current = m.group(1)
    dist_type = m.group(2)  # "bin" 或 "all"

    # 检测系统 Gradle
    sys_gradle = _get_system_gradle()
    if sys_gradle:
        gradle_home, detected_version = sys_gradle
        target = detected_version
    else:
        gradle_home = None
        target = _TARGET_GRADLE

    # 构造新的 distributionUrl
    if gradle_home:
        new_dist_url = None  # 有本地 Gradle，仅改版本即可
    else:
        # 国内镜像（华为云，有完整 Gradle 发行包）
        new_dist_url = (
            f"https://repo.huaweicloud.com/gradle/"
            f"gradle-{target}-{dist_type}.zip"
        )

    new_content = content
    # 更新版本号
    if current != target:
        new_content = re.sub(
            r'(gradle-)[\d.]+(-(?:bin|all)\.zip)',
            rf'\g<1>{target}\2',
            new_content,
        )
        print(f"✓ Gradle wrapper: {current} → {target}")
    else:
        print(f"✓ Gradle wrapper 已是 {target}，跳过版本更新")

    # 更新 distributionUrl（替换为国内镜像）
    if new_dist_url:
        if new_dist_url not in new_content:
            new_content = re.sub(
                r'^distributionUrl=.*$',
                f'distributionUrl={new_dist_url}',
                new_content,
                flags=re.MULTILINE,
            )
            print(f"✓ distributionUrl → 华为云镜像（避免 services.gradle.org 超时）")

    if new_content != content:
        wrapper_props.write_text(new_content, encoding='utf-8')

    # 为系统 Gradle 建立 wrapper 缓存（避免网络下载）
    if gradle_home:
        setup_local_gradle_cache(gradle_home, target, dist_type)
    else:
        print(f"  镜像地址: {new_dist_url}")

    return True


def fix_agp_version(android_dir: Path) -> bool:
    """将 AGP 版本降至 8.8.0（与 Gradle 8.10.2+ / 8.14.x 兼容）。"""
    settings = android_dir / "settings.gradle.kts"
    if not settings.exists():
        return True
    content = settings.read_text(encoding='utf-8')
    m = re.search(r'id\("com\.android\.application"\)\s+version\s+"([\d.]+)"', content)
    if not m:
        print("警告: settings.gradle.kts 中未找到 AGP 版本，跳过")
        return True
    current = m.group(1)
    parts = list(map(int, current.split('.')))
    target_parts = list(map(int, _TARGET_AGP.split('.')))
    if parts <= target_parts:
        print(f"✓ AGP {current} 已兼容 Gradle {_TARGET_GRADLE}，跳过")
        return True
    new_content = re.sub(
        r'(id\("com\.android\.application"\)\s+version\s+")[\d.]+"',
        rf'\g<1>{_TARGET_AGP}"',
        content,
    )
    settings.write_text(new_content, encoding='utf-8')
    print(f"✓ AGP: {current} → {_TARGET_AGP}（兼容 Gradle {_TARGET_GRADLE}，无需下载）")
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

    # 步骤 3: 恢复 gradlew（撤销之前的错误修改）
    ok3 = restore_gradlew(android_dir)

    # 步骤 4: 更新 Gradle wrapper 为系统版本并建立本地缓存
    ok4 = fix_gradle_wrapper_version(android_dir)

    # 步骤 5: 降级 AGP 至 8.8.0（与 Gradle 8.10.2+ 兼容）
    ok5 = fix_agp_version(android_dir)

    if not (ok1 and ok2 and ok3 and ok4 and ok5):
        sys.exit(1)

    print("\n✓ 修复完成！现在运行：")
    flutter_dir = android_dir.parent
    print(f"  cd {flutter_dir}")
    print("  flutter build apk --release")
    print()
    print("注意：此修复改动了 Flutter SDK 文件。如需还原：")
    tools_settings = flutter_sdk / "packages" / "flutter_tools" / "gradle" / "settings.gradle.kts"
    print(f"  cp {tools_settings}.orig {tools_settings}")


if __name__ == '__main__':
    main()
