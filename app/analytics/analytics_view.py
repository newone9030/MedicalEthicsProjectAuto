"""
数据分析视图
"""

import flet as ft
from app.task.task_service import list_tasks
from app.analytics.analytics_service import get_task_statistics, get_question_analysis
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import io
import base64


def build_analytics_view(page: ft.Page, on_back=None) -> list:
    """数据分析页面"""

    # 任务选择器
    tasks = list_tasks(status_filter='', search='')
    task_options = [ft.DropdownOption(key=str(t['id']), text=f"{t['name']} ({t['status']})") for t in tasks]
    task_dropdown = ft.Dropdown(
        label='选择要分析的任务',
        options=task_options,
        border_color='#BBDEFB',
        focused_border_color='#1976D2',
        width=400,
    )

    # 统计摘要
    summary_row = ft.Row(spacing=16)
    chart_area = ft.Column(spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)

    def on_task_select(e):
        tid_str = task_dropdown.value
        if not tid_str:
            return
        tid = int(tid_str)
        load_analysis(tid)

    task_dropdown.on_select = on_task_select

    def load_analysis(task_id: int):
        stats = get_task_statistics(task_id)
        questions_analysis = get_question_analysis(task_id)

        # 刷新统计摘要
        summary_row.controls.clear()
        summary_row.controls.extend([
            _build_stat_card('总案例数', str(stats['total_cases']), ft.Icons.LIBRARY_BOOKS, '#1565C0'),
            _build_stat_card('参与学生', str(stats['total_students']), ft.Icons.PEOPLE, '#4CAF50'),
            _build_stat_card('总提交数', str(stats['total_submissions']), ft.Icons.CHECK_CIRCLE, '#FF9800'),
            _build_stat_card('提交率',
                           f"{stats['total_students']}/{stats['total_cases']}",
                           ft.Icons.ANALYTICS, '#9C27B0'),
        ])

        # 每案例提交统计
        case_chart = _build_case_submission_chart(stats['per_case'])
        summary_row.controls.append(case_chart)

        # 刷新图表区
        chart_area.controls.clear()

        for qa in questions_analysis:
            if qa['question_type'] in ('single_choice', 'multiple_choice') and qa['total_responses'] > 0:
                chart_img = _generate_freq_chart(qa)
                if chart_img:
                    chart_area.controls.append(
                        ft.Container(
                            content=ft.Column([
                                ft.Text(f"[{qa['case_title']}] {qa['question_text'][:50]}",
                                        size=14, weight=ft.FontWeight.W_500, color='#212121'),
                                ft.Text(f"{qa['question_type'] == 'single_choice' and '单选题' or '多选题'} | {qa['total_responses']} 人作答",
                                        size=12, color='#757575'),
                                chart_img,
                            ], spacing=6),
                            bgcolor='white', border_radius=12, padding=16,
                            shadow=ft.BoxShadow(spread_radius=0.5, blur_radius=8, color='#00000015'),
                        )
                    )
            elif qa['question_type'] == 'open' and qa['total_responses'] > 0:
                answers_text = '\n\n'.join([f'"{a}"' for a in qa['text_answers'][:10]])
                if qa.get('has_more'):
                    answers_text += f'\n\n... 共 {qa["total_responses"]} 条回复，仅展示前 10 条'

                chart_area.controls.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Text(f"[{qa['case_title']}] {qa['question_text'][:50]}",
                                    size=14, weight=ft.FontWeight.W_500, color='#212121'),
                            ft.Text(f"开放题 | {qa['total_responses']} 人作答", size=12, color='#757575'),
                            ft.Divider(height=5, color='transparent'),
                            ft.Container(
                                content=ft.Text(answers_text, size=13, color='#424242', selectable=True),
                                bgcolor='#F5F5F5', border_radius=8, padding=12,
                            ),
                        ], spacing=6),
                        bgcolor='white', border_radius=12, padding=16,
                        shadow=ft.BoxShadow(spread_radius=0.5, blur_radius=8, color='#00000015'),
                    )
                )

        [c.update() for c in [summary_row, chart_area]]

    return [
        ft.Column([
            ft.Row([
                ft.IconButton(icon=ft.Icons.ARROW_BACK, icon_color='#1565C0',
                              on_click=lambda e: on_back() if on_back else None) if on_back else ft.Container(),
                ft.Text('数据分析', size=22, weight=ft.FontWeight.BOLD, color='#1565C0'),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(height=15, color='transparent'),
            task_dropdown,
            ft.Divider(height=15, color='transparent'),
            ft.Text('统计摘要', size=16, weight=ft.FontWeight.W_500, color='#212121'),
            ft.Divider(height=8, color='transparent'),
            summary_row,
            ft.Divider(height=15, color='transparent'),
            ft.Text('题目分析', size=16, weight=ft.FontWeight.W_500, color='#212121'),
            ft.Divider(height=8, color='transparent'),
            chart_area,
        ], expand=True, spacing=0, scroll=ft.ScrollMode.AUTO),
    ]


def _build_stat_card(title: str, value: str, icon, color: str) -> ft.Container:
    """构建统计卡片"""
    return ft.Container(
        content=ft.Row([
            ft.Icon(icon, color=color, size=28),
            ft.Column([
                ft.Text(value, size=22, weight=ft.FontWeight.BOLD, color='#212121'),
                ft.Text(title, size=11, color='#757575'),
            ], spacing=2),
        ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        bgcolor='white', border_radius=12, padding=16,
        shadow=ft.BoxShadow(spread_radius=0.5, blur_radius=8, color='#00000015'),
        width=160,
    )


def _build_case_submission_chart(per_case: list) -> ft.Container:
    """构建每案例提交迷你图"""
    fig, ax = plt.subplots(figsize=(4, 1.8))
    titles = [c['title'][:8] for c in per_case]
    counts = [c['submitted'] for c in per_case]

    colors = ['#1565C0', '#1976D2', '#2196F3', '#42A5F5', '#64B5F6', '#90CAF9'][:len(counts)]

    bars = ax.barh(range(len(counts)), counts, color=colors, height=0.5)
    for bar, val in zip(bars, counts):
        ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height()/2,
                str(val), va='center', fontsize=8)

    ax.set_yticks(range(len(counts)))
    ax.set_yticklabels(titles, fontsize=7)
    ax.invert_yaxis()
    ax.set_xlim(0, max(counts) * 1.2 if counts and max(counts) > 0 else 1)
    ax.tick_params(axis='x', labelsize=6)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.xaxis.set_visible(False)
    plt.tight_layout(pad=0.5)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=100, bbox_inches='tight', transparent=True)
    plt.close(fig)
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode('utf-8')

    return ft.Container(
        content=ft.Column([
            ft.Text('各案例提交数', size=11, color='#757575'),
            ft.Image(src=f"data:image/png;base64,{img_b64}", width=300, fit="contain"),
        ], spacing=4),
        bgcolor='white', border_radius=12, padding=ft.Padding(12, 8, 12, 8),
        shadow=ft.BoxShadow(spread_radius=0.5, blur_radius=8, color='#00000015'),
        width=320,
    )


def _generate_freq_chart(qa: dict) -> ft.Image:
    """生成频次统计图表"""
    freq = qa['frequency']
    raw_options = qa['options']
    # 兼容对象选项 / 旧字符串选项
    options = [o.get('label', '') if isinstance(o, dict) else str(o) for o in raw_options]
    is_multi = qa['question_type'] == 'multiple_choice'

    fig, ax = plt.subplots(figsize=(5, max(2.5, len(options) * 0.5)))

    counts = [freq.get(opt, 0) for opt in options]
    max_count = max(counts) if counts else 1

    colors = ['#1976D2' if not is_multi else '#FF9800' for _ in options]

    bars = ax.barh(range(len(options)), counts, color=colors, height=0.6, edgecolor='white', linewidth=0.5)

    total = qa['total_responses']
    for i, (bar, cnt) in enumerate(zip(bars, counts)):
        pct = f' ({cnt/total*100:.1f}%)' if total > 0 else ''
        ax.text(bar.get_width() + max_count * 0.02, bar.get_y() + bar.get_height()/2,
                f'{cnt}{pct}', va='center', fontsize=9, color='#424242')

    ax.set_yticks(range(len(options)))
    ax.set_yticklabels([o[:20] for o in options], fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(0, max_count * 1.3 if max_count > 0 else 1)
    ax.xaxis.set_visible(False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    plt.tight_layout(pad=0.5)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=120, bbox_inches='tight', transparent=True)
    plt.close(fig)
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode('utf-8')

    return ft.Image(src=f"data:image/png;base64,{img_b64}", fit="contain")
