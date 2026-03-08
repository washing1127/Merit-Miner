#!/usr/bin/env python3
"""
修复 cookiecutter 处理二进制文件时的 UnicodeDecodeError。

根本原因：
- binaryornot 0.4.4 对某些二进制文件（如 OTF/TTF 字体）误判为文本
  （这些文件以 ASCII 字节开头，如 OTF 字体以 "OTTO" 开头）
- Jinja2 随后尝试以 UTF-8 读取整个文件，在遇到高字节时崩溃

修复：在 cookiecutter 的 generate_file() 中捕获 UnicodeDecodeError，
回退为直接二进制复制（与检测到二进制文件时的处理方式相同）。
"""

import re
import shutil
import sys
from pathlib import Path


BINARY_EXTENSIONS = {
    '.otf', '.ttf', '.woff', '.woff2', '.eot',  # 字体
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.bmp',  # 图片
    '.mp3', '.mp4', '.wav', '.ogg', '.flac',  # 音频/视频
    '.zip', '.gz', '.tar', '.bz2', '.xz',  # 压缩
    '.pdf', '.so', '.dylib', '.dll', '.exe',  # 其他二进制
}


def find_cookiecutter_generate() -> Path:
    """找到 cookiecutter 的 generate.py 文件路径。"""
    try:
        import cookiecutter.generate as cg
        import inspect
        return Path(inspect.getfile(cg))
    except ImportError:
        print("错误: 找不到 cookiecutter 包，请先安装: pip install cookiecutter", file=sys.stderr)
        sys.exit(1)


def is_already_patched(content: str) -> bool:
    """检查是否已应用补丁。"""
    return 'UnicodeDecodeError' in content and 'binary fallback' in content


def apply_patch(generate_py: Path) -> bool:
    """
    向 generate_file() 函数添加 UnicodeDecodeError 捕获。

    原始代码:
        try:
            tmpl = env.get_template(infile_fwd_slashes)
        except TemplateSyntaxError as exception:
            exception.translated = False
            raise

    打补丁后:
        try:
            tmpl = env.get_template(infile_fwd_slashes)
        except TemplateSyntaxError as exception:
            exception.translated = False
            raise
        except UnicodeDecodeError:  # binary fallback
            shutil.copyfile(infile, outfile)
            shutil.copymode(infile, outfile)
            return
    """
    content = generate_py.read_text(encoding='utf-8')

    if is_already_patched(content):
        print(f"✓ {generate_py} 已应用补丁，跳过")
        return True

    # 匹配 except TemplateSyntaxError 块的末尾（raise 之后）
    old = (
        '        except TemplateSyntaxError as exception:\n'
        '        # Disable translated so that printed exception contains verbose\n'
        '        # information about syntax error location\n'
        '            exception.translated = False\n'
        '            raise\n'
    )
    new = (
        '        except TemplateSyntaxError as exception:\n'
        '        # Disable translated so that printed exception contains verbose\n'
        '        # information about syntax error location\n'
        '            exception.translated = False\n'
        '            raise\n'
        '        except UnicodeDecodeError:  # binary fallback\n'
        '            shutil.copyfile(infile, outfile)\n'
        '            shutil.copymode(infile, outfile)\n'
        '            return\n'
    )

    # 更健壮的匹配方式：查找 raise 后面的位置
    # 匹配格式可能因版本不同而略有差异
    # 查找 TemplateSyntaxError 块后的 raise，插入 UnicodeDecodeError 处理
    # raise 使用 8 空格缩进（与 except 子句对齐）
    search_anchor = 'TemplateSyntaxError'
    block_start = content.find(search_anchor)
    if block_start == -1:
        print("错误: 未找到 TemplateSyntaxError", file=sys.stderr)
        return False

    # 在 TemplateSyntaxError 之后找 raise（8空格缩进）
    for raise_str in ('        raise\n', '            raise\n'):
        idx = content.find(raise_str, block_start)
        if idx != -1:
            break
    else:
        print("错误: 无法定位 TemplateSyntaxError 处理块中的 raise", file=sys.stderr)
        return False

    insert_pos = idx + len(raise_str)
    # 插入代码的缩进与 except 块对齐（4空格 try 块内）
    except_indent = '    '
    body_indent = '        '
    insert_code = (
        f'{except_indent}except UnicodeDecodeError:  # binary fallback\n'
        f'{body_indent}shutil.copyfile(infile, outfile)\n'
        f'{body_indent}shutil.copymode(infile, outfile)\n'
        f'{body_indent}return\n'
    )
    new_content = content[:insert_pos] + insert_code + content[insert_pos:]

    # 备份原文件
    backup = generate_py.with_suffix('.py.orig')
    if not backup.exists():
        shutil.copy2(generate_py, backup)
        print(f"✓ 已备份原文件到 {backup}")

    generate_py.write_text(new_content, encoding='utf-8')
    print(f"✓ 已修复 {generate_py}")
    return True


def patch_binaryornot_extensions(generate_py: Path) -> bool:
    """
    在 is_binary() 调用前先检查文件扩展名，对已知二进制扩展名直接跳过。
    这是第二层防护，避免 binaryornot 误判。
    """
    content = generate_py.read_text(encoding='utf-8')

    if 'BINARY_EXTENSIONS' in content:
        print(f"✓ 扩展名检查已存在，跳过")
        return True

    old = (
        "    # Just copy over binary files. Don't render.\n"
        "    logger.debug(\"Check %s to see if it's a binary\", infile)\n"
        "    if is_binary(infile):\n"
    )
    new = (
        "    # Just copy over binary files. Don't render.\n"
        "    logger.debug(\"Check %s to see if it's a binary\", infile)\n"
        "    # Pre-check by extension for file types binaryornot may misdetect\n"
        "    _BINARY_EXTENSIONS = {\n"
        "        '.otf', '.ttf', '.woff', '.woff2', '.eot',\n"
        "        '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.bmp',\n"
        "        '.mp3', '.mp4', '.wav', '.ogg', '.so', '.dylib', '.dll',\n"
        "    }\n"
        "    import os as _os\n"
        "    if _os.path.splitext(infile)[1].lower() in _BINARY_EXTENSIONS or is_binary(infile):\n"
    )

    new_content = content.replace(old, new)
    if new_content == content:
        print("警告: 未找到 is_binary 调用位置，跳过扩展名补丁")
        return False

    generate_py.write_text(new_content, encoding='utf-8')
    print(f"✓ 已添加扩展名预检查到 {generate_py}")
    return True


def main():
    print("=== 修复 cookiecutter 二进制文件处理 ===\n")

    generate_py = find_cookiecutter_generate()
    print(f"找到 cookiecutter: {generate_py}\n")

    # 应用两层修复
    ok1 = patch_binaryornot_extensions(generate_py)
    ok2 = apply_patch(generate_py)

    if ok1 or ok2:
        print("\n✓ 修复完成！现在可以重新运行 flet build apk")
    else:
        print("\n✗ 修复失败，请手动检查", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
