"""首页。展示奖金余额、按月分组账单和快捷操作入口。"""

from collections import defaultdict
from datetime import datetime

import flet as ft
from loguru import logger

from core.config import (
    CONFIRM_MODE_ALWAYS,
    CONFIRM_MODE_SMART,
    CONFIRM_MODE_SILENT,
    CONFIDENCE_THRESHOLD_SMART,
    CONFIDENCE_THRESHOLD_REVIEW,
)
from models.transaction import Transaction
from repositories.category_repo import get_all_categories, get_category_by_id, get_category_by_name
from repositories.transaction_repo import get_all_transactions
from services.ai_service import analyze_text, AIParseResult
from services.logic_service import get_bonus_balance, record_transaction
from ui.components.stat_card import BalanceCard


class HomePage:
    """首页控制器。"""

    def __init__(self, page: ft.Page):
        self.page = page
        self.balance: float = 0.0
        self.recent_transactions: list[Transaction] = []
        self.categories: list[str] = []
        self._category_map: dict[int, str] = {}
        self._settings = None
        self._content_column: ft.Column | None = None
        self._txn_container: ft.Container | None = None

        now = datetime.now()
        self._current_year: int = now.year
        self._current_month: int = now.month
        self._search_text: str = ""

        # 搜索框（常驻对象，避免每次刷新重置输入）
        async def _on_search_change(e):
            self._search_text = e.control.value
            if self._txn_container:
                self._txn_container.content = self._build_txn_list()
                self._txn_container.update()

        self._search_field = ft.TextField(
            hint_text="搜索描述或分类...",
            prefix_icon=ft.Icons.SEARCH,
            on_change=_on_search_change,
            height=44,
            content_padding=ft.padding.symmetric(vertical=8, horizontal=12),
            border_radius=22,
            border_color=ft.Colors.GREY_300,
        )

    def _show_snack(self, message: str, bgcolor: str = None):
        """显示 SnackBar 提示。"""
        snack = ft.SnackBar(content=ft.Text(message), open=True)
        if bgcolor:
            snack.bgcolor = bgcolor
        self.page.overlay.append(snack)
        self.page.update()

    async def _load_settings(self):
        """加载应用设置。"""
        from core.database import get_session
        from models.settings import AppSettings
        from sqlmodel import select

        async with get_session() as session:
            result = await session.execute(select(AppSettings))
            self._settings = result.scalars().first()
            if not self._settings:
                self._settings = AppSettings()
                session.add(self._settings)

    async def load_data(self):
        """加载当前月份的账单数据。"""
        try:
            start = datetime(self._current_year, self._current_month, 1)
            if self._current_month == 12:
                end = datetime(self._current_year + 1, 1, 1)
            else:
                end = datetime(self._current_year, self._current_month + 1, 1)

            self.balance = await get_bonus_balance()
            self.recent_transactions = await get_all_transactions(
                start_date=start, end_date=end
            )
            cats = await get_all_categories()
            self.categories = [c.name for c in cats]
            self._category_map = {c.id: c.name for c in cats}
            await self._load_settings()
        except Exception as e:
            logger.error(f"加载首页数据失败: {e}")

    # ------------------------------------------------------------------ #
    # 月份导航
    # ------------------------------------------------------------------ #

    async def _prev_month(self, e=None):
        if self._current_month == 1:
            self._current_month = 12
            self._current_year -= 1
        else:
            self._current_month -= 1
        await self.load_data()
        await self._refresh_ui()

    async def _next_month(self, e=None):
        now = datetime.now()
        is_current = (
            self._current_year == now.year and self._current_month == now.month
        )
        if not is_current:
            if self._current_month == 12:
                self._current_month = 1
                self._current_year += 1
            else:
                self._current_month += 1
            await self.load_data()
            await self._refresh_ui()

    def _build_month_nav(self) -> ft.Row:
        now = datetime.now()
        is_current = (
            self._current_year == now.year and self._current_month == now.month
        )
        return ft.Row(
            [
                ft.IconButton(
                    ft.Icons.CHEVRON_LEFT,
                    icon_size=20,
                    on_click=lambda e: self.page.run_task(self._prev_month),
                ),
                ft.Text(
                    f"{self._current_year}年{self._current_month}月",
                    size=15,
                    weight=ft.FontWeight.BOLD,
                    expand=True,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.IconButton(
                    ft.Icons.CHEVRON_RIGHT,
                    icon_size=20,
                    disabled=is_current,
                    on_click=lambda e: self.page.run_task(self._next_month),
                ),
            ],
        )

    # ------------------------------------------------------------------ #
    # 月度概览
    # ------------------------------------------------------------------ #

    def _build_monthly_summary(self) -> ft.Container:
        total = sum(t.amount for t in self.recent_transactions)
        bonus = sum(
            t.amount for t in self.recent_transactions if t.is_bonus_related
        )
        count = len(self.recent_transactions)
        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text("本月支出", size=11, color=ft.Colors.GREY_500),
                            ft.Text(
                                f"¥{total:.2f}",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text(
                                f"共 {count} 笔",
                                size=11,
                                color=ft.Colors.GREY_400,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=2,
                        expand=True,
                    ),
                    ft.Container(width=1, height=36, bgcolor=ft.Colors.GREY_300),
                    ft.Column(
                        [
                            ft.Text("奖金核销", size=11, color=ft.Colors.GREY_500),
                            ft.Text(
                                f"¥{bonus:.2f}",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color=(
                                    ft.Colors.RED_400 if bonus > 0 else ft.Colors.GREY_600
                                ),
                            ),
                            ft.Text(
                                f"占 {bonus/total*100:.0f}%" if total > 0 else "—",
                                size=11,
                                color=ft.Colors.GREY_400,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=2,
                        expand=True,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            bgcolor=ft.Colors.SURFACE_CONTAINER,
            border_radius=8,
            padding=ft.padding.symmetric(vertical=10, horizontal=16),
        )

    # ------------------------------------------------------------------ #
    # 账单列表（按日分组）
    # ------------------------------------------------------------------ #

    def _build_txn_list(self) -> ft.Control:
        search = self._search_text.strip().lower()
        filtered = [
            t for t in self.recent_transactions
            if not search
            or search in (t.description or "").lower()
            or search in self._category_map.get(t.category_id, "").lower()
        ]

        if not filtered:
            empty_text = "没有符合条件的账单" if search else "本月暂无账单记录"
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(
                            ft.Icons.RECEIPT_LONG, size=48, color=ft.Colors.GREY_300
                        ),
                        ft.Text(empty_text, color=ft.Colors.GREY_400),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                alignment=ft.Alignment.CENTER,
                padding=40,
            )

        groups: dict = defaultdict(list)
        for txn in filtered:
            groups[txn.transaction_date.date()].append(txn)

        result: list[ft.Control] = []
        for day in sorted(groups.keys(), reverse=True):
            day_txns = groups[day]
            day_total = sum(t.amount for t in day_txns)

            result.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(
                                f"{day.month}月{day.day}日",
                                size=12,
                                weight=ft.FontWeight.W_600,
                                color=ft.Colors.GREY_700,
                            ),
                            ft.Text(
                                f"-¥{day_total:.2f}",
                                size=12,
                                color=ft.Colors.GREY_500,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    padding=ft.padding.only(left=4, right=4, top=12, bottom=4),
                )
            )
            for txn in day_txns:
                result.append(self._build_transaction_tile(txn))

        return ft.Column(result, spacing=0)

    def _build_transaction_tile(self, txn: Transaction) -> ft.Container:
        """构建单条账单列表项（点击进入详情）。"""
        needs_review = (
            not txn.is_verified and txn.ai_confidence < CONFIDENCE_THRESHOLD_REVIEW
        )
        cat_name = self._category_map.get(txn.category_id, "")

        subtitle_parts = []
        if cat_name:
            subtitle_parts.append(cat_name)
        subtitle_parts.append(txn.transaction_date.strftime("%H:%M"))
        if needs_review:
            subtitle_parts.append("需复核")

        async def on_tile_click(e, t=txn):
            await self._show_transaction_detail(t)

        return ft.Container(
            content=ft.ListTile(
                leading=ft.Icon(
                    ft.Icons.WARNING_AMBER if needs_review else ft.Icons.RECEIPT_LONG,
                    color=ft.Colors.ORANGE if needs_review else ft.Colors.GREY_500,
                ),
                title=ft.Text(
                    txn.description or "无描述",
                    size=14,
                    weight=ft.FontWeight.W_500,
                ),
                subtitle=ft.Text(
                    " · ".join(subtitle_parts),
                    size=12,
                    color=(
                        ft.Colors.ORANGE_700 if needs_review else ft.Colors.GREY_500
                    ),
                ),
                trailing=ft.Text(
                    f"-¥{txn.amount:.2f}",
                    size=15,
                    weight=ft.FontWeight.BOLD,
                    color=(
                        ft.Colors.RED if txn.is_bonus_related else ft.Colors.GREY_700
                    ),
                ),
                on_click=on_tile_click,
            ),
            border=ft.border.only(bottom=ft.BorderSide(1, ft.Colors.GREY_200)),
        )

    # ------------------------------------------------------------------ #
    # 账单详情
    # ------------------------------------------------------------------ #

    async def _show_transaction_detail(self, txn: Transaction):
        """显示账单详情对话框（含编辑/删除入口）。"""
        currency = self._settings.currency_symbol if self._settings else "¥"
        cat_name = self._category_map.get(txn.category_id, "其他")
        needs_review = (
            not txn.is_verified and txn.ai_confidence < CONFIDENCE_THRESHOLD_REVIEW
        )

        def detail_row(label: str, value: str, value_color=None) -> ft.Row:
            return ft.Row(
                [
                    ft.Text(
                        label,
                        size=13,
                        color=ft.Colors.GREY_500,
                        width=72,
                    ),
                    ft.Text(
                        value,
                        size=13,
                        color=value_color,
                        expand=True,
                    ),
                ],
                spacing=8,
            )

        content_items: list[ft.Control] = [
            ft.Container(
                content=ft.Text(
                    f"{currency}{txn.amount:.2f}",
                    size=36,
                    weight=ft.FontWeight.BOLD,
                    color=(
                        ft.Colors.RED if txn.is_bonus_related else ft.Colors.GREY_800
                    ),
                    text_align=ft.TextAlign.CENTER,
                ),
                alignment=ft.Alignment.CENTER,
                padding=ft.padding.symmetric(vertical=8),
            ),
            ft.Divider(height=1),
            detail_row("描述", txn.description or "—"),
            detail_row("分类", cat_name),
            detail_row(
                "时间", txn.transaction_date.strftime("%Y-%m-%d %H:%M")
            ),
            detail_row(
                "奖金核销",
                "是" if txn.is_bonus_related else "否",
                ft.Colors.RED if txn.is_bonus_related else None,
            ),
        ]

        if needs_review:
            content_items.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.WARNING_AMBER,
                                size=14,
                                color=ft.Colors.ORANGE,
                            ),
                            ft.Text(
                                "AI 置信度低，建议复核",
                                size=12,
                                color=ft.Colors.ORANGE,
                            ),
                        ],
                        spacing=4,
                    ),
                    padding=ft.padding.only(top=4),
                )
            )

        async def on_edit(e):
            self.page.pop_dialog()
            await self._show_edit_transaction(txn)

        async def on_delete_click(e):
            self.page.pop_dialog()

            async def do_delete_confirmed(e2):
                await self._do_delete_txn(txn.id)

            confirm = ft.AlertDialog(
                title=ft.Text("确认删除"),
                content=ft.Text("删除后无法恢复，确定要删除这条账单吗？"),
                actions=[
                    ft.TextButton(
                        "取消", on_click=lambda e: self.page.pop_dialog()
                    ),
                    ft.FilledButton(
                        "删除",
                        on_click=do_delete_confirmed,
                        style=ft.ButtonStyle(bgcolor=ft.Colors.RED),
                    ),
                ],
            )
            self.page.show_dialog(confirm)

        dialog = ft.AlertDialog(
            title=ft.Text("账单详情"),
            content=ft.Container(
                content=ft.Column(content_items, spacing=10, tight=True),
                width=350,
            ),
            actions=[
                ft.TextButton(
                    "删除",
                    on_click=on_delete_click,
                    style=ft.ButtonStyle(color=ft.Colors.RED),
                ),
                ft.TextButton(
                    "关闭", on_click=lambda e: self.page.pop_dialog()
                ),
                ft.FilledButton("编辑", on_click=on_edit),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)

    # ------------------------------------------------------------------ #
    # AI / 语音记账
    # ------------------------------------------------------------------ #

    async def _on_voice_submit(self, text: str):
        """处理语音/文本输入提交。"""
        self._show_snack("AI 正在分析...")

        api_url = self._settings.api_base_url if self._settings else ""
        model = self._settings.model_name if self._settings else ""
        result = await analyze_text(text, api_url, model)

        if result.fallback:
            self._show_snack(
                f"AI 解析失败: {result.error}，请手动填写", ft.Colors.ORANGE_100
            )
            await self._show_manual_input(description=text)
            return

        confirm_mode = (
            self._settings.confirm_mode if self._settings else CONFIRM_MODE_ALWAYS
        )

        if confirm_mode == CONFIRM_MODE_ALWAYS:
            await self._show_confirm_dialog(result)
        elif confirm_mode == CONFIRM_MODE_SMART:
            if result.confidence < CONFIDENCE_THRESHOLD_SMART:
                await self._show_confirm_dialog(result)
            else:
                await self._save_transaction(
                    result.amount,
                    result.category,
                    True,  # default all to bonus
                    result.summary,
                    result.confidence,
                    is_verified=True,
                )
        elif confirm_mode == CONFIRM_MODE_SILENT:
            is_verified = result.confidence >= CONFIDENCE_THRESHOLD_REVIEW
            await self._save_transaction(
                result.amount,
                result.category,
                True,  # default all to bonus
                result.summary,
                result.confidence,
                is_verified=is_verified,
            )
            if not is_verified:
                self._show_snack(
                    "已保存，但 AI 置信度较低，建议复核", ft.Colors.ORANGE_100
                )

    async def _show_confirm_dialog(self, result: AIParseResult):
        """显示 AI 解析结果确认对话框。"""
        currency = self._settings.currency_symbol if self._settings else "¥"

        amount_field = ft.TextField(
            label="金额",
            value=str(result.amount),
            keyboard_type=ft.KeyboardType.NUMBER,
            prefix=ft.Text(currency),
        )
        category_dropdown = ft.Dropdown(
            label="分类",
            value=result.category,
            options=[ft.dropdown.Option(key=c, text=c) for c in self.categories],
        )
        reimburse_switch = ft.Switch(label="从奖金扣除", value=True)
        summary_field = ft.TextField(label="描述", value=result.summary)

        confidence_color = (
            ft.Colors.GREEN
            if result.confidence >= 0.8
            else ft.Colors.ORANGE
            if result.confidence >= 0.5
            else ft.Colors.RED
        )

        async def on_confirm(e):
            try:
                amount = float(amount_field.value)
            except ValueError:
                amount_field.error_text = "请输入有效金额"
                amount_field.update()
                return
            if amount <= 0:
                amount_field.error_text = "金额必须大于0"
                amount_field.update()
                return
            self.page.pop_dialog()
            await self._save_transaction(
                amount,
                category_dropdown.value,
                reimburse_switch.value,
                summary_field.value,
                1.0,
                True,
            )

        dialog = ft.AlertDialog(
            title=ft.Text("确认账单"),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text("AI 置信度: ", size=12),
                                ft.Text(
                                    f"{result.confidence:.0%}",
                                    size=12,
                                    weight=ft.FontWeight.BOLD,
                                    color=confidence_color,
                                ),
                            ]
                        ),
                        amount_field,
                        category_dropdown,
                        summary_field,
                        reimburse_switch,
                    ],
                    tight=True,
                    spacing=12,
                ),
                width=350,
            ),
            actions=[
                ft.TextButton(
                    "取消", on_click=lambda e: self.page.pop_dialog()
                ),
                ft.FilledButton("确认保存", on_click=on_confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)

    async def _save_transaction(
        self,
        amount: float,
        category: str,
        is_reimbursable: bool,
        description: str,
        confidence: float,
        is_verified: bool,
    ):
        """保存账单到数据库。"""
        try:
            await record_transaction(
                amount=amount,
                category_name=category,
                description=description,
                is_bonus_related=is_reimbursable,
                ai_confidence=confidence,
                is_verified=is_verified,
            )
            self._show_snack(
                f"已记录: {description} ¥{amount:.2f}"
                + (" (奖金扣除)" if is_reimbursable else ""),
                ft.Colors.GREEN_100,
            )
            await self.load_data()
            await self._refresh_ui()
        except Exception as e:
            logger.error(f"保存账单失败: {e}")
            self._show_snack(f"保存失败: {e}", ft.Colors.RED_100)

    async def _show_manual_input(self, description: str = ""):
        """显示手动记账对话框。"""
        currency = self._settings.currency_symbol if self._settings else "¥"
        amount_field = ft.TextField(
            label="金额",
            keyboard_type=ft.KeyboardType.NUMBER,
            prefix=ft.Text(currency),
        )
        category_dropdown = ft.Dropdown(
            label="分类",
            value="其他",
            options=[ft.dropdown.Option(key=c, text=c) for c in self.categories],
        )
        desc_field = ft.TextField(label="描述", value=description)
        reimburse_switch = ft.Switch(label="从奖金扣除", value=True)

        async def on_save(e):
            try:
                amt = float(amount_field.value)
            except (ValueError, TypeError):
                amount_field.error_text = "请输入有效金额"
                amount_field.update()
                return
            if amt <= 0:
                amount_field.error_text = "金额必须大于0"
                amount_field.update()
                return
            self.page.pop_dialog()
            await self._save_transaction(
                amount=amt,
                category=category_dropdown.value,
                is_reimbursable=reimburse_switch.value,
                description=desc_field.value,
                confidence=1.0,
                is_verified=True,
            )

        dialog = ft.AlertDialog(
            title=ft.Text("手动记账"),
            content=ft.Container(
                content=ft.Column(
                    [amount_field, category_dropdown, desc_field, reimburse_switch],
                    tight=True,
                    spacing=12,
                ),
                width=350,
            ),
            actions=[
                ft.TextButton(
                    "取消", on_click=lambda e: self.page.pop_dialog()
                ),
                ft.FilledButton("保存", on_click=on_save),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)

    # ------------------------------------------------------------------ #
    # 编辑账单
    # ------------------------------------------------------------------ #

    async def _show_edit_transaction(self, txn: Transaction):
        """显示编辑账单对话框。"""
        from repositories.transaction_repo import update_transaction

        currency = self._settings.currency_symbol if self._settings else "¥"
        amount_field = ft.TextField(
            label="金额",
            value=str(txn.amount),
            keyboard_type=ft.KeyboardType.NUMBER,
            prefix=ft.Text(currency),
        )
        category_dropdown = ft.Dropdown(
            label="分类",
            options=[
                ft.dropdown.Option(key=c, text=c) for c in self.categories
            ],
        )
        # 设置当前分类
        current_cat = self._category_map.get(txn.category_id, "其他")
        category_dropdown.value = current_cat

        desc_field = ft.TextField(label="描述", value=txn.description)
        reimburse_switch = ft.Switch(
            label="从奖金扣除", value=txn.is_bonus_related
        )

        async def on_save(e):
            try:
                txn.amount = float(amount_field.value)
            except ValueError:
                amount_field.error_text = "请输入有效金额"
                amount_field.update()
                return
            cat = await get_category_by_name(category_dropdown.value)
            if cat:
                txn.category_id = cat.id
            txn.description = desc_field.value
            txn.is_bonus_related = reimburse_switch.value
            txn.is_verified = True
            await update_transaction(txn)
            self.page.pop_dialog()
            await self.load_data()
            await self._refresh_ui()

        dialog = ft.AlertDialog(
            title=ft.Text("编辑账单"),
            content=ft.Container(
                content=ft.Column(
                    [amount_field, category_dropdown, desc_field, reimburse_switch],
                    tight=True,
                    spacing=12,
                ),
                width=350,
            ),
            actions=[
                ft.TextButton(
                    "取消", on_click=lambda e: self.page.pop_dialog()
                ),
                ft.FilledButton("保存", on_click=on_save),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)

    async def _do_delete_txn(self, txn_id: int):
        """执行删除账单。"""
        from repositories.transaction_repo import delete_transaction

        self.page.pop_dialog()
        await delete_transaction(txn_id)
        self._show_snack("账单已删除")
        await self.load_data()
        await self._refresh_ui()

    # ------------------------------------------------------------------ #
    # 快捷操作
    # ------------------------------------------------------------------ #

    def _build_quick_actions(self) -> ft.Row:
        """构建快捷操作按钮行。"""
        return ft.Row(
            [
                ft.Button(
                    "语音记账",
                    icon=ft.Icons.MIC,
                    on_click=self._on_voice_btn_click,
                    style=ft.ButtonStyle(
                        bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE
                    ),
                    expand=True,
                ),
                ft.Button(
                    "手动记账",
                    icon=ft.Icons.EDIT_NOTE,
                    on_click=self._on_manual_btn_click,
                    expand=True,
                ),
            ],
            spacing=12,
        )

    # ------------------------------------------------------------------ #
    # 刷新 UI
    # ------------------------------------------------------------------ #

    async def _refresh_ui(self):
        """刷新首页内容。"""
        if self._content_column:
            currency = self._settings.currency_symbol if self._settings else "¥"
            balance_card = BalanceCard(self.balance, currency_symbol=currency)
            self._txn_container = ft.Container(
                content=self._build_txn_list()
            )
            self._content_column.controls = [
                balance_card,
                self._build_monthly_summary(),
                self._build_quick_actions(),
                self._build_month_nav(),
                self._search_field,
                self._txn_container,
            ]
            self._content_column.update()

    async def build(self) -> ft.Control:
        """构建首页视图。"""
        await self.load_data()

        currency = self._settings.currency_symbol if self._settings else "¥"
        balance_card = BalanceCard(self.balance, currency_symbol=currency)

        self._txn_container = ft.Container(content=self._build_txn_list())

        self._content_column = ft.Column(
            [
                balance_card,
                self._build_monthly_summary(),
                self._build_quick_actions(),
                self._build_month_nav(),
                self._search_field,
                self._txn_container,
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
        )

        return ft.Container(
            content=self._content_column,
            padding=ft.padding.all(16),
            expand=True,
        )

    async def _on_voice_btn_click(self, e: ft.ControlEvent):
        """语音记账按钮点击。"""
        text_field = ft.TextField(
            label="描述你的消费",
            hint_text="例如：买了杯咖啡花了35元，算奖金里",
            multiline=True,
            min_lines=2,
            max_lines=4,
            autofocus=True,
            prefix_icon=ft.Icons.MIC,
        )

        async def on_submit(e):
            text = text_field.value.strip()
            if not text:
                text_field.error_text = "请输入内容"
                text_field.update()
                return
            self.page.pop_dialog()
            await self._on_voice_submit(text)

        dialog = ft.AlertDialog(
            title=ft.Text("语音记账"),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "请输入或使用键盘语音按钮描述消费：",
                            size=14,
                            color=ft.Colors.GREY_600,
                        ),
                        text_field,
                    ],
                    tight=True,
                ),
                width=350,
            ),
            actions=[
                ft.TextButton(
                    "取消", on_click=lambda e: self.page.pop_dialog()
                ),
                ft.FilledButton("提交", on_click=on_submit),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)

    async def _on_manual_btn_click(self, e: ft.ControlEvent):
        """手动记账按钮点击。"""
        await self._show_manual_input()
