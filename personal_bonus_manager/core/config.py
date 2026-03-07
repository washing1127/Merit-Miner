"""全局配置管理模块，使用 pydantic-settings 加载配置。"""

from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "pbm.db"
DB_URL = f"sqlite+aiosqlite:///{DB_PATH}"

# API Key 加密存储文件路径
API_KEY_FILE = DATA_DIR / ".api_key"


class AppConfig(BaseSettings):
    """应用全局配置，支持从 .env 文件加载。"""

    api_key: str = Field(default="", alias="PBM_API_KEY")
    api_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        alias="PBM_API_BASE_URL",
    )
    model_name: str = Field(default="qwen-plus", alias="PBM_MODEL_NAME")

    model_config = {
        "env_file": str(BASE_DIR / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# 预设分类列表
DEFAULT_CATEGORIES: list[str] = [
    "餐饮", "交通", "购物", "娱乐", "医疗", "教育", "家居", "人情", "其他"
]

# AI 确认模式
CONFIRM_MODE_ALWAYS = 0   # 总是确认
CONFIRM_MODE_SMART = 1    # 智能确认
CONFIRM_MODE_SILENT = 2   # 静默模式

# 补卡允许的天数窗口（含当天）
MAKEUP_WINDOW_DAYS = 3

# AI 置信度阈值
CONFIDENCE_THRESHOLD_SMART = 0.8   # 智能确认模式的弹窗阈值
CONFIDENCE_THRESHOLD_REVIEW = 0.5  # 静默模式的"需复核"标记阈值
