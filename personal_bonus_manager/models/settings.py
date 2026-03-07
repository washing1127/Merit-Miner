"""应用设置模型定义。"""

from typing import Optional

from sqlmodel import Field, SQLModel

from core.config import CONFIRM_MODE_SMART


class AppSettings(SQLModel, table=True):
    """设置表：存储应用配置信息。API Key 不存此表，单独加密存储。"""
    __tablename__ = "settings"

    id: Optional[int] = Field(default=None, primary_key=True)
    api_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    model_name: str = Field(default="qwen-plus")
    confirm_mode: int = Field(default=CONFIRM_MODE_SMART)
    currency_symbol: str = Field(default="¥")
