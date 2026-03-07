"""语音输入组件。

MVP 阶段使用 TextField 结合系统输入法麦克风按钮（策略 A）。
用户点击输入框后可使用系统键盘的语音输入功能。
后续版本可接入 Android RecognizerIntent 实现一键录音。
"""

import flet as ft
from loguru import logger


class VoiceInputDialog(ft.AlertDialog):
    """语音/文本输入对话框。

    用户可以通过文本输入（支持系统键盘的语音功能）描述消费，
    提交后由 AI 解析或进入手动填写模式。
    """

    def __init__(self, on_submit: callable, on_cancel: callable = None):
        self.text_field = ft.TextField(
            label="描述你的消费",
            hint_text="例如：买了杯咖啡花了35元，算奖金里",
            multiline=True,
            min_lines=2,
            max_lines=4,
            autofocus=True,
            prefix_icon=ft.Icons.MIC,
        )
        self._on_submit = on_submit
        self._on_cancel = on_cancel

        super().__init__(
            title=ft.Text("语音记账"),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "请输入或使用键盘语音按钮描述消费：",
                            size=14,
                            color=ft.Colors.GREY_600,
                        ),
                        self.text_field,
                    ],
                    tight=True,
                ),
                width=350,
            ),
            actions=[
                ft.TextButton("取消", on_click=self._handle_cancel),
                ft.FilledButton("提交", on_click=self._handle_submit),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    async def _handle_submit(self, e: ft.ControlEvent):
        text = self.text_field.value.strip()
        if not text:
            self.text_field.error_text = "请输入内容"
            self.text_field.update()
            return
        self.open = False
        self.update()
        if self._on_submit:
            await self._on_submit(text)

    async def _handle_cancel(self, e: ft.ControlEvent):
        self.open = False
        self.update()
        if self._on_cancel:
            await self._on_cancel()


class TransactionConfirmDialog(ft.AlertDialog):
    """AI 解析结果确认对话框。

    显示 AI 解析的金额、分类、是否核销等信息，用户可修改后确认。
    """

    def __init__(
        self,
        amount: float,
        category: str,
        is_reimbursable: bool,
        summary: str,
        confidence: float,
        categories: list[str],
        on_confirm: callable,
        on_cancel: callable = None,
        currency_symbol: str = "¥",
    ):
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel

        self.amount_field = ft.TextField(
            label="金额",
            value=str(amount),
            keyboard_type=ft.KeyboardType.NUMBER,
            prefix_text=currency_symbol,
        )

        self.category_dropdown = ft.Dropdown(
            label="分类",
            value=category,
            options=[ft.dropdown.Option(c) for c in categories],
        )

        self.reimburse_switch = ft.Switch(
            label="从奖金扣除",
            value=is_reimbursable,
        )

        self.summary_field = ft.TextField(
            label="描述",
            value=summary,
        )

        confidence_color = (
            ft.Colors.GREEN if confidence >= 0.8
            else ft.Colors.ORANGE if confidence >= 0.5
            else ft.Colors.RED
        )

        super().__init__(
            title=ft.Text("确认账单"),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text("AI 置信度: ", size=12),
                                ft.Text(
                                    f"{confidence:.0%}",
                                    size=12,
                                    weight=ft.FontWeight.BOLD,
                                    color=confidence_color,
                                ),
                            ]
                        ),
                        self.amount_field,
                        self.category_dropdown,
                        self.summary_field,
                        self.reimburse_switch,
                    ],
                    tight=True,
                    spacing=12,
                ),
                width=350,
            ),
            actions=[
                ft.TextButton("取消", on_click=self._handle_cancel),
                ft.FilledButton("确认保存", on_click=self._handle_confirm),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    async def _handle_confirm(self, e: ft.ControlEvent):
        try:
            amount = float(self.amount_field.value)
        except ValueError:
            self.amount_field.error_text = "请输入有效金额"
            self.amount_field.update()
            return

        if amount <= 0:
            self.amount_field.error_text = "金额必须大于0"
            self.amount_field.update()
            return

        self.open = False
        self.update()
        if self._on_confirm:
            await self._on_confirm(
                amount=amount,
                category=self.category_dropdown.value,
                is_reimbursable=self.reimburse_switch.value,
                description=self.summary_field.value,
            )

    async def _handle_cancel(self, e: ft.ControlEvent):
        self.open = False
        self.update()
        if self._on_cancel:
            await self._on_cancel()
