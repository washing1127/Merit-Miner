"""Repeat rule engine: determines if a task is due on a given date."""

from datetime import datetime, timedelta
from typing import Optional

from models.task import Task, RepeatType


def _normalize(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def is_task_due_on(task: Task, date: datetime) -> bool:
    """Check whether *task* should be checked in on *date*."""
    if not task.is_enabled:
        return False

    date = _normalize(date)
    created = _normalize(task.created_at)

    # Task not yet created on that date
    if date < created:
        return False

    # Repeat-until deadline
    if task.repeat_until is not None and date > _normalize(task.repeat_until):
        return False

    rtype = task.repeat_type

    if rtype == RepeatType.NONE:
        target = _normalize(task.due_date) if task.due_date else created
        return date == target

    if rtype == RepeatType.DAILY:
        delta_days = (date - created).days
        return delta_days >= 0 and delta_days % task.repeat_interval == 0

    if rtype == RepeatType.WEEKDAYS:
        return date.weekday() < 5  # Mon=0 .. Fri=4

    if rtype == RepeatType.WEEKLY:
        if not task.repeat_days:
            return False
        try:
            target_days = {int(d.strip()) for d in task.repeat_days.split(",") if d.strip()}
        except ValueError:
            return False
        return date.weekday() in target_days

    if rtype == RepeatType.MONTHLY:
        # repeat_interval is the target day-of-month
        target_day = task.repeat_interval if task.repeat_interval > 0 else created.day
        return date.day == target_day

    return False


def get_previous_due_date(task: Task, from_date: datetime) -> Optional[datetime]:
    """Return the most recent due date on or before *from_date* (excluding today).

    Returns None if no previous due date exists (e.g. task created today).
    """
    from_date = _normalize(from_date)
    if not task.is_enabled:
        return None

    # Search backwards up to 90 days — plenty of margin
    for i in range(1, 91):
        candidate = from_date - timedelta(days=i)
        if candidate < _normalize(task.created_at):
            return None
        if is_task_due_on(task, candidate):
            return candidate
    return None


def get_due_dates_between(task: Task, start: datetime, end: datetime) -> list[datetime]:
    """Return all dates in [start, end] (inclusive) that *task* is due on."""
    start = _normalize(start)
    end = _normalize(end)
    if end < start:
        return []

    dates: list[datetime] = []
    current = start
    while current <= end:
        if is_task_due_on(task, current):
            dates.append(current)
        current += timedelta(days=1)
    return dates
