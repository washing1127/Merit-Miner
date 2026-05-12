"""Database engine, session management, and migration helpers."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from core.config import DB_URL

engine = create_async_engine(
    DB_URL,
    echo=False,
    future=True,
)

async_session_factory = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def _migrate_tasks_table():
    """Add any missing columns to the tasks table (schema v2 upgrade)."""
    new_columns = {
        "description": "TEXT NOT NULL DEFAULT ''",
        "priority": "INTEGER NOT NULL DEFAULT 0",
        "repeat_type": "TEXT NOT NULL DEFAULT 'daily'",
        "repeat_interval": "INTEGER NOT NULL DEFAULT 1",
        "repeat_days": "TEXT NOT NULL DEFAULT ''",
        "repeat_until": "DATETIME",
        "due_date": "DATETIME",
        "penalty_enabled": "BOOLEAN NOT NULL DEFAULT 0",
        "penalty_amount": "FLOAT NOT NULL DEFAULT 0.0",
        "sort_order": "INTEGER NOT NULL DEFAULT 0",
    }

    async with engine.begin() as conn:
        # Get existing columns
        result = await conn.execute(text("PRAGMA table_info(tasks)"))
        existing_cols = {row[1] for row in result.fetchall()}

        for col_name, col_def in new_columns.items():
            if col_name not in existing_cols:
                sql = f"ALTER TABLE tasks ADD COLUMN {col_name} {col_def}"
                await conn.execute(text(sql))
                logger.info(f"Migration: added tasks.{col_name}")


async def init_db() -> None:
    """Initialize database: create tables and run migrations."""
    import models.task  # noqa: F401
    import models.checkin  # noqa: F401
    import models.category  # noqa: F401
    import models.transaction  # noqa: F401
    import models.settings  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    logger.info("Database tables initialized")

    await _migrate_tasks_table()


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
