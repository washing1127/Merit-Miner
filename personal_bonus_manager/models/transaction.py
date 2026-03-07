"""账单/交易模型定义。"""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class TransactionType:
    """账单类型常量。"""
    EXPENSE = 0   # 支出
    INCOME = 1    # 收入（预留）


class Transaction(SQLModel, table=True):
    """账单表：记录用户的收支信息。"""
    __tablename__ = "transactions"

    id: Optional[int] = Field(default=None, primary_key=True)
    amount: float
    type: int = Field(default=TransactionType.EXPENSE)
    category_id: int = Field(foreign_key="categories.id", index=True)
    description: str = Field(default="")
    is_bonus_related: bool = Field(default=False, index=True)
    transaction_date: datetime = Field(default_factory=datetime.now, index=True)
    ai_confidence: float = Field(default=1.0)
    is_verified: bool = Field(default=False)
