"""分类数据访问层。封装分类的 CRUD 操作和初始化。"""

from typing import Optional

from loguru import logger
from sqlmodel import select

from core.config import DEFAULT_CATEGORIES
from core.database import get_session
from models.category import Category


async def init_default_categories() -> None:
    """初始化预设分类。如果分类表为空，则插入默认分类。"""
    async with get_session() as session:
        result = await session.execute(select(Category))
        existing = result.scalars().all()
        if existing:
            return

        for name in DEFAULT_CATEGORIES:
            cat = Category(name=name, is_default=True)
            session.add(cat)
        logger.info(f"初始化 {len(DEFAULT_CATEGORIES)} 个默认分类")


async def get_all_categories() -> list[Category]:
    """获取所有分类。"""
    async with get_session() as session:
        result = await session.execute(select(Category))
        return list(result.scalars().all())


async def get_category_by_id(cat_id: int) -> Optional[Category]:
    """根据 ID 获取分类。"""
    async with get_session() as session:
        return await session.get(Category, cat_id)


async def get_category_by_name(name: str) -> Optional[Category]:
    """根据名称获取分类。"""
    async with get_session() as session:
        stmt = select(Category).where(Category.name == name)
        result = await session.execute(stmt)
        return result.scalars().first()


async def create_category(name: str, is_default: bool = False) -> Category:
    """创建新分类。"""
    async with get_session() as session:
        cat = Category(name=name, is_default=is_default)
        session.add(cat)
        await session.flush()
        await session.refresh(cat)
        logger.info(f"创建分类: {name}")
        return cat


async def delete_category(cat_id: int) -> bool:
    """删除分类（仅允许删除非默认分类）。"""
    async with get_session() as session:
        cat = await session.get(Category, cat_id)
        if not cat:
            return False
        if cat.is_default:
            logger.warning(f"尝试删除默认分类被拒绝: {cat.name}")
            return False
        await session.delete(cat)
        logger.info(f"删除分类: {cat.name}")
        return True
