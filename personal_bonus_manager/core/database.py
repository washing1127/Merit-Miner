"""数据库引擎初始化与会话管理。使用 SQLModel + aiosqlite 异步操作。"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from core.config import DB_URL

# 创建异步引擎
engine = create_async_engine(
    DB_URL,
    echo=False,
    future=True,
)

# 异步会话工厂
async_session_factory = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def init_db() -> None:
    """初始化数据库：创建所有表。"""
    # 确保所有模型已导入，这样 SQLModel.metadata 中才有表定义
    import models.task  # noqa: F401
    import models.checkin  # noqa: F401
    import models.category  # noqa: F401
    import models.transaction  # noqa: F401
    import models.settings  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    logger.info("数据库表初始化完成")


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """获取异步数据库会话的上下文管理器。"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_db() -> None:
    """关闭数据库引擎。"""
    await engine.dispose()
    logger.info("数据库连接已关闭")
