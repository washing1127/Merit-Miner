"""打卡记录模型定义。"""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class CheckinStatus:
    """打卡状态常量。"""
    NORMAL = "normal"    # 正常打卡
    OVERDUE = "overdue"  # 补打卡（逾期完成）
    MISSED = "missed"    # 未打卡（系统自动标记）


class CheckinRecord(SQLModel, table=True):
    """打卡记录表：记录每次打卡的详细信息。"""
    __tablename__ = "checkin_records"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="tasks.id", index=True)
    checkin_date: datetime = Field(index=True)
    status: str = Field(default=CheckinStatus.NORMAL)
    actual_time: datetime = Field(default_factory=datetime.now)
