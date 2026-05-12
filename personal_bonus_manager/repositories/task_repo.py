"""Task data access layer: CRUD for tasks and check-in records."""

from datetime import datetime, timedelta
from typing import Optional

from loguru import logger
from sqlmodel import select, col

from core.database import get_session
from models.checkin import CheckinRecord, CheckinStatus
from models.task import Task, TaskPriority
from services.repeat_service import is_task_due_on


async def create_task(task: Task) -> Task:
    async with get_session() as session:
        session.add(task)
        await session.flush()
        await session.refresh(task)
        logger.info(f"Created task: {task.title} (id={task.id})")
        return task


async def get_all_tasks(enabled_only: bool = True) -> list[Task]:
    async with get_session() as session:
        stmt = select(Task)
        if enabled_only:
            stmt = stmt.where(Task.is_enabled == True)  # noqa: E712
        stmt = stmt.order_by(col(Task.sort_order), col(Task.priority).desc(), col(Task.created_at).desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_task_by_id(task_id: int) -> Optional[Task]:
    async with get_session() as session:
        return await session.get(Task, task_id)


async def update_task(task: Task) -> Task:
    async with get_session() as session:
        merged = await session.merge(task)
        await session.flush()
        await session.refresh(merged)
        logger.info(f"Updated task: {merged.title} (id={merged.id})")
        return merged


async def delete_task(task_id: int) -> bool:
    async with get_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return False
        stmt = select(CheckinRecord).where(CheckinRecord.task_id == task_id)
        result = await session.execute(stmt)
        for record in result.scalars().all():
            await session.delete(record)
        await session.delete(task)
        logger.info(f"Deleted task & records: {task.title} (id={task_id})")
        return True


# ------------------------------------------------------------------ #
# Today / Overdue queries
# ------------------------------------------------------------------ #

async def get_tasks_due_on(date: datetime) -> list[Task]:
    """Return enabled tasks that are due on *date*, with their latest check-in info."""
    all_tasks = await get_all_tasks(enabled_only=True)
    return [t for t in all_tasks if is_task_due_on(t, date)]


async def get_overdue_tasks() -> list[Task]:
    """Return tasks that had a due date < today but no completed check-in on that date."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    all_tasks = await get_all_tasks(enabled_only=True)

    overdue: list[Task] = []
    for task in all_tasks:
        # Find the most recent due date before today
        for i in range(1, 31):  # look back up to 30 days
            candidate = today - timedelta(days=i)
            if candidate < task.created_at.replace(hour=0, minute=0, second=0, microsecond=0):
                break
            if is_task_due_on(task, candidate):
                # Check if completed on that date
                existing = await get_checkin_for_date(task.id, candidate)
                if existing is None:
                    overdue.append(task)
                break  # Only report the most recent missed due date
    return overdue


async def get_tasks_sorted(sort_by: str = "priority") -> list[Task]:
    """Return all enabled tasks sorted by *sort_by*."""
    tasks = await get_all_tasks(enabled_only=True)
    if sort_by == "priority":
        tasks.sort(key=lambda t: (t.priority, t.created_at), reverse=True)
    elif sort_by == "created":
        tasks.sort(key=lambda t: t.created_at, reverse=True)
    elif sort_by == "title":
        tasks.sort(key=lambda t: t.title.lower())
    # "manual" — use sort_order
    return tasks


async def update_task_sort_order(task_id: int, order: int) -> bool:
    async with get_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return False
        task.sort_order = order
        await session.flush()
        return True


# ------------------------------------------------------------------ #
# Check-in record helpers
# ------------------------------------------------------------------ #

async def get_checkin_records(
    task_id: int,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> list[CheckinRecord]:
    async with get_session() as session:
        stmt = select(CheckinRecord).where(CheckinRecord.task_id == task_id)
        if start_date:
            stmt = stmt.where(CheckinRecord.checkin_date >= start_date)
        if end_date:
            stmt = stmt.where(CheckinRecord.checkin_date <= end_date)
        stmt = stmt.order_by(col(CheckinRecord.checkin_date).desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_checkin_for_date(task_id: int, target_date: datetime) -> Optional[CheckinRecord]:
    date_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    date_end = date_start + timedelta(days=1)
    async with get_session() as session:
        stmt = (
            select(CheckinRecord)
            .where(CheckinRecord.task_id == task_id)
            .where(CheckinRecord.checkin_date >= date_start)
            .where(CheckinRecord.checkin_date < date_end)
        )
        result = await session.execute(stmt)
        return result.scalars().first()


async def create_checkin(record: CheckinRecord) -> CheckinRecord:
    async with get_session() as session:
        session.add(record)
        await session.flush()
        await session.refresh(record)
        logger.info(
            f"Checkin created: task_id={record.task_id}, "
            f"date={record.checkin_date.date()}, status={record.status}"
        )
        return record


async def get_unchecked_dates(task_id: int, window_days: int = 3) -> list[datetime]:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    unchecked: list[datetime] = []
    for i in range(window_days):
        target_date = today - timedelta(days=i)
        existing = await get_checkin_for_date(task_id, target_date)
        if existing is None:
            unchecked.append(target_date)
    return unchecked
