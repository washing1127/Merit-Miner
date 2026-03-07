"""任务模型定义。"""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class TaskType:
    """任务类型常量。"""
    NORMAL = 0   # 普通任务（不奖励奖金）
    REWARD = 1   # 奖励任务（打卡可获得奖金）


class Task(SQLModel, table=True):
    """任务表：存储用户创建的任务信息。"""
    __tablename__ = "tasks"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    reward_amount: float = Field(default=0.0)
    task_type: int = Field(default=TaskType.NORMAL)
    current_streak: int = Field(default=0)
    max_streak: int = Field(default=0)
    last_completed_date: Optional[datetime] = Field(default=None)
    is_enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.now)

    # TODO: v1.1 - 连续目标字段，前端暂不可见
    # streak_target: Optional[int] = Field(default=None)
    # streak_bonus: float = Field(default=0.0)  # 达标额外奖金
