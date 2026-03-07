"""任务数据访问层。封装任务和打卡记录的 CRUD 操作。"""

from datetime import datetime, timedelta
from typing import Optional

from loguru import logger
from sqlmodel import select, col

from core.database import get_session
from models.checkin import CheckinRecord, CheckinStatus
from models.task import Task


async def create_task(task: Task) -> Task:
    """创建新任务。"""
    async with get_session() as session:
        session.add(task)
        await session.flush()
        await session.refresh(task)
        logger.info(f"创建任务: {task.title} (id={task.id})")
        return task


async def get_all_tasks(enabled_only: bool = True) -> list[Task]:
    """获取所有任务。"""
    async with get_session() as session:
        stmt = select(Task)
        if enabled_only:
            stmt = stmt.where(Task.is_enabled == True)  # noqa: E712
        stmt = stmt.order_by(col(Task.created_at).desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_task_by_id(task_id: int) -> Optional[Task]:
    """根据 ID 获取任务。"""
    async with get_session() as session:
        return await session.get(Task, task_id)


async def update_task(task: Task) -> Task:
    """更新任务。"""
    async with get_session() as session:
        session.add(task)
        await session.flush()
        await session.refresh(task)
        logger.info(f"更新任务: {task.title} (id={task.id})")
        return task


async def delete_task(task_id: int) -> bool:
    """删除任务及其所有打卡记录。"""
    async with get_session() as session:
        task = await session.get(Task, task_id)
        if not task:
            return False
        # 先删除关联的打卡记录
        stmt = select(CheckinRecord).where(CheckinRecord.task_id == task_id)
        result = await session.execute(stmt)
        for record in result.scalars().all():
            await session.delete(record)
        await session.delete(task)
        logger.info(f"删除任务及打卡记录: {task.title} (id={task_id})")
        return True


# --- 打卡记录相关 ---

async def get_checkin_records(
    task_id: int,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> list[CheckinRecord]:
    """获取指定任务的打卡记录。"""
    async with get_session() as session:
        stmt = select(CheckinRecord).where(CheckinRecord.task_id == task_id)
        if start_date:
            stmt = stmt.where(CheckinRecord.checkin_date >= start_date)
        if end_date:
            stmt = stmt.where(CheckinRecord.checkin_date <= end_date)
        stmt = stmt.order_by(col(CheckinRecord.checkin_date).desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_checkin_for_date(
    task_id: int, target_date: datetime
) -> Optional[CheckinRecord]:
    """获取指定任务在指定日期的打卡记录。"""
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
    """创建打卡记录。"""
    async with get_session() as session:
        session.add(record)
        await session.flush()
        await session.refresh(record)
        logger.info(
            f"打卡记录创建: task_id={record.task_id}, "
            f"date={record.checkin_date.date()}, status={record.status}"
        )
        return record


async def get_unchecked_dates(task_id: int, window_days: int = 3) -> list[datetime]:
    """获取指定任务在补卡窗口内未打卡的日期列表。"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    unchecked: list[datetime] = []

    for i in range(window_days):
        target_date = today - timedelta(days=i)
        existing = await get_checkin_for_date(task_id, target_date)
        if existing is None:
            unchecked.append(target_date)

    return unchecked
