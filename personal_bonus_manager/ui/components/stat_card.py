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


def TaskStreakCard(
    title: str,
    streak: int,
    max_streak: int,
    is_checked_today: bool,
    reward_amount: float = 0,
    is_reward_task: bool = False,
    on_checkin=None,
    on_makeup=None,
    on_edit=None,
) -> ft.Card:
    """任务打卡卡片。使用 ListTile 布局确保事件正常响应。"""

    # 打卡按钮（leading 区域）
    checkin_icon = ft.Container(
        content=ft.Icon(
            ft.Icons.CHECK_CIRCLE if is_checked_today
            else ft.Icons.CHECK_CIRCLE_OUTLINE,
            color=ft.Colors.GREEN if is_checked_today else ft.Colors.GREY_400,
            size=32,
        ),
        on_click=None if is_checked_today else on_checkin,
        tooltip="今日已打卡" if is_checked_today else "点击打卡",
        padding=ft.padding.all(4),
    )

    # 副标题：连击信息
    reward_text = (
        ft.Text(f"  奖励 ¥{reward_amount:.2f}/次", size=11, color=ft.Colors.AMBER_700)
        if is_reward_task and reward_amount > 0
        else ft.Text("")
    )
    subtitle = ft.Row(
        [
            ft.Icon(ft.Icons.LOCAL_FIRE_DEPARTMENT, size=13, color=ft.Colors.ORANGE),
            ft.Text(f"连续 {streak} 天", size=12),
            ft.Text(f"(最高 {max_streak})", size=11, color=ft.Colors.GREY_500),
            reward_text,
        ],
        spacing=4,
    )

    # 操作按钮（trailing 区域）
    trailing = ft.Row(
        [
            ft.IconButton(
                icon=ft.Icons.HISTORY, icon_size=20, tooltip="补卡", on_click=on_makeup,
            ),
            ft.IconButton(
                icon=ft.Icons.EDIT, icon_size=20, tooltip="编辑", on_click=on_edit,
            ),
        ],
        tight=True,
        spacing=0,
    )

    return ft.Card(
        content=ft.ListTile(
            leading=checkin_icon,
            title=ft.Text(title, size=15, weight=ft.FontWeight.W_600),
            subtitle=subtitle,
            trailing=trailing,
            on_click=on_edit,
        ),
        elevation=1,
    )
