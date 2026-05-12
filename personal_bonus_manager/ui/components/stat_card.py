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
    is_enabled: bool = True,
    description: str = "",
    priority: int = 0,
    repeat_label: str = "",
    view_mode: str = "today",  # "today" or "all"
    on_checkin=None,
    on_makeup=None,
    on_edit=None,
    on_history=None,
) -> ft.Card:
    """Task card with priority indicator and cleaner layout.

    *today* view: prominent check-in, minimal actions.
    *all* view: streak info, edit/makeup actions, enabled/disabled state.
    """
    from models.task import PRIORITY_COLORS, TaskPriority

    prio_color = PRIORITY_COLORS.get(priority, "#9E9E9E")

    # --- Priority color bar ---
    priority_bar = ft.Container(
        width=4,
        bgcolor=prio_color,
        border_radius=ft.border_radius.only(top_left=4, bottom_left=4),
    )

    # --- Check-in button (right side, today view) ---
    if view_mode == "today":
        if is_checked_today:
            checkin_btn = ft.Icon(
                ft.Icons.CHECK_CIRCLE,
                color=ft.Colors.GREEN,
                size=30,
                tooltip="今日已打卡",
            )
        elif not is_enabled:
            checkin_btn = ft.Icon(
                ft.Icons.CHECK_CIRCLE_OUTLINE,
                color=ft.Colors.GREY_300,
                size=30,
                tooltip="任务已禁用",
            )
        else:
            checkin_btn = ft.IconButton(
                icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
                icon_color=ft.Colors.GREY_400,
                icon_size=30,
                tooltip="打卡",
                on_click=on_checkin,
            )
    else:
        # All view: show streak + actions
        checkin_btn = ft.Column(
            [
                ft.Text(
                    f"{streak}天",
                    size=13,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.ORANGE if streak > 0 else ft.Colors.GREY_400,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "连续" if streak > 0 else "",
                    size=10,
                    color=ft.Colors.GREY_500,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    # --- Title row with priority and reward badges ---
    badge_widgets = []

    # Priority badge
    if priority > TaskPriority.NONE:
        prio_labels = {1: "低", 2: "中", 3: "高"}
        badge_widgets.append(
            ft.Container(
                content=ft.Text(
                    prio_labels.get(priority, ""),
                    size=10,
                    color=prio_color,
                    weight=ft.FontWeight.W_600,
                ),
                bgcolor=ft.Colors.with_opacity(0.12, prio_color),
                border_radius=4,
                padding=ft.padding.symmetric(horizontal=5, vertical=1),
            )
        )

    # Reward badge
    if is_reward_task and reward_amount > 0:
        badge_widgets.append(
            ft.Container(
                content=ft.Text(
                    f"¥{reward_amount:.0f}",
                    size=10,
                    color=ft.Colors.AMBER_700,
                    weight=ft.FontWeight.W_600,
                ),
                bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.AMBER),
                border_radius=4,
                padding=ft.padding.symmetric(horizontal=5, vertical=1),
            )
        )

    # Repeat label
    if repeat_label and view_mode == "all":
        badge_widgets.append(
            ft.Container(
                content=ft.Text(repeat_label, size=10, color=ft.Colors.GREY_500),
                bgcolor=ft.Colors.GREY_100,
                border_radius=4,
                padding=ft.padding.symmetric(horizontal=5, vertical=1),
            )
        )

    # Disabled badge
    if not is_enabled:
        badge_widgets.append(
            ft.Container(
                content=ft.Text("已禁用", size=10, color=ft.Colors.WHITE),
                bgcolor=ft.Colors.GREY_400,
                border_radius=4,
                padding=ft.padding.symmetric(horizontal=5, vertical=1),
            )
        )

    title_row = ft.Row(
        [
            ft.Text(
                title,
                size=15,
                weight=ft.FontWeight.W_600,
                color=ft.Colors.GREY_500 if not is_enabled else None,
                expand=True,
            ),
            *badge_widgets,
        ],
        spacing=6,
    )

    # --- Description preview ---
    desc_widget = ft.Container()
    if description:
        desc_widget = ft.Text(
            description[:60] + ("..." if len(description) > 60 else ""),
            size=12,
            color=ft.Colors.GREY_500,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )

    # --- Subtitle (streak info for today, nothing for all) ---
    if view_mode == "today" and is_reward_task and reward_amount > 0:
        subtitle = ft.Text(
            f"奖励 ¥{reward_amount:.2f}/次 · 连续 {streak} 天 · 最高 {max_streak} 天",
            size=12,
            color=ft.Colors.GREY_500,
        )
    elif view_mode == "today":
        subtitle = ft.Text(
            f"连续 {streak} 天 · 最高 {max_streak} 天",
            size=12,
            color=ft.Colors.GREY_500,
        )
    else:
        subtitle = ft.Container()

    # --- Action buttons (all view) ---
    if view_mode == "all":
        actions = ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.HISTORY,
                    icon_size=18,
                    tooltip="补卡",
                    on_click=on_makeup,
                ),
                ft.IconButton(
                    icon=ft.Icons.EDIT,
                    icon_size=18,
                    tooltip="编辑",
                    on_click=on_edit,
                ),
            ],
            tight=True,
            spacing=0,
        )
    else:
        actions = ft.Container()

    # --- Main body ---
    body = ft.Column(
        [title_row, desc_widget, subtitle],
        spacing=2,
        expand=True,
    )

    # --- Click handler for history ---
    async def card_click(e):
        if on_history:
            await on_history(e)

    return ft.Card(
        content=ft.Container(
            content=ft.Row(
                [
                    priority_bar,
                    ft.Container(
                        content=body,
                        padding=ft.padding.symmetric(horizontal=10, vertical=10),
                        expand=True,
                        on_click=card_click if view_mode == "today" else card_click,
                    ),
                    ft.Container(
                        content=ft.Column(
                            [
                                checkin_btn,
                                actions,
                            ],
                            spacing=4,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.padding.only(right=10, top=10, bottom=10),
                    ),
                ],
                spacing=0,
            ),
            padding=ft.padding.zero,
        ),
        elevation=1,
        color=ft.Colors.GREY_100 if not is_enabled else None,
    )
