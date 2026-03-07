"""首页。展示奖金余额、最近账单和快捷操作入口。"""

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
from repositories.category_repo import get_all_categories, get_category_by_id
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
        self._settings = None
        self._content_column: ft.Column | None = None

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
        """加载首页数据。"""
        try:
            self.balance = await get_bonus_balance()
            self.recent_transactions = await get_all_transactions()
            cats = await get_all_categories()
            self.categories = [c.name for c in cats]
            await self._load_settings()
        except Exception as e:
            logger.error(f"加载首页数据失败: {e}")

    async def _on_voice_submit(self, text: str):
        """处理语音/文本输入提交。"""
        self._show_snack("AI 正在分析...")

        # 调用 AI 服务
        api_url = self._settings.api_base_url if self._settings else ""
        model = self._settings.model_name if self._settings else ""
        result = await analyze_text(text, api_url, model)

        if result.fallback:
            self._show_snack(f"AI 解析失败: {result.error}，请手动填写", ft.Colors.ORANGE_100)
            await self._show_manual_input(description=text)
            return

        # 根据确认模式处理
        confirm_mode = self._settings.confirm_mode if self._settings else CONFIRM_MODE_ALWAYS

        if confirm_mode == CONFIRM_MODE_ALWAYS:
            await self._show_confirm_dialog(result)
        elif confirm_mode == CONFIRM_MODE_SMART:
            if result.confidence < CONFIDENCE_THRESHOLD_SMART:
                await self._show_confirm_dialog(result)
            else:
                await self._save_transaction(
                    result.amount, result.category, result.is_reimbursable,
                    result.summary, result.confidence, is_verified=True,
                )
        elif confirm_mode == CONFIRM_MODE_SILENT:
            is_verified = result.confidence >= CONFIDENCE_THRESHOLD_REVIEW
            await self._save_transaction(
                result.amount, result.category, result.is_reimbursable,
                result.summary, result.confidence, is_verified=is_verified,
            )
            if not is_verified:
                self._show_snack("已保存，但 AI 置信度较低，建议复核", ft.Colors.ORANGE_100)

    async def _show_confirm_dialog(self, result: AIParseResult):
        """显示 AI 解析结果确认对话框。"""
        currency = self._settings.currency_symbol if self._settings else "¥"

        amount_field = ft.TextField(
            label="金额", value=str(result.amount),
            keyboard_type=ft.KeyboardType.NUMBER, prefix_text=currency,
        )
        category_dropdown = ft.Dropdown(
            label="分类", value=result.category,
            options=[ft.dropdown.Option(key=c, text=c) for c in self.categories],
        )
        reimburse_switch = ft.Switch(label="从奖金扣除", value=result.is_reimbursable)
        summary_field = ft.TextField(label="描述", value=result.summary)

        confidence_color = (
            ft.Colors.GREEN if result.confidence >= 0.8
            else ft.Colors.ORANGE if result.confidence >= 0.5
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
                amount, category_dropdown.value, reimburse_switch.value,
                summary_field.value, 1.0, True,
            )

        dialog = ft.AlertDialog(
            title=ft.Text("确认账单"),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Row([
                            ft.Text("AI 置信度: ", size=12),
                            ft.Text(f"{result.confidence:.0%}", size=12,
                                    weight=ft.FontWeight.BOLD, color=confidence_color),
                        ]),
                        amount_field, category_dropdown, summary_field, reimburse_switch,
                    ],
                    tight=True, spacing=12,
                ),
                width=350,
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton("确认保存", on_click=on_confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)

    async def _save_transaction(
        self, amount: float, category: str, is_reimbursable: bool,
        description: str, confidence: float, is_verified: bool,
    ):
        """保存账单到数据库。"""
        try:
            await record_transaction(
                amount=amount, category_name=category, description=description,
                is_bonus_related=is_reimbursable, ai_confidence=confidence,
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
            label="金额", keyboard_type=ft.KeyboardType.NUMBER, prefix_text=currency,
        )
        category_dropdown = ft.Dropdown(
            label="分类", value="其他",
            options=[ft.dropdown.Option(key=c, text=c) for c in self.categories],
        )
        desc_field = ft.TextField(label="描述", value=description)
        reimburse_switch = ft.Switch(label="从奖金扣除", value=False)

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
                amount=amt, category=category_dropdown.value,
                is_reimbursable=reimburse_switch.value,
                description=desc_field.value, confidence=1.0, is_verified=True,
            )

        dialog = ft.AlertDialog(
            title=ft.Text("手动记账"),
            content=ft.Container(
                content=ft.Column(
                    [amount_field, category_dropdown, desc_field, reimburse_switch],
                    tight=True, spacing=12,
                ),
                width=350,
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton("保存", on_click=on_save),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)

    def _build_transaction_tile(self, txn: Transaction) -> ft.Container:
        """构建账单列表项。"""
        needs_review = not txn.is_verified and txn.ai_confidence < CONFIDENCE_THRESHOLD_REVIEW

        return ft.Container(
            content=ft.ListTile(
                leading=ft.Icon(
                    ft.Icons.WARNING_AMBER if needs_review else ft.Icons.RECEIPT_LONG,
                    color=ft.Colors.ORANGE if needs_review else ft.Colors.GREY_600,
                ),
                title=ft.Text(
                    txn.description or "无描述", size=14, weight=ft.FontWeight.W_500,
                ),
                subtitle=ft.Text(
                    txn.transaction_date.strftime("%m-%d %H:%M")
                    + (" | 需复核" if needs_review else ""),
                    size=12,
                ),
                trailing=ft.Text(
                    f"-¥{txn.amount:.2f}", size=15, weight=ft.FontWeight.BOLD,
                    color=ft.Colors.RED if txn.is_bonus_related else ft.Colors.GREY_700,
                ),
                on_click=lambda e, t=txn: self.page.run_task(
                    self._show_edit_transaction(t)
                ),
            ),
            border=ft.border.only(bottom=ft.BorderSide(1, ft.Colors.GREY_200)),
        )

    async def _show_edit_transaction(self, txn: Transaction):
        """显示编辑账单对话框。"""
        from repositories.transaction_repo import update_transaction, delete_transaction
        from repositories.category_repo import get_category_by_name

        currency = self._settings.currency_symbol if self._settings else "¥"
        amount_field = ft.TextField(
            label="金额", value=str(txn.amount),
            keyboard_type=ft.KeyboardType.NUMBER, prefix_text=currency,
        )
        category_dropdown = ft.Dropdown(
            label="分类",
            options=[ft.dropdown.Option(key=c, text=c) for c in self.categories],
        )
        cat = await get_category_by_id(txn.category_id)
        if cat:
            category_dropdown.value = cat.name

        desc_field = ft.TextField(label="描述", value=txn.description)
        reimburse_switch = ft.Switch(label="从奖金扣除", value=txn.is_bonus_related)

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

        async def on_delete(e):
            self.page.pop_dialog()
            confirm = ft.AlertDialog(
                title=ft.Text("确认删除"),
                content=ft.Text("删除后无法恢复，确定要删除这条账单吗？"),
                actions=[
                    ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
                    ft.FilledButton(
                        "删除",
                        on_click=lambda e: self.page.run_task(
                            self._do_delete_txn(txn.id)
                        ),
                        style=ft.ButtonStyle(bgcolor=ft.Colors.RED),
                    ),
                ],
            )
            self.page.show_dialog(confirm)

        dialog = ft.AlertDialog(
            title=ft.Text("编辑账单"),
            content=ft.Container(
                content=ft.Column(
                    [amount_field, category_dropdown, desc_field, reimburse_switch],
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

    async def _do_delete_txn(self, txn_id: int):
        """执行删除账单。"""
        from repositories.transaction_repo import delete_transaction
        self.page.pop_dialog()
        await delete_transaction(txn_id)
        self._show_snack("账单已删除")
        await self.load_data()
        await self._refresh_ui()

    async def _refresh_ui(self):
        """刷新首页内容。"""
        if self._content_column:
            currency = self._settings.currency_symbol if self._settings else "¥"
            balance_card = BalanceCard(self.balance, currency_symbol=currency)

            txn_list = self._build_txn_list()

            self._content_column.controls = [
                balance_card,
                self._build_quick_actions(),
                ft.Row(
                    [
                        ft.Text("最近账单", size=16, weight=ft.FontWeight.BOLD),
                        ft.Text(f"共 {len(self.recent_transactions)} 条",
                                size=12, color=ft.Colors.GREY_500),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                txn_list,
            ]
            self._content_column.update()

    def _build_quick_actions(self) -> ft.Row:
        """构建快捷操作按钮行。"""
        return ft.Row(
            [
                ft.Button(
                    "语音记账", icon=ft.Icons.MIC,
                    on_click=self._on_voice_btn_click,
                    style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE, color=ft.Colors.WHITE),
                    expand=True,
                ),
                ft.Button(
                    "手动记账", icon=ft.Icons.EDIT_NOTE,
                    on_click=self._on_manual_btn_click,
                    expand=True,
                ),
            ],
            spacing=12,
        )

    def _build_txn_list(self) -> ft.Control:
        """构建账单列表。"""
        if not self.recent_transactions:
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.RECEIPT_LONG, size=48, color=ft.Colors.GREY_300),
                        ft.Text("暂无账单记录", color=ft.Colors.GREY_400),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8,
                ),
                alignment=ft.Alignment.CENTER, padding=40,
            )
        return ft.Column(
            [self._build_transaction_tile(txn) for txn in self.recent_transactions[:20]],
            spacing=0,
        )

    async def build(self) -> ft.Control:
        """构建首页视图。"""
        await self.load_data()

        currency = self._settings.currency_symbol if self._settings else "¥"
        balance_card = BalanceCard(self.balance, currency_symbol=currency)
        quick_actions = self._build_quick_actions()

        txn_header = ft.Row(
            [
                ft.Text("最近账单", size=16, weight=ft.FontWeight.BOLD),
                ft.Text(f"共 {len(self.recent_transactions)} 条",
                        size=12, color=ft.Colors.GREY_500),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        txn_list = self._build_txn_list()

        self._content_column = ft.Column(
            [balance_card, quick_actions, txn_header, txn_list],
            spacing=16,
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
            multiline=True, min_lines=2, max_lines=4,
            autofocus=True, prefix_icon=ft.Icons.MIC,
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
                        ft.Text("请输入或使用键盘语音按钮描述消费：",
                                size=14, color=ft.Colors.GREY_600),
                        text_field,
                    ],
                    tight=True,
                ),
                width=350,
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda e: self.page.pop_dialog()),
                ft.FilledButton("提交", on_click=on_submit),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dialog)

    async def _on_manual_btn_click(self, e: ft.ControlEvent):
        """手动记账按钮点击。"""
        await self._show_manual_input()
