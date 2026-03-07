"""备份与恢复服务。支持数据库文件和 JSON 格式的导入导出。"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from core.config import DB_PATH, DATA_DIR
from core.database import get_session, close_db, init_db
from models.task import Task
from models.checkin import CheckinRecord
from models.category import Category
from models.transaction import Transaction
from models.settings import AppSettings
from sqlmodel import select


BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)


async def export_db_file() -> Path:
    """导出数据库文件副本。

    Returns:
        导出文件的路径
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_path = BACKUP_DIR / f"pbm_backup_{timestamp}.db"
    shutil.copy2(DB_PATH, export_path)
    logger.info(f"数据库已导出到: {export_path}")
    return export_path


async def export_json() -> Path:
    """导出所有数据为 JSON 文件。

    Returns:
        导出文件的路径
    """
    data: dict = {"export_time": datetime.now().isoformat(), "version": "1.0"}

    async with get_session() as session:
        # 导出任务
        result = await session.execute(select(Task))
        tasks = result.scalars().all()
        data["tasks"] = [
            {
                "id": t.id,
                "title": t.title,
                "reward_amount": t.reward_amount,
                "task_type": t.task_type,
                "current_streak": t.current_streak,
                "max_streak": t.max_streak,
                "last_completed_date": t.last_completed_date.isoformat()
                if t.last_completed_date
                else None,
                "is_enabled": t.is_enabled,
                "created_at": t.created_at.isoformat(),
            }
            for t in tasks
        ]

        # 导出打卡记录
        result = await session.execute(select(CheckinRecord))
        checkins = result.scalars().all()
        data["checkin_records"] = [
            {
                "id": r.id,
                "task_id": r.task_id,
                "checkin_date": r.checkin_date.isoformat(),
                "status": r.status,
                "actual_time": r.actual_time.isoformat(),
            }
            for r in checkins
        ]

        # 导出分类
        result = await session.execute(select(Category))
        categories = result.scalars().all()
        data["categories"] = [
            {"id": c.id, "name": c.name, "is_default": c.is_default}
            for c in categories
        ]

        # 导出账单
        result = await session.execute(select(Transaction))
        transactions = result.scalars().all()
        data["transactions"] = [
            {
                "id": t.id,
                "amount": t.amount,
                "type": t.type,
                "category_id": t.category_id,
                "description": t.description,
                "is_bonus_related": t.is_bonus_related,
                "transaction_date": t.transaction_date.isoformat(),
                "ai_confidence": t.ai_confidence,
                "is_verified": t.is_verified,
            }
            for t in transactions
        ]

        # 导出设置
        result = await session.execute(select(AppSettings))
        settings_list = result.scalars().all()
        data["settings"] = [
            {
                "id": s.id,
                "api_base_url": s.api_base_url,
                "model_name": s.model_name,
                "confirm_mode": s.confirm_mode,
                "currency_symbol": s.currency_symbol,
            }
            for s in settings_list
        ]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_path = BACKUP_DIR / f"pbm_backup_{timestamp}.json"
    export_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(f"JSON 数据已导出到: {export_path}")
    return export_path


async def import_db_file(import_path: str) -> tuple[bool, str]:
    """导入数据库文件。导入前自动备份当前数据。

    Args:
        import_path: 要导入的数据库文件路径

    Returns:
        (success, message)
    """
    source = Path(import_path)
    if not source.exists():
        return False, "文件不存在"
    if not source.suffix == ".db":
        return False, "文件格式不正确，需要 .db 文件"

    # 自动备份当前数据库
    try:
        await export_db_file()
    except Exception as e:
        logger.warning(f"自动备份失败: {e}")

    # 关闭当前连接
    await close_db()

    # 覆盖数据库文件
    try:
        shutil.copy2(source, DB_PATH)
        logger.info(f"数据库已从 {source} 导入")
        return True, "导入成功，请重启应用"
    except Exception as e:
        logger.error(f"导入失败: {e}")
        return False, f"导入失败: {e}"


async def import_json(import_path: str) -> tuple[bool, str]:
    """导入 JSON 备份文件。导入前自动备份当前数据。

    Args:
        import_path: 要导入的 JSON 文件路径

    Returns:
        (success, message)
    """
    source = Path(import_path)
    if not source.exists():
        return False, "文件不存在"

    try:
        raw = source.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return False, f"文件格式错误: {e}"

    # 自动备份
    try:
        await export_db_file()
    except Exception as e:
        logger.warning(f"自动备份失败: {e}")

    # 关闭并重建数据库
    await close_db()
    if DB_PATH.exists():
        DB_PATH.unlink()
    await init_db()

    try:
        async with get_session() as session:
            # 导入分类
            for c in data.get("categories", []):
                cat = Category(
                    id=c["id"], name=c["name"], is_default=c["is_default"]
                )
                session.add(cat)
            await session.flush()

            # 导入任务
            for t in data.get("tasks", []):
                task = Task(
                    id=t["id"],
                    title=t["title"],
                    reward_amount=t["reward_amount"],
                    task_type=t["task_type"],
                    current_streak=t["current_streak"],
                    max_streak=t["max_streak"],
                    last_completed_date=datetime.fromisoformat(
                        t["last_completed_date"]
                    )
                    if t.get("last_completed_date")
                    else None,
                    is_enabled=t["is_enabled"],
                    created_at=datetime.fromisoformat(t["created_at"]),
                )
                session.add(task)
            await session.flush()

            # 导入打卡记录
            for r in data.get("checkin_records", []):
                record = CheckinRecord(
                    id=r["id"],
                    task_id=r["task_id"],
                    checkin_date=datetime.fromisoformat(r["checkin_date"]),
                    status=r["status"],
                    actual_time=datetime.fromisoformat(r["actual_time"]),
                )
                session.add(record)
            await session.flush()

            # 导入账单
            for t in data.get("transactions", []):
                txn = Transaction(
                    id=t["id"],
                    amount=t["amount"],
                    type=t["type"],
                    category_id=t["category_id"],
                    description=t["description"],
                    is_bonus_related=t["is_bonus_related"],
                    transaction_date=datetime.fromisoformat(
                        t["transaction_date"]
                    ),
                    ai_confidence=t["ai_confidence"],
                    is_verified=t["is_verified"],
                )
                session.add(txn)
            await session.flush()

            # 导入设置
            for s in data.get("settings", []):
                setting = AppSettings(
                    id=s["id"],
                    api_base_url=s["api_base_url"],
                    model_name=s["model_name"],
                    confirm_mode=s["confirm_mode"],
                    currency_symbol=s["currency_symbol"],
                )
                session.add(setting)

        logger.info("JSON 数据导入完成")
        return True, "导入成功，请重启应用"
    except Exception as e:
        logger.error(f"JSON 导入失败: {e}")
        return False, f"导入失败: {e}"


def get_backup_files() -> list[Path]:
    """获取所有备份文件列表。"""
    files = list(BACKUP_DIR.glob("pbm_backup_*"))
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files
