"""Personal Bonus Manager (PBM) - 个人任务奖金管理系统

入口文件。初始化数据库，加载 UI，配置导航。
"""

import os
import subprocess
import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
sys.path.insert(0, str(Path(__file__).resolve().parent))

import asyncio

import flet as ft
from loguru import logger

from core.database import init_db, close_db
from repositories.category_repo import init_default_categories
from ui.pages.home_page import HomePage
from ui.pages.tasks_page import TasksPage
from ui.pages.stats_page import StatsPage
from ui.pages.settings_page import SettingsPage

# 配置日志
logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | {message}",
)
logger.add(
    Path(__file__).parent / "data" / "pbm.log",
    rotation="5 MB",
    retention="3 days",
    level="DEBUG",
)


def _find_chinese_font() -> str | None:
    """运行时动态查找系统中文字体，返回字体文件路径。"""
    # 优先用 fc-list 查找（Linux/macOS with fontconfig）
    try:
        result = subprocess.run(
            ["fc-list", ":lang=zh", "--format=%{file}\n"],
            capture_output=True, text=True, timeout=3,
        )
        for line in result.stdout.splitlines():
            path = line.strip()
            if path and os.path.exists(path):
                return path
    except Exception:
        pass

    # 常见路径兜底
    fallback_paths = [
        # Linux (wqy)
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        # Linux (Noto CJK)
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        # macOS
        "/System/Library/Fonts/PingFang.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        # Windows
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simsun.ttc",
    ]
    for path in fallback_paths:
        if os.path.exists(path):
            return path
    return None


async def main(page: ft.Page):
    """应用主入口。"""
    # --- 页面基础配置 ---
    page.title = "Personal Bonus Manager"
    page.theme_mode = ft.ThemeMode.LIGHT

    # 动态注册中文字体
    chinese_font_path = _find_chinese_font()
    if chinese_font_path:
        logger.info(f"使用中文字体: {chinese_font_path}")
        page.fonts = {"CJK": chinese_font_path}
        page.theme = ft.Theme(
            color_scheme_seed=ft.Colors.BLUE,
            use_material3=True,
            font_family="CJK",
        )
    else:
        logger.warning("未找到中文字体，文字可能显示异常")
        page.theme = ft.Theme(
            color_scheme_seed=ft.Colors.BLUE,
            use_material3=True,
        )
    page.padding = 0

    # 窗口配置（桌面端）
    page.width = 420
    page.height = 780

    # --- 初始化数据库 ---
    loading_indicator = ft.Container(
        content=ft.Column(
            [
                ft.ProgressRing(),
                ft.Text("正在初始化...", size=14),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=16,
        ),
        alignment=ft.Alignment.CENTER,
        expand=True,
    )
    page.add(loading_indicator)

    try:
        await init_db()
        await init_default_categories()
        logger.info("应用初始化完成")
    except Exception as e:
        logger.error(f"初始化失败: {e}")
        page.clean()
        page.add(
            ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.ERROR, size=48, color=ft.Colors.RED),
                        ft.Text(f"初始化失败: {e}", color=ft.Colors.RED),
                        ft.Button(
                            "重试",
                            on_click=lambda _: page.run_task(main(page)),
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=16,
                ),
                alignment=ft.Alignment.CENTER,
                expand=True,
            )
        )
        return

    # --- 页面控制器实例 ---
    home_page = HomePage(page)
    tasks_page = TasksPage(page)
    stats_page = StatsPage(page)
    settings_page = SettingsPage(page)

    # --- 内容区域 ---
    content_area = ft.Container(expand=True)

    async def switch_page(index: int):
        """切换页面。"""
        page.overlay.clear()
        loading = ft.Container(
            content=ft.ProgressRing(width=24, height=24, stroke_width=2),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )
        content_area.content = loading
        page.update()

        try:
            if index == 0:
                content_area.content = await home_page.build()
            elif index == 1:
                content_area.content = await tasks_page.build()
            elif index == 2:
                content_area.content = await stats_page.build()
            elif index == 3:
                content_area.content = await settings_page.build()
        except Exception as e:
            logger.error(f"页面加载失败: {e}")
            content_area.content = ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.ERROR_OUTLINE, size=36,
                                color=ft.Colors.RED),
                        ft.Text(f"加载失败: {e}", size=13),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                alignment=ft.Alignment.CENTER,
                expand=True,
            )
        page.update()

    # --- 底部导航栏 ---
    def on_nav_change(e: ft.ControlEvent):
        page.run_task(switch_page(e.control.selected_index))

    nav_bar = ft.NavigationBar(
        selected_index=0,
        on_change=on_nav_change,
        destinations=[
            ft.NavigationBarDestination(
                icon=ft.Icons.HOME_OUTLINED,
                selected_icon=ft.Icons.HOME,
                label="首页",
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.TASK_ALT_OUTLINED,
                selected_icon=ft.Icons.TASK_ALT,
                label="任务",
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.BAR_CHART_OUTLINED,
                selected_icon=ft.Icons.BAR_CHART,
                label="统计",
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.SETTINGS_OUTLINED,
                selected_icon=ft.Icons.SETTINGS,
                label="设置",
            ),
        ],
    )

    # --- 应用顶栏 ---
    app_bar = ft.AppBar(
        title=ft.Text("PBM", weight=ft.FontWeight.BOLD),
        center_title=True,
        bgcolor=ft.Colors.SURFACE_CONTAINER,
        actions=[
            ft.IconButton(
                icon=ft.Icons.MIC,
                tooltip="快速语音记账",
                on_click=lambda e: page.run_task(
                    home_page._on_voice_btn_click(e)
                ),
            ),
        ],
    )

    # --- 组装主界面 ---
    page.clean()
    page.appbar = app_bar
    page.navigation_bar = nav_bar
    page.add(content_area)

    # 加载首页
    await switch_page(0)

    # --- 清理钩子 ---
    async def on_disconnect(e):
        await close_db()
        logger.info("应用已退出")

    page.on_disconnect = on_disconnect


if __name__ == "__main__":
    ft.run(main)
