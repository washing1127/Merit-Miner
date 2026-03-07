"""设置页。管理 AI API 配置、确认模式、数据备份等。"""

import flet as ft
from loguru import logger
from sqlmodel import select

from core.config import CONFIRM_MODE_ALWAYS, CONFIRM_MODE_SMART, CONFIRM_MODE_SILENT
from core.database import get_session
from core.security import load_api_key, save_api_key
from models.settings import AppSettings
from services.backup_service import (
    export_db_file,
    export_json,
    get_backup_files,
    import_db_file,
    import_json,
)


class SettingsPage:
    """设置页控制器。"""

    def __init__(self, page: ft.Page):
        self.page = page
        self._settings: AppSettings | None = None
        self._api_key: str = ""

    async def _load_settings(self):
        """加载设置。"""
        async with get_session() as session:
            result = await session.execute(select(AppSettings))
            self._settings = result.scalars().first()
            if not self._settings:
                self._settings = AppSettings()
                session.add(self._settings)
        self._api_key = load_api_key()

    async def _save_settings(self):
        """保存设置到数据库。"""
        async with get_session() as session:
            session.add(self._settings)
        logger.info("设置已保存")

    def _show_snack(self, message: str, bgcolor: str = None):
        """显示 SnackBar 提示。"""
        snack = ft.SnackBar(content=ft.Text(message), open=True)
        if bgcolor:
            snack.bgcolor = bgcolor
        self.page.overlay.append(snack)
        self.page.update()

    async def build(self) -> ft.Control:
        """构建设置页视图。"""
        await self._load_settings()

        # --- AI 配置区域 ---
        api_key_field = ft.TextField(
            label="API Key",
            value=self._api_key,
            password=True,
            can_reveal_password=True,
            prefix_icon=ft.Icons.KEY,
            hint_text="输入你的 AI API Key",
        )

        base_url_field = ft.TextField(
            label="API Base URL",
            value=self._settings.api_base_url,
            prefix_icon=ft.Icons.LINK,
            hint_text="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

        model_field = ft.TextField(
            label="模型名称",
            value=self._settings.model_name,
            prefix_icon=ft.Icons.SMART_TOY,
            hint_text="qwen-plus",
        )

        confirm_mode_dropdown = ft.Dropdown(
            label="AI 确认模式",
            value=str(self._settings.confirm_mode),
            options=[
                ft.dropdown.Option(key=str(CONFIRM_MODE_ALWAYS), text="总是确认"),
                ft.dropdown.Option(key=str(CONFIRM_MODE_SMART), text="智能确认 (推荐)"),
                ft.dropdown.Option(key=str(CONFIRM_MODE_SILENT), text="静默模式"),
            ],
            helper_text="控制 AI 记账后是否弹窗确认",
        )

        currency_field = ft.TextField(
            label="货币符号",
            value=self._settings.currency_symbol,
            prefix_icon=ft.Icons.CURRENCY_YUAN,
        )

        async def on_save_ai_config(e):
            # 保存 API Key
            api_key = api_key_field.value.strip()
            if api_key:
                save_api_key(api_key)
            self._api_key = api_key

            # 保存其他设置
            self._settings.api_base_url = base_url_field.value.strip()
            self._settings.model_name = model_field.value.strip()
            self._settings.confirm_mode = int(confirm_mode_dropdown.value)
            self._settings.currency_symbol = currency_field.value.strip() or "¥"
            await self._save_settings()
            self._show_snack("设置已保存", ft.Colors.GREEN_100)

        ai_config_section = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.SMART_TOY),
                            title=ft.Text(
                                "AI 配置", weight=ft.FontWeight.BOLD
                            ),
                            subtitle=ft.Text("配置 AI API 连接信息"),
                        ),
                        ft.Container(
                            content=ft.Column(
                                [
                                    api_key_field,
                                    base_url_field,
                                    model_field,
                                    confirm_mode_dropdown,
                                    currency_field,
                                    ft.Container(
                                        content=ft.FilledButton(
                                            "保存配置",
                                            icon=ft.Icons.SAVE,
                                            on_click=on_save_ai_config,
                                        ),
                                        alignment=ft.Alignment.CENTER_RIGHT,
                                    ),
                                ],
                                spacing=12,
                            ),
                            padding=ft.padding.symmetric(horizontal=16, vertical=8),
                        ),
                    ],
                ),
                padding=ft.padding.only(bottom=16),
            ),
        )

        # --- 确认模式说明 ---
        mode_info = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.INFO_OUTLINE),
                            title=ft.Text("确认模式说明", weight=ft.FontWeight.BOLD),
                        ),
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.Text(
                                        "总是确认：每次语音记账后弹窗预览，需手动确认保存。",
                                        size=13,
                                    ),
                                    ft.Text(
                                        "智能确认：仅当 AI 置信度 < 80% 时弹窗，否则直接保存。",
                                        size=13,
                                    ),
                                    ft.Text(
                                        "静默模式：从不弹窗，直接保存。置信度 < 50% 的条目标记为\"需复核\"。",
                                        size=13,
                                    ),
                                ],
                                spacing=8,
                            ),
                            padding=ft.padding.symmetric(horizontal=16, vertical=8),
                        ),
                    ],
                ),
                padding=ft.padding.only(bottom=16),
            ),
        )

        # --- 数据管理区域 ---
        file_picker = ft.FilePicker()
        self.page.overlay.append(file_picker)
        self._file_picker = file_picker

        async def on_export_db(e):
            try:
                path = await export_db_file()
                self._show_snack(f"数据库已导出到: {path.name}", ft.Colors.GREEN_100)
            except Exception as ex:
                self._show_snack(f"导出失败: {ex}", ft.Colors.RED_100)

        async def on_export_json(e):
            try:
                path = await export_json()
                self._show_snack(f"JSON 已导出到: {path.name}", ft.Colors.GREEN_100)
            except Exception as ex:
                self._show_snack(f"导出失败: {ex}", ft.Colors.RED_100)

        async def on_import_db(e):
            files = file_picker.pick_files(
                dialog_title="选择数据库备份文件",
                allowed_extensions=["db"],
                file_type=ft.FilePickerFileType.CUSTOM,
            )
            if files and len(files) > 0 and files[0].path:
                await self._confirm_import(files[0].path, "db")

        async def on_import_json(e):
            files = file_picker.pick_files(
                dialog_title="选择 JSON 备份文件",
                allowed_extensions=["json"],
                file_type=ft.FilePickerFileType.CUSTOM,
            )
            if files and len(files) > 0 and files[0].path:
                await self._confirm_import(files[0].path, "json")

        data_section = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.STORAGE),
                            title=ft.Text(
                                "数据管理", weight=ft.FontWeight.BOLD
                            ),
                            subtitle=ft.Text("备份与恢复数据"),
                        ),
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.Row(
                                        [
                                            ft.OutlinedButton(
                                                "导出数据库",
                                                icon=ft.Icons.DOWNLOAD,
                                                on_click=on_export_db,
                                                expand=True,
                                            ),
                                            ft.OutlinedButton(
                                                "导出 JSON",
                                                icon=ft.Icons.CODE,
                                                on_click=on_export_json,
                                                expand=True,
                                            ),
                                        ],
                                        spacing=8,
                                    ),
                                    ft.Row(
                                        [
                                            ft.OutlinedButton(
                                                "导入数据库",
                                                icon=ft.Icons.UPLOAD,
                                                on_click=on_import_db,
                                                expand=True,
                                            ),
                                            ft.OutlinedButton(
                                                "导入 JSON",
                                                icon=ft.Icons.UPLOAD_FILE,
                                                on_click=on_import_json,
                                                expand=True,
                                            ),
                                        ],
                                        spacing=8,
                                    ),
                                    self._build_backup_list(),
                                ],
                                spacing=8,
                            ),
                            padding=ft.padding.symmetric(horizontal=16, vertical=8),
                        ),
                    ],
                ),
                padding=ft.padding.only(bottom=16),
            ),
        )

        # --- 关于 ---
        about_section = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.ListTile(
                            leading=ft.Icon(ft.Icons.INFO),
                            title=ft.Text("关于", weight=ft.FontWeight.BOLD),
                        ),
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.Text(
                                        "Personal Bonus Manager v1.0",
                                        size=14,
                                        weight=ft.FontWeight.W_500,
                                    ),
                                    ft.Text(
                                        "个人任务奖金管理系统",
                                        size=12,
                                        color=ft.Colors.GREY_600,
                                    ),
                                    ft.Text(
                                        "数据完全存储在本地，不上传任何信息。",
                                        size=12,
                                        color=ft.Colors.GREY_500,
                                    ),
                                ],
                                spacing=4,
                            ),
                            padding=ft.padding.symmetric(horizontal=16, vertical=8),
                        ),
                    ],
                ),
                padding=ft.padding.only(bottom=16),
            ),
        )

        return ft.Container(
            content=ft.Column(
                [
                    ai_config_section,
                    mode_info,
                    data_section,
                    about_section,
                ],
                spacing=12,
                scroll=ft.ScrollMode.AUTO,
            ),
            padding=ft.padding.all(16),
            expand=True,
        )

    def _build_backup_list(self) -> ft.Control:
        """构建备份文件列表。"""
        files = get_backup_files()
        if not files:
            return ft.Container(
                content=ft.Text(
                    "暂无备份文件",
                    size=12,
                    color=ft.Colors.GREY_400,
                    text_align=ft.TextAlign.CENTER,
                ),
                padding=ft.padding.symmetric(vertical=8),
                alignment=ft.Alignment.CENTER,
            )

        items = []
        for f in files[:5]:
            size_kb = f.stat().st_size / 1024
            items.append(
                ft.ListTile(
                    leading=ft.Icon(
                        ft.Icons.DESCRIPTION,
                        color=ft.Colors.GREY_600,
                        size=20,
                    ),
                    title=ft.Text(f.name, size=12),
                    subtitle=ft.Text(f"{size_kb:.1f} KB", size=11),
                    dense=True,
                )
            )

        return ft.Column(
            [
                ft.Text(
                    "最近备份",
                    size=13,
                    weight=ft.FontWeight.W_500,
                    color=ft.Colors.GREY_600,
                ),
                *items,
            ],
            spacing=0,
        )

    async def _confirm_import(self, file_path: str, import_type: str):
        """确认导入操作。"""
        async def do_import(e):
            self.page.pop_dialog()
            if import_type == "db":
                success, msg = await import_db_file(file_path)
            else:
                success, msg = await import_json(file_path)

            if success:
                restart_dialog = ft.AlertDialog(
                    title=ft.Text("导入完成"),
                    content=ft.Text(msg),
                    modal=True,
                    actions=[
                        ft.FilledButton("确定", on_click=lambda e: self.page.pop_dialog()),
                    ],
                )
                self.page.show_dialog(restart_dialog)
            else:
                self._show_snack(f"导入失败: {msg}", ft.Colors.RED_100)

        dialog = ft.AlertDialog(
            title=ft.Text("确认导入"),
            content=ft.Text(
                "导入将覆盖当前数据（系统会自动备份当前数据）。\n"
                "导入完成后需要重启应用。\n\n确定要继续吗？"
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton("确认导入", on_click=do_import),
            ],
        )
        self.page.show_dialog(dialog)
