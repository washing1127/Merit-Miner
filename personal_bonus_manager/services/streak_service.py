"""连续打卡计算与补卡逻辑服务。"""

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


def _normalize_date(dt: datetime) -> datetime:
    """将 datetime 归一化到当天 00:00:00。"""
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


async def calculate_streak(task_id: int) -> int:
    """计算指定任务的当前连续打卡天数。

    从今天往前逐天检查，遇到无打卡记录（或标记为 missed）时停止。
    normal 和 overdue 状态均计为有效打卡。
    """
    records = await get_checkin_records(task_id)
    if not records:
        return 0

    # 构建已打卡日期集合（排除 missed）
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
    """为指定任务执行今日打卡。

    Returns:
        (success, message): 是否成功及提示信息
    """
    today = _normalize_date(datetime.now())

    # 检查今天是否已打卡
    existing = await get_checkin_for_date(task_id, today)
    if existing:
        return False, "今天已经打卡过了"

    # 获取任务信息
    task = await get_task_by_id(task_id)
    if not task:
        return False, "任务不存在"

    # 创建打卡记录
    record = CheckinRecord(
        task_id=task_id,
        checkin_date=today,
        status=CheckinStatus.NORMAL,
        actual_time=datetime.now(),
    )
    await create_checkin(record)

    # 更新连续天数
    streak = await calculate_streak(task_id)
    task.current_streak = streak
    if streak > task.max_streak:
        task.max_streak = streak
    task.last_completed_date = datetime.now()
    await update_task(task)

    # 奖金发放信息
    reward_msg = ""
    if task.task_type == TaskType.REWARD and task.reward_amount > 0:
        reward_msg = f"，获得奖金 {task.reward_amount:.2f}"

    return True, f"打卡成功！连续 {streak} 天{reward_msg}"


async def makeup_checkin(task_id: int, target_date: datetime) -> tuple[bool, str]:
    """为指定任务补打卡。

    Args:
        task_id: 任务 ID
        target_date: 需要补卡的日期

    Returns:
        (success, message): 是否成功及提示信息
    """
    target = _normalize_date(target_date)
    today = _normalize_date(datetime.now())

    # 验证补卡日期在允许窗口内
    days_diff = (today - target).days
    if days_diff < 0:
        return False, "不能补打卡未来的日期"
    if days_diff >= MAKEUP_WINDOW_DAYS:
        return False, f"只能补打卡最近 {MAKEUP_WINDOW_DAYS} 天内的日期"

    # 检查目标日期是否已打卡
    existing = await get_checkin_for_date(task_id, target)
    if existing:
        return False, f"{target.strftime('%m-%d')} 已有打卡记录"

    # 获取任务信息
    task = await get_task_by_id(task_id)
    if not task:
        return False, "任务不存在"

    # 创建补卡记录
    record = CheckinRecord(
        task_id=task_id,
        checkin_date=target,
        status=CheckinStatus.OVERDUE,
        actual_time=datetime.now(),
    )
    await create_checkin(record)

    # 重新计算连续天数
    streak = await calculate_streak(task_id)
    task.current_streak = streak
    if streak > task.max_streak:
        task.max_streak = streak
    task.last_completed_date = datetime.now()
    await update_task(task)

    reward_msg = ""
    if task.task_type == TaskType.REWARD and task.reward_amount > 0:
        reward_msg = f"，获得奖金 {task.reward_amount:.2f}"

    return True, f"补卡成功（{target.strftime('%m-%d')}），连续 {streak} 天{reward_msg}"


async def get_available_makeup_dates(task_id: int) -> list[datetime]:
    """获取指定任务可补卡的日期列表。"""
    return await get_unchecked_dates(task_id, MAKEUP_WINDOW_DAYS)
