"""简单加密工具。MVP 阶段使用 base64 混淆存储 API Key。

注意：base64 不是真正的加密，仅防止明文泄露。
后续版本可接入 flutter_secure_storage 或 keyring 实现系统级安全存储。
"""

import base64
from pathlib import Path

from loguru import logger

from core.config import API_KEY_FILE


def encode_key(raw_key: str) -> str:
    """将 API Key 进行 base64 编码。"""
    return base64.b64encode(raw_key.encode("utf-8")).decode("utf-8")


def decode_key(encoded_key: str) -> str:
    """将 base64 编码的 API Key 解码。"""
    return base64.b64decode(encoded_key.encode("utf-8")).decode("utf-8")


def save_api_key(raw_key: str) -> None:
    """将 API Key 编码后存储到文件。"""
    encoded = encode_key(raw_key)
    API_KEY_FILE.write_text(encoded, encoding="utf-8")
    logger.info("API Key 已保存")


def load_api_key() -> str:
    """从文件加载并解码 API Key。"""
    if not API_KEY_FILE.exists():
        return ""
    try:
        encoded = API_KEY_FILE.read_text(encoding="utf-8").strip()
        if not encoded:
            return ""
        return decode_key(encoded)
    except Exception as e:
        logger.warning(f"加载 API Key 失败: {e}")
        return ""


def delete_api_key() -> None:
    """删除存储的 API Key 文件。"""
    if API_KEY_FILE.exists():
        API_KEY_FILE.unlink()
        logger.info("API Key 已删除")
