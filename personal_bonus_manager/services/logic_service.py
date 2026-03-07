"""双账户业务逻辑服务。处理奖金余额计算、账单校验等核心逻辑。"""

from datetime import datetime, timedelta

from loguru import logger

from models.checkin import CheckinStatus
from models.task import Task, TaskType
from models.transaction import Transaction
from repositories.task_repo import get_all_tasks, get_checkin_records
from repositories.transaction_repo import (
    create_transaction,
    get_all_transactions,
)
from repositories.category_repo import get_category_by_name


async def get_bonus_balance() -> float:
    """计算当前奖金池余额。

    余额 = 所有 REWARD_TASK 打卡获得的奖金总额 - 所有 is_bonus_related 支出总额。
    允许负数。
    """
    # 计算打卡收入
    total_income = 0.0
    tasks = await get_all_tasks(enabled_only=False)
    for task in tasks:
        if task.task_type == TaskType.REWARD and task.reward_amount > 0:
            records = await get_checkin_records(task.id)
            valid_count = sum(
                1 for r in records if r.status != CheckinStatus.MISSED
            )
            total_income += valid_count * task.reward_amount

    # 计算奖金支出
    total_expense = 0.0
    transactions = await get_all_transactions(bonus_only=True)
    for txn in transactions:
        total_expense += txn.amount

    balance = total_income - total_expense
    logger.debug(
        f"奖金余额: 收入={total_income:.2f}, 支出={total_expense:.2f}, "
        f"余额={balance:.2f}"
    )
    return balance


async def record_transaction(
    amount: float,
    category_name: str,
    description: str,
    is_bonus_related: bool,
    ai_confidence: float = 1.0,
    is_verified: bool = True,
    transaction_date: datetime | None = None,
) -> Transaction:
    """记录一笔账单。

    Args:
        amount: 金额
        category_name: 分类名称
        description: 描述
        is_bonus_related: 是否核销奖金
        ai_confidence: AI 置信度
        is_verified: 是否已确认
        transaction_date: 交易日期，默认当前时间
    """
    # 查找分类
    category = await get_category_by_name(category_name)
    if not category:
        # 如果分类不存在，使用"其他"
        category = await get_category_by_name("其他")
        if not category:
            raise ValueError("默认分类'其他'不存在，请检查数据库初始化")

    txn = Transaction(
        amount=amount,
        category_id=category.id,
        description=description,
        is_bonus_related=is_bonus_related,
        ai_confidence=ai_confidence,
        is_verified=is_verified,
        transaction_date=transaction_date or datetime.now(),
    )
    return await create_transaction(txn)


async def get_monthly_stats(
    year: int, month: int
) -> dict:
    """获取指定月份的统计数据。

    Returns:
        dict with keys:
        - bonus_income: 奖金收入
        - bonus_expense: 奖金支出
        - total_expense: 总支出
        - task_completion_rate: 任务完成率（每日）
        - category_breakdown: 分类支出统计
    """
    # 计算月份的起止时间
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)

    # 奖金支出
    bonus_txns = await get_all_transactions(
        start_date=start, end_date=end, bonus_only=True
    )
    bonus_expense = sum(t.amount for t in bonus_txns)

    # 总支出
    all_txns = await get_all_transactions(start_date=start, end_date=end)
    total_expense = sum(t.amount for t in all_txns)

    # 奖金收入（本月打卡的奖励任务）
    bonus_income = 0.0
    tasks = await get_all_tasks(enabled_only=False)
    for task in tasks:
        if task.task_type == TaskType.REWARD and task.reward_amount > 0:
            records = await get_checkin_records(
                task.id, start_date=start, end_date=end
            )
            valid_count = sum(
                1 for r in records if r.status != CheckinStatus.MISSED
            )
            bonus_income += valid_count * task.reward_amount

    # 分类统计
    category_breakdown: dict[int, float] = {}
    for txn in bonus_txns:
        cat_id = txn.category_id
        category_breakdown[cat_id] = category_breakdown.get(cat_id, 0) + txn.amount

    # 任务完成率（按天计算）
    days_in_month = (end - start).days
    today = datetime.now()
    effective_days = min(days_in_month, (today - start).days + 1)
    effective_days = max(effective_days, 1)

    total_tasks = len(tasks)
    if total_tasks == 0:
        daily_rates = []
    else:
        daily_rates = []
        for day_offset in range(effective_days):
            day = start + timedelta(days=day_offset)
            day_completed = 0
            for task in tasks:
                records = await get_checkin_records(
                    task.id, start_date=day, end_date=day + timedelta(days=1)
                )
                if any(r.status != CheckinStatus.MISSED for r in records):
                    day_completed += 1
            daily_rates.append(day_completed / total_tasks)

    return {
        "bonus_income": bonus_income,
        "bonus_expense": bonus_expense,
        "total_expense": total_expense,
        "daily_rates": daily_rates,
        "category_breakdown": category_breakdown,
        "start": start,
        "end": end,
    }
