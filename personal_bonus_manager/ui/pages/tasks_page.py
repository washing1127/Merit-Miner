"""Task list page with Today / All dual views, repeat rules, priority, and penalty."""

from datetime import datetime, timedelta

import flet as ft
from loguru import logger

from models.checkin import CheckinStatus
from models.task import (
    Task,
    TaskType,
    TaskPriority,
    RepeatType,
    PRIORITY_LABELS,
    PRIORITY_COLORS,
    REPEAT_LABELS,
    WEEKDAY_LABELS,
)
from repositories.task_repo import (
    create_task,
    delete_task,
    get_all_tasks,
    get_checkin_for_date,
    get_checkin_records,
    get_overdue_tasks,
    update_task,
)
from services.repeat_service import is_task_due_on
from services.streak_service import (
    checkin_today,
    get_available_makeup_dates,
    makeup_checkin,
)
from ui.components.stat_card import TaskStreakCard


class TasksPage:
    """Tasks page with Today / All dual-tab layout."""

    def __init__(self, page: ft.Page):
        self.page = page
        self.tasks: list[Task] = []
        self.overdue_tasks: list[Task] = []
        self._checked_today: dict[int, bool] = {}
        self._sort_by: str = "priority"
        self._search_text: str = ""
        self._content_area: ft.Container | None = None
        self._today_col: ft.Column | None = None
        self._all_col: ft.Column | None = None
        self._tab_index: int = 0

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _show_snack(self, message: str, bgcolor: str = None):
        snack = ft.SnackBar(content=ft.Text(message), open=True)
        if bgcolor:
            snack.bgcolor = bgcolor
        self.page.overlay.append(snack)
        self.page.update()

    @staticmethod
    def _norm(date: datetime) -> datetime:
        return date.replace(hour=0, minute=0, second=0, microsecond=0)

    # ------------------------------------------------------------------ #
    # Data loading
    # ------------------------------------------------------------------ #

    async def load_data(self):
        try:
            self.tasks = await get_all_tasks(enabled_only=False)
            self.overdue_tasks = await get_overdue_tasks()
            today = self._norm(datetime.now())
            self._checked_today = {}
            for task in self.tasks:
                existing = await get_checkin_for_date(task.id, today)
                self._checked_today[task.id] = existing is not None
        except Exception as e:
            logger.error(f"Failed loading task data: {e}")

    async def _refresh_ui(self):
        await self.load_data()
        if self._today_col is not None:
            self._today_col.controls = self._build_today_view()
        if self._all_col is not None:
            self._all_col.controls = self._build_all_view()
        if self._content_area:
            self._content_area.update()
        self._update_fab()

    def _update_fab(self):
        self.page.floating_action_button = ft.FloatingActionButton(
            icon=ft.Icons.ADD,
            on_click=self._on_add_task,
            tooltip="创建新任务",
        )

    # ------------------------------------------------------------------ #
    # Today Tab
    # ------------------------------------------------------------------ #

    def _build_today_view(self) -> list[ft.Control]:
        today = self._norm(datetime.now())
        weekday_names = ["一", "二", "三", "四", "五", "六", "日"]
        wday = weekday_names[today.weekday()]

        # Calculate today's due tasks
        due_today = [t for t in self.tasks if t.is_enabled and is_task_due_on(t, today)]
        completed_today = [t for t in due_today if self._checked_today.get(t.id, False)]
        pending_today = [t for t in due_today if not self._checked_today.get(t.id, False)]

        # Overdue: exclude tasks that are also due today (they get another chance)
        overdue_ids = {t.id for t in self.overdue_tasks}
        overdue_filtered = [
            t for t in self.overdue_tasks
            if not is_task_due_on(t, today)
        ]

        # Enable/disable state: a task might be in overdue but disabled
        overdue_filtered = [t for t in overdue_filtered if t.is_enabled]

        total = len(due_today)
        done = len(completed_today)

        controls: list[ft.Control] = []

        # --- Date header ---
        controls.append(
            ft.Container(
                content=ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text(
                                    f"{today.month}月{today.day}日 周{wday}",
                                    size=20,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Text(
                                    f"{done}/{total} 已完成" if total > 0 else "今日暂无任务",
                                    size=13,
                                    color=ft.Colors.GREEN if done == total and total > 0 else ft.Colors.GREY_500,
                                ),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.ADD,
                            tooltip="创建任务",
                            on_click=self._on_add_task,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                padding=ft.padding.only(bottom=8),
            )
        )

        if not self.tasks:
            controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(ft.Icons.TASK_ALT, size=48, color=ft.Colors.GREY_300),
                            ft.Text("还没有任务", color=ft.Colors.GREY_400, size=15),
                            ft.Text(
                                "点击 + 按钮创建第一个任务",
                                size=12,
                                color=ft.Colors.GREY_400,
                            ),
                            ft.OutlinedButton(
                                "创建任务",
                                icon=ft.Icons.ADD,
                                on_click=self._on_add_task,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),
                    alignment=ft.Alignment.CENTER,
                    padding=60,
                )
            )
            return controls

        # --- Overdue section ---
        if overdue_filtered:
            controls.append(
                ft.Text(
                    f"已逾期 ({len(overdue_filtered)})",
                    size=13,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.RED,
                )
            )
            for task in overdue_filtered:
                card = self._build_task_card(task, view_mode="today", is_overdue=True)
                controls.append(card)

        # --- Pending section ---
        if pending_today:
            controls.append(
                ft.Text(
                    f"待完成 ({len(pending_today)})",
                    size=13,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.GREY_700,
                )
            )
            for task in pending_today:
                card = self._build_task_card(task, view_mode="today")
                controls.append(card)

        # --- Completed section ---
        if completed_today:
            controls.append(
                ft.Text(
                    f"已完成 ({len(completed_today)})",
                    size=13,
                    weight=ft.FontWeight.W_600,
                    color=ft.Colors.GREEN,
                )
            )
            for task in completed_today:
                card = self._build_task_card(task, view_mode="today")
                # Override: completed cards are semi-transparent
                card.opacity = 0.65
                controls.append(card)

        return controls

    # ------------------------------------------------------------------ #
    # All Tab
    # ------------------------------------------------------------------ #

    def _build_all_view(self) -> list[ft.Control]:
        # Sort
        tasks = list(self.tasks)
        if self._sort_by == "priority":
            tasks.sort(key=lambda t: (t.priority, t.created_at), reverse=True)
        elif self._sort_by == "created":
            tasks.sort(key=lambda t: t.created_at, reverse=True)
        elif self._sort_by == "title":
            tasks.sort(key=lambda t: t.title.lower())

        # Search filter
        search = self._search_text.strip().lower()
        if search:
            tasks = [t for t in tasks if search in t.title.lower() or search in (t.description or "").lower()]

        # Sort bar
        sort_buttons = ft.Row(
            [
                ft.TextButton(
                    "优先级",
                    icon=ft.Icons.FLAG,
                    on_click=lambda e: self._on_sort_change("priority"),
                    style=ft.ButtonStyle(
                        color=ft.Colors.BLUE if self._sort_by == "priority" else ft.Colors.GREY_500
                    ),
                ),
                ft.TextButton(
                    "创建时间",
                    icon=ft.Icons.SCHEDULE,
                    on_click=lambda e: self._on_sort_change("created"),
                    style=ft.ButtonStyle(
                        color=ft.Colors.BLUE if self._sort_by == "created" else ft.Colors.GREY_500
                    ),
                ),
                ft.TextButton(
                    "标题",
                    icon=ft.Icons.SORT_BY_ALPHA,
                    on_click=lambda e: self._on_sort_change("title"),
                    style=ft.ButtonStyle(
                        color=ft.Colors.BLUE if self._sort_by == "title" else ft.Colors.GREY_500
                    ),
                ),
            ],
            spacing=0,
            scroll=ft.ScrollMode.AUTO,
        )

        # Search field
        async def _on_search_change(e):
            self._search_text = e.control.value
            await self._refresh_ui()

        search_field = ft.TextField(
            hint_text="搜索任务...",
            prefix_icon=ft.Icons.SEARCH,
            value=self._search_text,
            on_change=_on_search_change,
            height=40,
            content_padding=ft.padding.symmetric(vertical=8, horizontal=12),
            border_radius=20,
            border_color=ft.Colors.GREY_300,
        )

        controls: list[ft.Control] = [sort_buttons, search_field]

        if not tasks:
            controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(ft.Icons.SEARCH_OFF, size=48, color=ft.Colors.GREY_300),
                            ft.Text("没有匹配的任务" if search else "暂无任务", color=ft.Colors.GREY_400),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),
                    alignment=ft.Alignment.CENTER,
                    padding=40,
                )
            )
            return controls

        # Group: enabled first, then disabled
        enabled = [t for t in tasks if t.is_enabled]
        disabled = [t for t in tasks if not t.is_enabled]

        for task in enabled:
            controls.append(self._build_task_card(task, view_mode="all"))

        if disabled:
            controls.append(
                ft.Text(
                    f"已禁用 ({len(disabled)})",
                    size=13,
                    color=ft.Colors.GREY_400,
                    weight=ft.FontWeight.W_500,
                )
            )
            for task in disabled:
                controls.append(self._build_task_card(task, view_mode="all"))

        return controls

    async def _on_sort_change(self, sort_by: str):
        self._sort_by = sort_by
        await self._refresh_ui()

    # ------------------------------------------------------------------ #
    # Task Card builder
    # ------------------------------------------------------------------ #

    def _build_task_card(self, task: Task, view_mode: str = "today", is_overdue: bool = False) -> ft.Card:
        async def on_checkin(e, t=task):
            await self._on_checkin(t)

        async def on_makeup(e, t=task):
            await self._on_makeup(t)

        async def on_edit(e, t=task):
            await self._on_edit_task(t)

        async def on_history(e, t=task):
            await self._show_task_history(t)

        repeat_label = REPEAT_LABELS.get(task.repeat_type, "")

        card = TaskStreakCard(
            title=task.title,
            streak=task.current_streak,
            max_streak=task.max_streak,
            is_checked_today=self._checked_today.get(task.id, False),
            reward_amount=task.reward_amount,
            is_reward_task=task.task_type == TaskType.REWARD,
            is_enabled=task.is_enabled,
            description=task.description,
            priority=task.priority,
            repeat_label=repeat_label,
            view_mode=view_mode,
            on_checkin=on_checkin,
            on_makeup=on_makeup,
            on_edit=on_edit,
            on_history=on_history,
        )

        if is_overdue:
            card.color = ft.Colors.with_opacity(0.06, ft.Colors.RED)

        return card

    # ------------------------------------------------------------------ #
    # Check-in / Makeup
    # ------------------------------------------------------------------ #

    async def _on_checkin(self, task: Task):
        try:
            success, message = await checkin_today(task.id)
            self._show_snack(
                message,
                ft.Colors.GREEN_100 if success else ft.Colors.ORANGE_100,
            )
            await self._refresh_ui()
        except Exception as e:
            logger.exception(f"Check-in error: {e}")
            self._show_snack(f"打卡失败: {e}", ft.Colors.RED_100)

    async def _on_makeup(self, task: Task):
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
        self.page.pop_dialog()
        success, message = await makeup_checkin(task_id, target_date)
        self._show_snack(
            message,
            ft.Colors.GREEN_100 if success else ft.Colors.RED_100,
        )
        await self._refresh_ui()

    # ------------------------------------------------------------------ #
    # Task History
    # ------------------------------------------------------------------ #

    async def _show_task_history(self, task: Task):
        end = datetime.now()
        start = end - timedelta(days=30)
        records = await get_checkin_records(task.id, start_date=start)

        valid_count = sum(1 for r in records if r.status != CheckinStatus.MISSED)

        def build_record_tile(r) -> ft.Container:
            if r.status == CheckinStatus.NORMAL:
                icon = ft.Icons.CHECK_CIRCLE
                color = ft.Colors.GREEN
                label = "正常"
            elif r.status == CheckinStatus.OVERDUE:
                icon = ft.Icons.CHECK_CIRCLE_OUTLINE
                color = ft.Colors.ORANGE
                label = "补卡"
            else:
                icon = ft.Icons.CANCEL_OUTLINED
                color = ft.Colors.GREY_400
                label = "未打"

            return ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(icon, size=16, color=color),
                        ft.Text(r.checkin_date.strftime("%m月%d日"), size=13, expand=True),
                        ft.Container(
                            content=ft.Text(label, size=11, color=color),
                            bgcolor=ft.Colors.with_opacity(0.12, color),
                            border_radius=4,
                            padding=ft.padding.symmetric(horizontal=6, vertical=2),
                        ),
                    ],
                    spacing=8,
                ),
                padding=ft.padding.symmetric(vertical=7, horizontal=4),
                border=ft.border.only(bottom=ft.BorderSide(1, ft.Colors.GREY_100)),
            )

        if records:
            records_list = ft.Container(
                content=ft.Column(
                    [build_record_tile(r) for r in records],
                    spacing=0,
                    scroll=ft.ScrollMode.AUTO,
                ),
                height=260,
                width=320,
            )
        else:
            records_list = ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.CALENDAR_TODAY, size=36, color=ft.Colors.GREY_300),
                        ft.Text("近30天暂无打卡记录", color=ft.Colors.GREY_400),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                alignment=ft.Alignment.CENTER,
                height=100,
                width=320,
            )

        reward_info = (
            f"¥{task.reward_amount:.2f}/次"
            if task.task_type == TaskType.REWARD and task.reward_amount > 0
            else "无奖励"
        )

        repeat_label = REPEAT_LABELS.get(task.repeat_type, "")
        prio_label = PRIORITY_LABELS.get(task.priority, "")

        stats_row = ft.Row(
            [
                ft.Column(
                    [
                        ft.Text("当前连续", size=11, color=ft.Colors.GREY_500),
                        ft.Text(f"{task.current_streak}天", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=2,
                    expand=True,
                ),
                ft.Column(
                    [
                        ft.Text("历史最高", size=11, color=ft.Colors.GREY_500),
                        ft.Text(f"{task.max_streak}天", size=18, weight=ft.FontWeight.BOLD),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=2,
                    expand=True,
                ),
                ft.Column(
                    [
                        ft.Text("近30天", size=11, color=ft.Colors.GREY_500),
                        ft.Text(f"{valid_count}次", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=2,
                    expand=True,
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_AROUND,
        )

        # Info rows: description, repeat, priority, penalty
        info_items = []
        if task.description:
            info_items.append(ft.Text(f"备注: {task.description}", size=12, color=ft.Colors.GREY_600))
        info_items.append(ft.Text(f"重复: {repeat_label}", size=12, color=ft.Colors.GREY_600))
        if task.priority > TaskPriority.NONE:
            info_items.append(ft.Text(f"优先级: {prio_label}", size=12, color=PRIORITY_COLORS[task.priority]))
        if task.penalty_enabled:
            info_items.append(ft.Text(f"断签惩罚: ¥{task.penalty_amount:.2f}/天", size=12, color=ft.Colors.RED))

        dialog = ft.AlertDialog(
            title=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.TASK_ALT, size=18,
                        color=ft.Colors.GREEN if task.task_type == TaskType.REWARD else ft.Colors.BLUE,
                    ),
                    ft.Text(task.title, size=16),
                    ft.Text(f"  {reward_info}", size=12, color=ft.Colors.AMBER_700)
                    if task.task_type == TaskType.REWARD else ft.Container(),
                ],
                spacing=6,
            ),
            content=ft.Container(
                content=ft.Column(
                    [
                        *info_items,
                        ft.Divider(height=1),
                        stats_row,
                        ft.Divider(height=1),
                        ft.Text("最近30天打卡记录", size=13, weight=ft.FontWeight.W_500, color=ft.Colors.GREY_700),
                        records_list,
                    ],
                    spacing=10,
                    tight=True,
                ),
                width=320,
            ),
            actions=[
                ft.TextButton("关闭", on_click=lambda e: self.page.pop_dialog()),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)

    # ------------------------------------------------------------------ #
    # Create / Edit Task (unified dialog)
    # ------------------------------------------------------------------ #

    async def _on_add_task(self, e: ft.ControlEvent = None):
        await self._show_task_form()

    async def _on_edit_task(self, task: Task):
        await self._show_task_form(task=task)

    async def _show_task_form(self, task: Task | None = None):
        """Unified create/edit form dialog."""
        is_edit = task is not None

        # --- Form fields ---
        title_field = ft.TextField(
            label="任务名称",
            value=task.title if task else "",
            autofocus=not is_edit,
        )
        desc_field = ft.TextField(
            label="备注 (可选)",
            value=task.description if task else "",
            multiline=True,
            min_lines=1,
            max_lines=3,
        )

        # Repeat type
        repeat_types = [
            ("none", "不重复"),
            ("daily", "每天"),
            ("weekdays", "工作日"),
            ("weekly", "每周"),
            ("monthly", "每月"),
        ]
        default_rtype = task.repeat_type if task else "daily"

        def _rtype_btn(rtype, label):
            selected = rtype == default_rtype
            return ft.TextButton(
                label,
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.BLUE if selected else ft.Colors.GREY_200,
                    color=ft.Colors.WHITE if selected else ft.Colors.GREY_700,
                    shape=ft.RoundedRectangleBorder(radius=6),
                    padding=ft.padding.symmetric(horizontal=10, vertical=4),
                ),
                data=rtype,
                on_click=_on_rtype_change,
            )

        rtype_row = ft.Row(
            [_rtype_btn(rt, lb) for rt, lb in repeat_types],
            spacing=4,
            scroll=ft.ScrollMode.AUTO,
        )

        # Weekday selector (shown for weekly)
        current_days = set()
        if task and task.repeat_days:
            try:
                current_days = {int(d) for d in task.repeat_days.split(",") if d.strip()}
            except ValueError:
                pass

        weekday_chips = []
        for i, label in enumerate(WEEKDAY_LABELS):
            selected = i in current_days

            def _toggle_day(e, day=i):
                nonlocal current_days
                if day in current_days:
                    current_days.discard(day)
                else:
                    current_days.add(day)
                e.control.bgcolor = ft.Colors.BLUE if day in current_days else ft.Colors.GREY_200
                e.control.update()

            chip = ft.Container(
                content=ft.Text(label, size=12),
                padding=ft.padding.symmetric(horizontal=10, vertical=6),
                border_radius=16,
                bgcolor=ft.Colors.BLUE if selected else ft.Colors.GREY_200,
                on_click=_toggle_day,
            )
            weekday_chips.append(chip)

        weekday_row = ft.Row(
            weekday_chips,
            spacing=6,
            visible=(default_rtype == "weekly"),
        )
        weekday_label = ft.Text(
            "选择星期",
            size=12,
            color=ft.Colors.GREY_600,
            visible=(default_rtype == "weekly"),
        )

        async def _on_rtype_change(e):
            nonlocal default_rtype
            default_rtype = e.control.data
            # Update all buttons
            for btn in rtype_row.controls:
                selected = btn.data == default_rtype
                btn.style = ft.ButtonStyle(
                    bgcolor=ft.Colors.BLUE if selected else ft.Colors.GREY_200,
                    color=ft.Colors.WHITE if selected else ft.Colors.GREY_700,
                    shape=ft.RoundedRectangleBorder(radius=6),
                    padding=ft.padding.symmetric(horizontal=10, vertical=4),
                )
                btn.update()
            # Toggle weekday selector
            weekday_row.visible = (default_rtype == "weekly")
            weekday_label.visible = (default_rtype == "weekly")
            weekday_row.update()
            weekday_label.update()
            # Toggle due date
            due_date_row.visible = (default_rtype == "none")
            due_date_row.update()

        # Priority selector
        prio_default = task.priority if task else TaskPriority.NONE
        prio_buttons = []
        for p_val in [TaskPriority.NONE, TaskPriority.LOW, TaskPriority.MEDIUM, TaskPriority.HIGH]:
            label = PRIORITY_LABELS[p_val]
            color = PRIORITY_COLORS[p_val]
            is_selected = p_val == prio_default

            def _set_priority(e, pv=p_val):
                nonlocal prio_default
                prio_default = pv
                for i, btn in enumerate(prio_buttons):
                    sel = [TaskPriority.NONE, TaskPriority.LOW, TaskPriority.MEDIUM, TaskPriority.HIGH][i] == prio_default
                    btn.style = ft.ButtonStyle(
                        bgcolor=PRIORITY_COLORS[[TaskPriority.NONE, TaskPriority.LOW, TaskPriority.MEDIUM, TaskPriority.HIGH][i]] if sel else ft.Colors.GREY_200,
                        color=ft.Colors.WHITE if sel else ft.Colors.GREY_600,
                        shape=ft.RoundedRectangleBorder(radius=6),
                        padding=ft.padding.symmetric(horizontal=8, vertical=4),
                    )
                    btn.update()

            btn = ft.TextButton(
                label,
                style=ft.ButtonStyle(
                    bgcolor=color if is_selected else ft.Colors.GREY_200,
                    color=ft.Colors.WHITE if is_selected else ft.Colors.GREY_600,
                    shape=ft.RoundedRectangleBorder(radius=6),
                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                ),
                on_click=_set_priority,
            )
            prio_buttons.append(btn)

        prio_row = ft.Row(prio_buttons, spacing=4)

        # Task type
        task_type_default = task.task_type if task else TaskType.NORMAL

        def _set_ttype(e):
            nonlocal task_type_default
            task_type_default = TaskType.REWARD if e.control.value else TaskType.NORMAL
            reward_amount_field.visible = (task_type_default == TaskType.REWARD)
            reward_amount_field.update()

        type_switch = ft.Switch(
            label="奖励任务（打卡获得奖金）",
            value=(task_type_default == TaskType.REWARD),
            on_change=_set_ttype,
        )

        # Reward amount
        reward_amount_field = ft.TextField(
            label="每次打卡奖励",
            value=str(task.reward_amount) if task and task.reward_amount > 0 else "0",
            keyboard_type=ft.KeyboardType.NUMBER,
            prefix=ft.Text("¥"),
            visible=(task_type_default == TaskType.REWARD),
        )

        # Penalty
        penalty_switch = ft.Switch(
            label="启用断签惩罚",
            value=(task.penalty_enabled if task else False),
        )

        penalty_amount_field = ft.TextField(
            label="每次断签扣除金额",
            value=str(task.penalty_amount) if (task and task.penalty_amount > 0) else "",
            hint_text="留空则默认等于奖励金额",
            keyboard_type=ft.KeyboardType.NUMBER,
            prefix=ft.Text("¥"),
        )

        # Due date (only for "none" repeat)
        due_date_field = ft.TextField(
            hint_text="YYYY-MM-DD (可选)",
            value=task.due_date.strftime("%Y-%m-%d") if (task and task.due_date) else "",
            width=200,
            prefix_icon=ft.Icons.CALENDAR_TODAY,
        )
        due_date_row = ft.Row(
            [
                ft.Text("截止日期", size=13, color=ft.Colors.GREY_700),
                due_date_field,
            ],
            spacing=8,
            visible=(default_rtype == "none"),
        )

        # Enabled switch (edit only)
        enabled_switch = ft.Switch(
            label="启用任务",
            value=(task.is_enabled if task else True),
            active_color=ft.Colors.GREEN,
            visible=is_edit,
        )

        async def on_save(e):
            # Validate title
            if not title_field.value.strip():
                title_field.error_text = "请输入任务名称"
                title_field.update()
                return

            # Validate / compute penalty amount
            try:
                pa_str = penalty_amount_field.value.strip()
                pa_val = float(pa_str) if pa_str else 0.0
            except ValueError:
                penalty_amount_field.error_text = "请输入有效金额"
                panalty_field.update()
                return

            # If penalty enabled but no amount, default to reward amount
            if penalty_switch.value and pa_val <= 0:
                try:
                    reward_val = float(reward_amount_field.value or "0")
                except ValueError:
                    reward_val = 0
                pa_val = reward_val

            # Compute repeat_days for weekly
            repeat_days_str = ",".join(str(d) for d in sorted(current_days)) if default_rtype == "weekly" and current_days else ""

            # Parse due date
            due_date_val = None
            if default_rtype == "none":
                due_date_str = due_date_field.value.strip()
                if due_date_str:
                    try:
                        due_date_val = datetime.strptime(due_date_str, "%Y-%m-%d")
                    except ValueError:
                        pass

            if is_edit:
                # Update existing task
                task.title = title_field.value.strip()
                task.description = desc_field.value.strip()
                task.repeat_type = default_rtype
                task.repeat_interval = 1
                task.repeat_days = repeat_days_str
                task.priority = prio_default
                task.task_type = task_type_default
                try:
                    task.reward_amount = float(reward_amount_field.value or "0")
                except ValueError:
                    task.reward_amount = 0
                task.penalty_enabled = penalty_switch.value
                task.penalty_amount = pa_val
                task.due_date = due_date_val
                task.is_enabled = enabled_switch.value
                await update_task(task)
                self.page.pop_dialog()
                self._show_snack("任务已更新")
            else:
                new_task = Task(
                    title=title_field.value.strip(),
                    description=desc_field.value.strip(),
                    repeat_type=default_rtype,
                    repeat_interval=1,
                    repeat_days=repeat_days_str,
                    priority=prio_default,
                    task_type=task_type_default,
                    reward_amount=float(reward_amount_field.value or "0") if task_type_default == TaskType.REWARD else 0.0,
                    penalty_enabled=penalty_switch.value,
                    penalty_amount=pa_val,
                    due_date=due_date_val,
                )
                await create_task(new_task)
                self.page.pop_dialog()
                self._show_snack("任务创建成功")

            await self._refresh_ui()

        async def on_delete(e):
            if not is_edit:
                return
            self.page.pop_dialog()

            async def do_delete_confirmed(e2):
                await self._do_delete_task(task.id)

            confirm = ft.AlertDialog(
                title=ft.Text("确认删除"),
                content=ft.Text(f"删除任务「{task.title}」后，相关打卡记录也将被删除。确定要删除吗？"),
                actions=[
                    ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
                    ft.FilledButton("删除", on_click=do_delete_confirmed, style=ft.ButtonStyle(bgcolor=ft.Colors.RED)),
                ],
            )
            self.page.show_dialog(confirm)

        dialog = ft.AlertDialog(
            title=ft.Text("编辑任务" if is_edit else "创建新任务"),
            content=ft.Container(
                content=ft.Column(
                    [
                        title_field,
                        desc_field,
                        ft.Text("重复类型", size=12, color=ft.Colors.GREY_600),
                        rtype_row,
                        weekday_label,
                        weekday_row,
                        due_date_row,
                        ft.Text("优先级", size=12, color=ft.Colors.GREY_600),
                        prio_row,
                        type_switch,
                        reward_amount_field,
                        penalty_switch,
                        penalty_amount_field,
                        enabled_switch,
                    ],
                    tight=True,
                    spacing=10,
                    scroll=ft.ScrollMode.AUTO,
                ),
                width=360,
                height=520,
            ),
            actions=[
                ft.TextButton("删除", on_click=on_delete, style=ft.ButtonStyle(color=ft.Colors.RED), visible=is_edit),
                ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton("保存", on_click=on_save),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)

    async def _do_delete_task(self, task_id: int):
        self.page.pop_dialog()
        await delete_task(task_id)
        self._show_snack("任务已删除")
        await self._refresh_ui()

    # ------------------------------------------------------------------ #
    # Build
    # ------------------------------------------------------------------ #

    async def build(self) -> ft.Control:
        await self.load_data()
        self._update_fab()

        async def on_tab_change(e):
            self._tab_index = e.control.selected_index
            await self._refresh_ui()
            if self._content_area:
                self._content_area.update()

        tab_bar = ft.Tabs(
            selected_index=0,
            on_change=on_tab_change,
            tabs=[
                ft.Tab(label="今日", icon=ft.Icons.TODAY),
                ft.Tab(label="全部", icon=ft.Icons.LIST),
            ],
            expand=True,
        )

        # Build initial views
        self._today_col = ft.Column(
            self._build_today_view(),
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
        )
        self._all_col = ft.Column(
            self._build_all_view(),
            spacing=8,
            scroll=ft.ScrollMode.AUTO,
        )

        self._content_area = ft.Container(
            content=ft.Column(
                [
                    tab_bar,
                    ft.Container(
                        content=ft.Column(
                            [self._today_col],  # will be swapped
                            spacing=8,
                        ),
                        expand=True,
                    ),
                ],
                expand=True,
            ),
            padding=ft.padding.all(16),
            expand=True,
        )

        # Actually, Tabs with TabBarView is a better pattern for content switching.
        # But since we need independent scroll positions, let me use a simple approach:
        # Show today_col or all_col based on tab selection.
        # Use a single container that swaps content.

        # Let me rebuild with a simpler approach — no TabBarView, just manual swapping
        tab_content = ft.Container(expand=True)

        async def on_tab_change2(e):
            idx = e.control.selected_index
            tab_content.content = self._today_col if idx == 0 else self._all_col
            tab_content.update()

        tab_bar2 = ft.Tabs(
            selected_index=0,
            on_change=on_tab_change2,
            tabs=[
                ft.Tab(label="今日", icon=ft.Icons.TODAY),
                ft.Tab(label="全部", icon=ft.Icons.LIST),
            ],
            expand=True,
        )
        tab_content.content = self._today_col

        return ft.Container(
            content=ft.Column(
                [tab_bar2, tab_content],
                expand=True,
                spacing=0,
            ),
            padding=ft.padding.all(16),
            expand=True,
        )
