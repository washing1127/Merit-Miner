"""统计与分析页。包含"奖金银行"和"任务与生活"两个 Tab。

注意：Flet 0.81 移除了 BarChart/LineChart/PieChart，
因此使用 ProgressBar、Container 和文本实现可视化统计。
"""

import flet as ft
from datetime import datetime
from loguru import logger

from models.task import TaskType
from repositories.category_repo import get_category_by_id
from repositories.task_repo import get_all_tasks, get_checkin_records
from services.logic_service import get_bonus_balance, get_monthly_stats
from ui.components.stat_card import BalanceCard, StatCard


class StatsPage:
    """统计页控制器。"""

    def __init__(self, page: ft.Page):
        self.page = page

    def _build_bar(
        self, label: str, value: float, max_value: float, color: str
    ) -> ft.Container:
        """构建一个横向进度条形图。"""
        ratio = (value / max_value) if max_value > 0 else 0
        ratio = min(ratio, 1.0)
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(label, size=12, expand=True),
                            ft.Text(f"¥{value:.2f}", size=12,
                                    weight=ft.FontWeight.BOLD),
                        ],
                    ),
                    ft.ProgressBar(value=ratio, color=color, bgcolor=ft.Colors.GREY_200),
                ],
                spacing=2,
            ),
            padding=ft.padding.symmetric(vertical=4),
        )

    def _build_category_bars(
        self, breakdown: dict[int, float], cat_names: dict[int, str]
    ) -> list[ft.Control]:
        """构建分类占比的横向条形图列表。"""
        if not breakdown:
            return [
                ft.Container(
                    content=ft.Text("暂无数据", color=ft.Colors.GREY_400,
                                    text_align=ft.TextAlign.CENTER),
                    alignment=ft.Alignment.CENTER,
                    padding=20,
                )
            ]

        colors = [
            ft.Colors.BLUE, ft.Colors.RED, ft.Colors.GREEN,
            ft.Colors.ORANGE, ft.Colors.PURPLE, ft.Colors.TEAL,
            ft.Colors.AMBER, ft.Colors.PINK, ft.Colors.CYAN,
        ]
        total = sum(breakdown.values())
        max_val = max(breakdown.values()) if breakdown else 1
        bars = []
        for i, (cat_id, amount) in enumerate(
            sorted(breakdown.items(), key=lambda x: x[1], reverse=True)
        ):
            name = cat_names.get(cat_id, "未知")
            pct = (amount / total * 100) if total > 0 else 0
            color = colors[i % len(colors)]
            bars.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Container(
                                        width=12, height=12,
                                        bgcolor=color,
                                        border_radius=2,
                                    ),
                                    ft.Text(name, size=12, expand=True),
                                    ft.Text(f"¥{amount:.2f} ({pct:.0f}%)",
                                            size=12, weight=ft.FontWeight.W_500),
                                ],
                                spacing=8,
                            ),
                            ft.ProgressBar(
                                value=amount / max_val if max_val > 0 else 0,
                                color=color,
                                bgcolor=ft.Colors.GREY_200,
                            ),
                        ],
                        spacing=2,
                    ),
                    padding=ft.padding.symmetric(vertical=2),
                )
            )
        return bars

    async def _build_bonus_bank_tab(self) -> ft.Control:
        """构建"奖金银行"Tab 内容。"""
        now = datetime.now()
        balance = await get_bonus_balance()
        stats = await get_monthly_stats(now.year, now.month)

        # 余额卡片
        balance_card = BalanceCard(balance)

        # 本月收支统计卡片
        income_card = StatCard(
            title="本月奖金收入",
            value=f"¥{stats['bonus_income']:.2f}",
            icon=ft.Icons.TRENDING_UP,
            color=ft.Colors.GREEN,
        )
        expense_card = StatCard(
            title="本月奖金支出",
            value=f"¥{stats['bonus_expense']:.2f}",
            icon=ft.Icons.TRENDING_DOWN,
            color=ft.Colors.RED,
        )
        net_income = stats["bonus_income"] - stats["bonus_expense"]
        net_card = StatCard(
            title="本月净收益",
            value=f"¥{net_income:.2f}",
            icon=ft.Icons.ACCOUNT_BALANCE,
            color=ft.Colors.GREEN if net_income >= 0 else ft.Colors.RED,
        )

        # 本月收支对比条形图
        max_val = max(stats["bonus_income"], stats["bonus_expense"], 1)
        income_bar = self._build_bar(
            "奖金收入", stats["bonus_income"], max_val, ft.Colors.GREEN
        )
        expense_bar = self._build_bar(
            "奖金支出", stats["bonus_expense"], max_val, ft.Colors.RED
        )

        bar_chart_section = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text("本月收支对比", size=14,
                                weight=ft.FontWeight.W_600),
                        income_bar,
                        expense_bar,
                    ],
                    spacing=8,
                ),
                padding=ft.padding.all(16),
            ),
        )

        # 奖金消耗分类占比
        category_breakdown = stats.get("category_breakdown", {})
        cat_names: dict[int, str] = {}
        for cat_id in category_breakdown:
            cat = await get_category_by_id(cat_id)
            cat_names[cat_id] = cat.name if cat else "未知"

        category_bars = self._build_category_bars(category_breakdown, cat_names)
        pie_section = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text("奖金消耗分类占比", size=14,
                                weight=ft.FontWeight.W_600),
                        *category_bars,
                    ],
                    spacing=4,
                ),
                padding=ft.padding.all(16),
            ),
        )

        return ft.Container(
            content=ft.Column(
                [
                    balance_card,
                    ft.Row([income_card, expense_card], spacing=8),
                    net_card,
                    bar_chart_section,
                    pie_section,
                ],
                spacing=12,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            padding=ft.padding.all(16),
            expand=True,
        )

    async def _build_tasks_life_tab(self) -> ft.Control:
        """构建"任务与生活"Tab 内容。"""
        now = datetime.now()
        stats = await get_monthly_stats(now.year, now.month)
        tasks = await get_all_tasks(enabled_only=False)

        # 活跃任务概览
        active_count = len([t for t in tasks if t.is_enabled])
        reward_count = len(
            [t for t in tasks if t.task_type == TaskType.REWARD and t.is_enabled]
        )
        task_overview = ft.Row(
            [
                StatCard(
                    title="活跃任务",
                    value=str(active_count),
                    icon=ft.Icons.CHECKLIST,
                    color=ft.Colors.BLUE,
                ),
                StatCard(
                    title="奖励任务",
                    value=str(reward_count),
                    icon=ft.Icons.STAR,
                    color=ft.Colors.AMBER,
                ),
            ],
            spacing=8,
        )

        # 总支出
        total_expense_card = StatCard(
            title="本月总支出",
            value=f"¥{stats['total_expense']:.2f}",
            icon=ft.Icons.PAYMENTS,
            color=ft.Colors.DEEP_PURPLE,
            subtitle="包含所有类型支出",
        )

        # 任务完成率趋势（用每日色块代替折线图）
        daily_rates = stats.get("daily_rates", [])
        avg_rate = (
            sum(daily_rates) / len(daily_rates) if daily_rates else 0
        )

        rate_items = []
        for i, rate in enumerate(daily_rates):
            day_num = i + 1
            color = (
                ft.Colors.GREEN if rate >= 0.8
                else ft.Colors.ORANGE if rate >= 0.5
                else ft.Colors.RED if rate > 0
                else ft.Colors.GREY_300
            )
            rate_items.append(
                ft.Container(
                    content=ft.Text(str(day_num), size=9,
                                    text_align=ft.TextAlign.CENTER,
                                    color=ft.Colors.WHITE if rate > 0
                                    else ft.Colors.GREY_500),
                    width=28,
                    height=28,
                    bgcolor=color,
                    border_radius=4,
                    alignment=ft.Alignment.CENTER,
                    tooltip=f"第{day_num}天: {rate:.0%}",
                )
            )

        completion_section = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text("任务完成率趋势", size=14,
                                        weight=ft.FontWeight.W_600),
                                ft.Text(f"均值 {avg_rate:.0%}", size=12,
                                        color=ft.Colors.GREY_500),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Row(
                            [
                                ft.Container(width=10, height=10,
                                             bgcolor=ft.Colors.GREEN,
                                             border_radius=2),
                                ft.Text(">=80%", size=10),
                                ft.Container(width=10, height=10,
                                             bgcolor=ft.Colors.ORANGE,
                                             border_radius=2),
                                ft.Text(">=50%", size=10),
                                ft.Container(width=10, height=10,
                                             bgcolor=ft.Colors.RED,
                                             border_radius=2),
                                ft.Text("<50%", size=10),
                            ],
                            spacing=6,
                        ),
                        ft.Row(
                            rate_items,
                            wrap=True,
                            spacing=4,
                            run_spacing=4,
                        ) if rate_items else ft.Text(
                            "暂无打卡数据",
                            color=ft.Colors.GREY_400,
                        ),
                    ],
                    spacing=8,
                ),
                padding=ft.padding.all(16),
            ),
        )

        # 连续打卡天数排行
        streak_tasks = [t for t in tasks if t.current_streak > 0]
        streak_tasks.sort(key=lambda t: t.current_streak, reverse=True)
        streak_tasks = streak_tasks[:10]

        max_streak = max(
            (t.current_streak for t in streak_tasks), default=1
        )

        streak_items = []
        for task in streak_tasks:
            ratio = task.current_streak / max_streak if max_streak > 0 else 0
            streak_items.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.LOCAL_FIRE_DEPARTMENT,
                                            size=14, color=ft.Colors.ORANGE),
                                    ft.Text(task.title, size=12, expand=True),
                                    ft.Text(f"{task.current_streak} 天",
                                            size=12,
                                            weight=ft.FontWeight.BOLD,
                                            color=ft.Colors.ORANGE),
                                ],
                                spacing=6,
                            ),
                            ft.ProgressBar(
                                value=ratio,
                                color=ft.Colors.ORANGE,
                                bgcolor=ft.Colors.GREY_200,
                            ),
                        ],
                        spacing=2,
                    ),
                    padding=ft.padding.symmetric(vertical=2),
                )
            )

        streak_section = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text("连续打卡天数排行", size=14,
                                weight=ft.FontWeight.W_600),
                        *(streak_items if streak_items else [
                            ft.Container(
                                content=ft.Text("暂无打卡记录",
                                                color=ft.Colors.GREY_400),
                                alignment=ft.Alignment.CENTER,
                                padding=20,
                            )
                        ]),
                    ],
                    spacing=4,
                ),
                padding=ft.padding.all(16),
            ),
        )

        return ft.Container(
            content=ft.Column(
                [
                    task_overview,
                    total_expense_card,
                    completion_section,
                    streak_section,
                ],
                spacing=12,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            padding=ft.padding.all(16),
            expand=True,
        )

    async def build(self) -> ft.Control:
        """构建统计页视图。使用 TabBar + TabBarView 实现双 Tab 布局。"""
        bonus_tab_content = await self._build_bonus_bank_tab()
        life_tab_content = await self._build_tasks_life_tab()

        return ft.Tabs(
            content=ft.Column(
                [
                    ft.TabBar(
                        tabs=[
                            ft.Tab(label="奖金银行", icon=ft.Icons.ACCOUNT_BALANCE_WALLET),
                            ft.Tab(label="任务与生活", icon=ft.Icons.INSIGHTS),
                        ],
                    ),
                    ft.Container(
                        content=ft.TabBarView(
                            controls=[bonus_tab_content, life_tab_content],
                        ),
                        expand=True,
                    ),
                ],
                expand=True,
            ),
            length=2,
            selected_index=0,
            animation_duration=300,
            expand=True,
        )
