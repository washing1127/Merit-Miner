"""Streak calculation, check-in, makeup, and penalty logic."""

from datetime import datetime, timedelta

from loguru import logger

from core.config import MAKEUP_WINDOW_DAYS
from models.checkin import CheckinRecord, CheckinStatus
from models.task import Task, TaskType
from repositories.task_repo import (
    create_checkin,
    get_checkin_for_date,
    get_checkin_records,
    get_task_by_id,
    get_unchecked_dates,
    update_task,
)
from services.repeat_service import is_task_due_on, get_due_dates_between


def _normalize_date(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


PENALTY_LOOKBACK_DAYS = 7


async def calculate_streak(task_id: int) -> int:
    """Calculate current consecutive days streak for a task.

    Walks backward from today; stops at the first day with no valid check-in.
    Both NORMAL and OVERDUE statuses count as valid.
    """
    records = await get_checkin_records(task_id)
    if not records:
        return 0

    checked_dates: set[str] = set()
    for r in records:
        if r.status != CheckinStatus.MISSED:
            checked_dates.add(_normalize_date(r.checkin_date).strftime("%Y-%m-%d"))

    today = _normalize_date(datetime.now())
    streak = 0
    for i in range(len(checked_dates) + 1):
        check_date = today - timedelta(days=i)
        date_str = check_date.strftime("%Y-%m-%d")
        if date_str in checked_dates:
            streak += 1
        else:
            break
    return streak


async def checkin_today(task_id: int) -> tuple[bool, str]:
    """Check in *task_id* for today. Returns (success, message)."""
    today = _normalize_date(datetime.now())

    existing = await get_checkin_for_date(task_id, today)
    if existing:
        return False, "今天已经打过卡了"

    task = await get_task_by_id(task_id)
    if not task:
        return False, "任务不存在"

    # --- Create the check-in record ---
    record = CheckinRecord(
        task_id=task_id,
        checkin_date=today,
        status=CheckinStatus.NORMAL,
        actual_time=datetime.now(),
    )
    await create_checkin(record)

    # --- Update streak ---
    streak = await calculate_streak(task_id)
    task.current_streak = streak
    if streak > task.max_streak:
        task.max_streak = streak
    task.last_completed_date = datetime.now()
    await update_task(task)

    # --- Penalty check ---
    penalty_msg = ""
    if task.penalty_enabled and task.penalty_amount > 0:
        penalty_msg = await _apply_penalty(task)

    reward_msg = ""
    if task.task_type == TaskType.REWARD and task.reward_amount > 0:
        reward_msg = f"，奖金 +{task.reward_amount:.2f}"

    return True, f"打卡成功！连续 {streak} 天{reward_msg}{penalty_msg}"


async def _apply_penalty(task: Task) -> str:
    """Check for missed due dates and apply penalties.

    Returns a message describing penalties applied (empty string if none).
    """
    today = _normalize_date(datetime.now())

    # Find the last check-in date before today
    last_checkin_date: datetime | None = None
    for i in range(1, PENALTY_LOOKBACK_DAYS + 1):
        candidate = today - timedelta(days=i)
        record = await get_checkin_for_date(task.id, candidate)
        if record is not None:
            last_checkin_date = candidate
            break

    # Determine range to check for missed dates
    if last_checkin_date is None:
        # First check-in ever — check from task creation
        search_start = _normalize_date(task.created_at)
    else:
        search_start = last_checkin_date + timedelta(days=1)

    search_end = today - timedelta(days=1)
    if search_start > search_end:
        return ""

    missed_dates = get_due_dates_between(task, search_start, search_end)
    if not missed_dates:
        return ""

    # Apply penalties
    from services.logic_service import record_penalty
    total_penalty = 0.0
    for missed_date in missed_dates:
        # Skip if a check-in already exists for that date
        existing = await get_checkin_for_date(task.id, missed_date)
        if existing is not None:
            continue
        await record_penalty(
            amount=task.penalty_amount,
            task_title=task.title,
            penalty_date=missed_date,
        )
        total_penalty += task.penalty_amount

    if total_penalty > 0:
        return f"，断签惩罚 -{total_penalty:.2f}（{len(missed_dates)} 天）"
    return ""


async def makeup_checkin(task_id: int, target_date: datetime) -> tuple[bool, str]:
    """Make up a missed check-in for *target_date*."""
    target = _normalize_date(target_date)
    today = _normalize_date(datetime.now())

    days_diff = (today - target).days
    if days_diff < 0:
        return False, "不能补打卡未来的日期"
    if days_diff >= MAKEUP_WINDOW_DAYS:
        return False, f"只能补打卡最近 {MAKEUP_WINDOW_DAYS} 天"

    existing = await get_checkin_for_date(task_id, target)
    if existing:
        return False, f"{target.strftime('%m-%d')} 已有打卡记录"

    task = await get_task_by_id(task_id)
    if not task:
        return False, "任务不存在"

    record = CheckinRecord(
        task_id=task_id,
        checkin_date=target,
        status=CheckinStatus.OVERDUE,
        actual_time=datetime.now(),
    )
    await create_checkin(record)

    streak = await calculate_streak(task_id)
    task.current_streak = streak
    if streak > task.max_streak:
        task.max_streak = streak
    task.last_completed_date = datetime.now()
    await update_task(task)

    reward_msg = ""
    if task.task_type == TaskType.REWARD and task.reward_amount > 0:
        reward_msg = f"，奖金 +{task.reward_amount:.2f}"

    return True, f"补卡成功（{target.strftime('%m-%d')}），连续 {streak} 天{reward_msg}"


async def get_available_makeup_dates(task_id: int) -> list[datetime]:
    return await get_unchecked_dates(task_id, MAKEUP_WINDOW_DAYS)
