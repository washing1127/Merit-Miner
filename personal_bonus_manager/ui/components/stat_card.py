"""统计卡片组件。用于展示统计数据的可复用 UI 组件。"""

import flet as ft


class StatCard(ft.Card):
    """统计数据卡片。显示标题、数值和可选的图标/颜色。"""

    def __init__(
        self,
        title: str,
        value: str,
        icon: str = None,
        color: str = None,
        subtitle: str = None,
        value_color: str = None,
    ):
        content = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(icon, size=20, color=color)
                            if icon
                            else ft.Container(),
                            ft.Text(
                                title,
                                size=13,
                                color=ft.Colors.GREY_600,
                                weight=ft.FontWeight.W_500,
                            ),
                        ],
                        spacing=6,
                    ),
                    ft.Text(
                        value,
                        size=24,
                        weight=ft.FontWeight.BOLD,
                        color=value_color or color,
                    ),
                    ft.Text(
                        subtitle,
                        size=11,
                        color=ft.Colors.GREY_500,
                    )
                    if subtitle
                    else ft.Container(),
                ],
                spacing=4,
            ),
            padding=ft.padding.all(16),
        )
        super().__init__(content=content, elevation=2)


class BalanceCard(ft.Card):
    """奖金余额大字卡片。余额允许负数，负数红色显示。"""

    def __init__(self, balance: float, currency_symbol: str = "¥"):
        is_negative = balance < 0
        balance_color = ft.Colors.RED if is_negative else ft.Colors.GREEN
        balance_text = f"{currency_symbol}{balance:,.2f}"

        content = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "当前可用余额",
                        size=14,
                        color=ft.Colors.GREY_600,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Text(
                        balance_text,
                        size=36,
                        weight=ft.FontWeight.BOLD,
                        color=balance_color,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Text(
                        "余额不足" if is_negative else "余额充足",
                        size=12,
                        color=balance_color,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                spacing=4,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.all(24),
            alignment=ft.Alignment.CENTER,
        )
        super().__init__(
            content=content,
            elevation=4,
            bgcolor=ft.Colors.with_opacity(0.05, balance_color),
        )


class TaskStreakCard(ft.Card):
    """任务打卡卡片。显示任务名称、连续天数和打卡按钮。"""

    def __init__(
        self,
        title: str,
        streak: int,
        max_streak: int,
        is_checked_today: bool,
        reward_amount: float = 0,
        is_reward_task: bool = False,
        on_checkin: callable = None,
        on_makeup: callable = None,
        on_edit: callable = None,
    ):
        self._on_checkin = on_checkin
        self._on_makeup = on_makeup

        # 打卡按钮
        checkin_btn = ft.IconButton(
            icon=ft.Icons.CHECK_CIRCLE if is_checked_today
            else ft.Icons.CHECK_CIRCLE_OUTLINE,
            icon_color=ft.Colors.GREEN if is_checked_today
            else ft.Colors.GREY_400,
            icon_size=36,
            on_click=on_checkin,
            disabled=is_checked_today,
            tooltip="今日已打卡" if is_checked_today else "点击打卡",
        )

        # 任务信息
        info_col = ft.Column(
            [
                ft.Text(title, size=16, weight=ft.FontWeight.W_600),
                ft.Row(
                    [
                        ft.Icon(ft.Icons.LOCAL_FIRE_DEPARTMENT, size=14,
                                color=ft.Colors.ORANGE),
                        ft.Text(f"连续 {streak} 天", size=13),
                        ft.Text(f"(最高 {max_streak})", size=11,
                                color=ft.Colors.GREY_500),
                    ],
                    spacing=4,
                ),
                ft.Text(
                    f"奖励 ¥{reward_amount:.2f}/次",
                    size=12,
                    color=ft.Colors.AMBER_700,
                )
                if is_reward_task and reward_amount > 0
                else ft.Container(),
            ],
            spacing=2,
            expand=True,
        )

        # 操作按钮
        actions_row = ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.HISTORY,
                    icon_size=20,
                    tooltip="补卡",
                    on_click=on_makeup,
                ),
                ft.IconButton(
                    icon=ft.Icons.EDIT,
                    icon_size=20,
                    tooltip="编辑",
                    on_click=on_edit,
                ),
            ],
            spacing=0,
        )

        content = ft.Container(
            content=ft.Row(
                [checkin_btn, info_col, actions_row],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(horizontal=12, vertical=8),
        )
        super().__init__(content=content, elevation=1)
