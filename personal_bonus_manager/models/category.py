"""分类模型定义。"""

from typing import Optional

from sqlmodel import Field, SQLModel


class Category(SQLModel, table=True):
    """分类表：存储账单分类信息。"""
    __tablename__ = "categories"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    is_default: bool = Field(default=False)
