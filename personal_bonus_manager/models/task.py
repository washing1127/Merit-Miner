"""Task model with repeat rules, priority, and penalty support."""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class TaskType:
    """Task type constants."""
    NORMAL = 0
    REWARD = 1


class TaskPriority:
    """Priority constants. Higher = more important."""
    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class RepeatType:
    """Repeat rule constants."""
    NONE = "none"          # one-time task
    DAILY = "daily"        # every N days
    WEEKLY = "weekly"      # on specified weekdays
    MONTHLY = "monthly"    # on a specific day each month
    WEEKDAYS = "weekdays"  # Monday-Friday


PRIORITY_LABELS = {0: "无", 1: "低", 2: "中", 3: "高"}
PRIORITY_COLORS = {0: "#9E9E9E", 1: "#4CAF50", 2: "#FF9800", 3: "#F44336"}
REPEAT_LABELS = {
    "none": "不重复",
    "daily": "每天",
    "weekly": "每周",
    "monthly": "每月",
    "weekdays": "工作日",
}
WEEKDAY_LABELS = ["一", "二", "三", "四", "五", "六", "日"]


class Task(SQLModel, table=True):
    __tablename__ = "tasks"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    description: str = Field(default="")
    reward_amount: float = Field(default=0.0)
    task_type: int = Field(default=TaskType.NORMAL)
    priority: int = Field(default=TaskPriority.NONE)
    current_streak: int = Field(default=0)
    max_streak: int = Field(default=0)
    last_completed_date: Optional[datetime] = Field(default=None)
    # Repeat rules
    repeat_type: str = Field(default=RepeatType.DAILY)
    repeat_interval: int = Field(default=1)
    repeat_days: str = Field(default="")     # "0,2,4" for Mon/Wed/Fri
    repeat_until: Optional[datetime] = Field(default=None)
    # For one-time tasks
    due_date: Optional[datetime] = Field(default=None)
    # Streak penalty
    penalty_enabled: bool = Field(default=False)
    penalty_amount: float = Field(default=0.0)
    # State
    is_enabled: bool = Field(default=True)
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)
