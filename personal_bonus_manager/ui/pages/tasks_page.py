"""任务列表页。展示任务打卡、补卡和任务 CRUD 操作。"""

import flet as ft
from datetime import datetime
from loguru import logger

from models.task import Task, TaskType
from repositories.task_repo import (
    create_task,
    delete_task,
    get_all_tasks,
    get_checkin_for_date,
    update_task,
)
from services.streak_service import (
    checkin_today,
    get_available_makeup_dates,
    makeup_checkin,
)
from ui.components.stat_card import TaskStreakCard


class TasksPage:
    """任务列表页控制器。"""

    def __init__(self, page: ft.Page):
        self.page = page
        self.tasks: list[Task] = []
        self._checked_today: dict[int, bool] = {}
        self._content_column: ft.Column | None = None

    def _show_snack(self, message: str, bgcolor: str = None):
        """显示 SnackBar 提示。"""
        snack = ft.SnackBar(content=ft.Text(message), open=True)
        if bgcolor:
            snack.bgcolor = bgcolor
        self.page.overlay.append(snack)
        self.page.update()

    async def load_data(self):
        """加载任务数据。"""
        try:
            self.tasks = await get_all_tasks()
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            self._checked_today = {}
            for task in self.tasks:
                existing = await get_checkin_for_date(task.id, today)
                self._checked_today[task.id] = existing is not None
        except Exception as e:
            logger.error(f"加载任务数据失败: {e}")

    async def _refresh_ui(self):
        """刷新 UI。"""
        await self.load_data()
        if self._content_column:
            self._content_column.controls = self._build_task_list()
            self._content_column.update()

    def _build_task_list(self) -> list[ft.Control]:
        """构建任务列表。"""
        if not self.tasks:
            return [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(ft.Icons.TASK_ALT, size=48, color=ft.Colors.GREY_300),
                            ft.Text("暂无任务", color=ft.Colors.GREY_400),
                            ft.Text("点击右下角按钮创建第一个任务",
                                    size=12, color=ft.Colors.GREY_400),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8,
                    ),
                    alignment=ft.Alignment.CENTER, padding=60,
                )
            ]

        cards = []
        for task in self.tasks:
            async def on_checkin(e, t=task):
                await self._on_checkin(t)

            async def on_makeup(e, t=task):
                await self._on_makeup(t)

            async def on_edit(e, t=task):
                await self._on_edit_task(t)

            card = TaskStreakCard(
                title=task.title,
                streak=task.current_streak,
                max_streak=task.max_streak,
                is_checked_today=self._checked_today.get(task.id, False),
                reward_amount=task.reward_amount,
                is_reward_task=task.task_type == TaskType.REWARD,
                on_checkin=on_checkin,
                on_makeup=on_makeup,
                on_edit=on_edit,
            )
            cards.append(card)
        return cards

    async def _on_checkin(self, task: Task):
        """打卡操作。"""
        success, message = await checkin_today(task.id)
        self._show_snack(
            message,
            ft.Colors.GREEN_100 if success else ft.Colors.ORANGE_100,
        )
        await self._refresh_ui()

    async def _on_makeup(self, task: Task):
        """补卡操作。"""
        dates = await get_available_makeup_dates(task.id)

        if not dates:
            self._show_snack("最近没有需要补卡的日期")
            return

        date_buttons = []
        for d in dates:
            date_str = d.strftime("%Y-%m-%d")

            async def on_date_click(e, date=d):
                await self._do_makeup(task.id, date)

            date_buttons.append(
                ft.ListTile(
                    title=ft.Text(date_str),
                    leading=ft.Icon(ft.Icons.CALENDAR_TODAY),
                    on_click=on_date_click,
                )
            )

        dialog = ft.AlertDialog(
            title=ft.Text(f"补卡 - {task.title}"),
            content=ft.Container(
                content=ft.Column(
                    [ft.Text("选择需要补卡的日期：", size=14), *date_buttons],
                    tight=True,
                ),
                width=350,
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
            ],
        )
        self.page.show_dialog(dialog)

    async def _do_makeup(self, task_id: int, target_date: datetime):
        """执行补卡。"""
        self.page.pop_dialog()
        success, message = await makeup_checkin(task_id, target_date)
        self._show_snack(
            message,
            ft.Colors.GREEN_100 if success else ft.Colors.RED_100,
        )
        await self._refresh_ui()

    async def _on_edit_task(self, task: Task):
        """编辑任务对话框。"""
        title_field = ft.TextField(label="任务名称", value=task.title)
        amount_field = ft.TextField(
            label="每次奖金", value=str(task.reward_amount),
            keyboard_type=ft.KeyboardType.NUMBER, prefix=ft.Text("¥"),
        )
        type_dropdown = ft.Dropdown(
            label="任务类型", value=str(task.task_type),
            options=[
                ft.dropdown.Option(key="0", text="普通任务"),
                ft.dropdown.Option(key="1", text="奖励任务"),
            ],
        )

        async def on_save(e):
            if not title_field.value.strip():
                title_field.error_text = "请输入任务名称"
                title_field.update()
                return
            try:
                reward = float(amount_field.value)
            except ValueError:
                amount_field.error_text = "请输入有效金额"
                amount_field.update()
                return

            task.title = title_field.value.strip()
            task.reward_amount = reward
            task.task_type = int(type_dropdown.value)
            await update_task(task)
            self.page.pop_dialog()
            await self._refresh_ui()

        async def on_delete(e):
            self.page.pop_dialog()

            async def do_delete_confirmed(e):
                await self._do_delete_task(task.id)

            confirm = ft.AlertDialog(
                title=ft.Text("确认删除"),
                content=ft.Text(
                    f"删除任务 \"{task.title}\" 后，相关打卡记录也将被删除。确定要删除吗？"
                ),
                actions=[
                    ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
                    ft.FilledButton(
                        "删除",
                        on_click=do_delete_confirmed,
                        style=ft.ButtonStyle(bgcolor=ft.Colors.RED),
                    ),
                ],
            )
            self.page.show_dialog(confirm)

        dialog = ft.AlertDialog(
            title=ft.Text("编辑任务"),
            content=ft.Container(
                content=ft.Column(
                    [title_field, type_dropdown, amount_field],
                    tight=True, spacing=12,
                ),
                width=350,
            ),
            actions=[
                ft.TextButton("删除", on_click=on_delete,
                              style=ft.ButtonStyle(color=ft.Colors.RED)),
                ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton("保存", on_click=on_save),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)

    async def _do_delete_task(self, task_id: int):
        """执行删除任务。"""
        self.page.pop_dialog()
        await delete_task(task_id)
        self._show_snack("任务已删除")
        await self._refresh_ui()

    async def _on_add_task(self, e: ft.ControlEvent):
        """创建新任务对话框。"""
        title_field = ft.TextField(label="任务名称", autofocus=True)
        amount_field = ft.TextField(
            label="每次奖金", value="0",
            keyboard_type=ft.KeyboardType.NUMBER, prefix=ft.Text("¥"),
        )
        type_dropdown = ft.Dropdown(
            label="任务类型", value="0",
            options=[
                ft.dropdown.Option(key="0", text="普通任务"),
                ft.dropdown.Option(key="1", text="奖励任务"),
            ],
        )

        async def on_save(e):
            if not title_field.value.strip():
                title_field.error_text = "请输入任务名称"
                title_field.update()
                return
            try:
                reward = float(amount_field.value)
            except ValueError:
                amount_field.error_text = "请输入有效金额"
                amount_field.update()
                return

            task_type = int(type_dropdown.value)
            new_task = Task(
                title=title_field.value.strip(),
                reward_amount=reward if task_type == TaskType.REWARD else 0.0,
                task_type=task_type,
            )
            await create_task(new_task)
            self.page.pop_dialog()
            self._show_snack("任务创建成功")
            await self._refresh_ui()

        dialog = ft.AlertDialog(
            title=ft.Text("创建新任务"),
            content=ft.Container(
                content=ft.Column(
                    [title_field, type_dropdown, amount_field],
                    tight=True, spacing=12,
                ),
                width=350,
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton("创建", on_click=on_save),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)

    async def build(self) -> ft.Control:
        """构建任务页视图。"""
        await self.load_data()

        self._content_column = ft.Column(
            self._build_task_list(),
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        return ft.Stack(
            [
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text("我的任务", size=20, weight=ft.FontWeight.BOLD),
                                    ft.Text(f"{len(self.tasks)} 个任务",
                                            size=13, color=ft.Colors.GREY_500),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                            self._content_column,
                        ],
                        spacing=12,
                    ),
                    padding=ft.padding.all(16),
                    expand=True,
                ),
                ft.Container(
                    content=ft.FloatingActionButton(
                        icon=ft.Icons.ADD,
                        on_click=self._on_add_task,
                        tooltip="创建新任务",
                    ),
                    alignment=ft.Alignment.BOTTOM_RIGHT,
                    padding=ft.padding.all(16),
                ),
            ],
            expand=True,
        )
