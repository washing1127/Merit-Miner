"""账单数据访问层。封装账单/交易的 CRUD 操作。"""

from datetime import datetime
from typing import Optional

from loguru import logger
from sqlmodel import select, col

from core.database import get_session
from models.transaction import Transaction


async def create_transaction(txn: Transaction) -> Transaction:
    """创建新账单。"""
    async with get_session() as session:
        session.add(txn)
        await session.flush()
        await session.refresh(txn)
        logger.info(f"创建账单: amount={txn.amount}, category_id={txn.category_id}")
        return txn


async def get_all_transactions(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    bonus_only: Optional[bool] = None,
) -> list[Transaction]:
    """获取账单列表，支持按时间和类型过滤。"""
    async with get_session() as session:
        stmt = select(Transaction)
        if start_date:
            stmt = stmt.where(Transaction.transaction_date >= start_date)
        if end_date:
            stmt = stmt.where(Transaction.transaction_date <= end_date)
        if bonus_only is not None:
            stmt = stmt.where(
                Transaction.is_bonus_related == bonus_only  # noqa: E712
            )
        stmt = stmt.order_by(col(Transaction.transaction_date).desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_transaction_by_id(txn_id: int) -> Optional[Transaction]:
    """根据 ID 获取账单。"""
    async with get_session() as session:
        return await session.get(Transaction, txn_id)


async def update_transaction(txn: Transaction) -> Transaction:
    """更新账单。"""
    async with get_session() as session:
        merged = await session.merge(txn)
        await session.flush()
        await session.refresh(merged)
        logger.info(f"更新账单: id={merged.id}")
        return merged


async def delete_transaction(txn_id: int) -> bool:
    """删除账单。"""
    async with get_session() as session:
        txn = await session.get(Transaction, txn_id)
        if not txn:
            return False
        await session.delete(txn)
        logger.info(f"删除账单: id={txn_id}")
        return True


async def get_bonus_balance() -> float:
    """计算当前奖金余额。
    余额 = 所有 REWARD_TASK 打卡收入 - 所有 is_bonus_related 支出。
    注意：打卡收入通过 logic_service 计算，此处仅统计支出扣除。
    """
    async with get_session() as session:
        stmt = select(Transaction).where(
            Transaction.is_bonus_related == True  # noqa: E712
        )
        result = await session.execute(stmt)
        total_expense = sum(txn.amount for txn in result.scalars().all())
        return -total_expense  # 返回负的支出总额，调用方需加上收入


async def get_unverified_transactions() -> list[Transaction]:
    """获取未确认的账单（静默模式下低置信度的账单）。"""
    async with get_session() as session:
        stmt = (
            select(Transaction)
            .where(Transaction.is_verified == False)  # noqa: E712
            .order_by(col(Transaction.transaction_date).desc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
