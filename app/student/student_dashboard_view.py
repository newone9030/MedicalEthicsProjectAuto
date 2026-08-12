"""
学生仪表盘视图
"""

from datetime import datetime
import threading
import flet as ft
from app.task.task_service import get_active_task_for_student, get_background_task
from app.response.response_service import get_submission_status, delete_student_responses, delete_background_survey_responses, is_background_completed
from app.student.feedback_service import has_feedback, get_student_feedback, delete_student_feedback


def build_student_dashboard(page: ft.Page, on_enter_task) -> list:
    """学生仪表盘 - 展示进行中任务"""
    user = page.session.store.get('user')
    student_id = user['id']

    task_container = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO)

    def refresh_task():
        try:
            task = get_active_task_for_student(student_id)
        except Exception as ex:
            task_container.controls.clear()
            task_container.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.ERROR_OUTLINE, size=64, color='#FF5252'),
                        ft.Text('加载失败', size=20, weight=ft.FontWeight.W_500, color='#757575'),
                        ft.Text(f'错误信息: {ex}', size=15, color='#BDBDBD'),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                    padding=60,
                    alignment=ft.Alignment.CENTER,
                    expand=True,
                )
            )
            if task_container.page:
                task_container.update()
            return

        task_container.controls.clear()

        # ---- 背景资料卡片（无论是否完成都显示入口） ----
        bg_task = get_background_task()
        if bg_task:
            task_container.controls.append(
                _build_background_survey_card(bg_task, student_id, page, refresh_task)
            )
            task_container.controls.append(ft.Divider(height=15, color='transparent'))

        if not task:
            _build_empty_state(task_container)
        else:
            statuses = get_submission_status(task['id'], student_id)
            all_submitted = statuses and all(s == 'submitted' for s in statuses.values())
            task_container.controls.append(
                _build_task_card(task, statuses, page, on_enter_task, all_submitted, student_id, refresh_task)
            )

            # 历史任务（已关闭的）
            _add_history_tasks(task_container, student_id, page, on_enter_task)

        # 测试用户反馈入口（无论活跃任务是否存在，检查条件）
        _maybe_add_feedback_entry(task_container, page, student_id, user, task, bg_task,
                                  refresh_cb=refresh_task)

        if task_container.page:
            task_container.update()

    # 控件挂载后延迟加载数据
    threading.Timer(0.3, refresh_task).start()

    return [
        ft.Column([
            ft.Row([
                ft.Text('我的任务', size=24, weight=ft.FontWeight.BOLD, color='#1565C0'),
                ft.Container(
                    content=ft.Text(
                        f'{user.get("real_name") or user["username"]} | {user.get("class_name", "")}',
                        size=15, color='#757575'
                    ),
                ),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(height=15, color='transparent'),
            task_container,
        ], expand=True, spacing=0),
    ]


def _build_empty_state(container: ft.Column):
    container.controls.append(
        ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.INBOX, size=64, color='#BDBDBD'),
                ft.Text('暂无可用任务', size=20, weight=ft.FontWeight.W_500, color='#757575'),
                ft.Text('目前暂时没有开放中的任务，请联系系统管理员', size=15, color='#BDBDBD'),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
            padding=60,
            alignment=ft.Alignment.CENTER,
            expand=True,
        )
    )


def _close_overlay_dlg(dialog):
    """关闭并移除 overlay 中的对话框"""
    if dialog.page:
        dialog.open = False
        ##dialog.page.overlay.remove(dialog)
        
        dialog.page.update()


def _build_task_card(task: dict, statuses: dict, page: ft.Page, on_enter_task,
                     all_submitted: bool = False, student_id: int = None,
                     on_refresh=None) -> ft.Container:
    """构建进行中任务卡片"""
    now = datetime.now()
    end_time = task.get('end_time')
    if isinstance(end_time, str):
        try:
            end_time = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            end_time = None
    remaining = end_time - now if isinstance(end_time, datetime) else None
    is_closed = remaining is not None and remaining.total_seconds() < 0

    if is_closed:
        remaining_str = '已关闭'
        remaining_color = '#FF5252'
    elif remaining:
        days = remaining.days
        hours = remaining.seconds // 3600
        mins = (remaining.seconds % 3600) // 60
        if days > 0:
            remaining_str = f'{days}天{hours}小时'
        elif hours > 0:
            remaining_str = f'{hours}小时{mins}分钟'
        else:
            remaining_str = f'{mins}分钟'
        remaining_color = '#4CAF50' if days > 0 else '#FF9800' if hours > 1 else '#FF5252'
    else:
        remaining_str = '计算中...'
        remaining_color = '#757575'

    # 案例进度
    total = len(task['cases'])
    submitted_count = sum(1 for s in statuses.values() if s == 'submitted')
    draft_count = sum(1 for s in statuses.values() if s == 'draft')

    progress = submitted_count / total if total > 0 else 0

    case_chips = []
    for case in task['cases']:
        st = case['response_status']
        if st == 'submitted':
            chip_color = '#C8E6C9'
            icon_color = '#4CAF50'
            label = '已提交'
        elif st == 'draft':
            chip_color = '#FFF3E0'
            icon_color = '#FF9800'
            label = '草稿'
        else:
            chip_color = '#F5F5F5'
            icon_color = '#BDBDBD'
            label = '未开始'

        case_chips.append(
            ft.Container(
                content=ft.Row([
                    ft.Container(width=6, height=6, border_radius=3, bgcolor=icon_color),
                    ft.Text(case['title'][:10], size=13, color='#212121'),
                ], spacing=4),
                bgcolor=chip_color,
                border_radius=8,
                padding=ft.Padding(8, 4, 8, 4),
            )
        )

    # ---- 底部按钮区（根据是否全部已提交决定） ----
    if all_submitted:
        def show_restart_confirm(e):
            page.overlay.append(confirm_dlg)
            confirm_dlg.open = True
            page.update()

        def do_restart(e2):
            """确认重新作答"""
            _close_overlay_dlg(confirm_dlg)
            result = delete_student_responses(task['id'], student_id)
            if result['success']:
                snack = ft.SnackBar(ft.Text(result['message']), bgcolor='#4CAF50')
                page.overlay.append(snack)
                snack.open = True
                page.update()
                if on_refresh:
                    on_refresh()
            else:
                snack = ft.SnackBar(ft.Text(result['message']), bgcolor='#FF5252')
                page.overlay.append(snack)
                snack.open = True
                page.update()

        confirm_dlg = ft.AlertDialog(
            title=ft.Text('确认重新作答'),
            content=ft.Text('删除作答后，之前填写的所有内容将丢失。\n\n确定要重新作答吗？'),
            actions=[
                ft.TextButton(content='取消', on_click=lambda e: _close_overlay_dlg(confirm_dlg)),
                ft.ElevatedButton(content='确认删除', on_click=do_restart,
                                  style=ft.ButtonStyle(bgcolor='#FF5252', color='white')),
            ],
            modal=True,
        )

        action_buttons = ft.Row([
            ft.ElevatedButton(
                content='查看作答',
                icon=ft.Icons.VISIBILITY,
                on_click=lambda e: on_enter_task(task['id'], page, readonly=True),
                style=ft.ButtonStyle(
                    bgcolor='#1565C0', color='white',
                    shape=ft.RoundedRectangleBorder(radius=8),
                ),
            ),
            ft.OutlinedButton(
                content='重新作答',
                icon=ft.Icons.REFRESH,
                on_click=show_restart_confirm if not is_closed else None,
                disabled=is_closed,
                style=ft.ButtonStyle(
                    color='#FF5252' if not is_closed else '#BDBDBD',
                    shape=ft.RoundedRectangleBorder(radius=8),
                    side=ft.BorderSide(color='#FF5252' if not is_closed else '#BDBDBD', width=1),
                ),
            ),
        ], spacing=10)
    else:
        action_buttons = ft.ElevatedButton(
            content='进入作答' if not is_closed else '已关闭',
            icon=ft.Icons.PLAY_ARROW if not is_closed else ft.Icons.LOCK,
            on_click=lambda e: on_enter_task(task['id'], page) if not is_closed else None,
            disabled=is_closed,
            style=ft.ButtonStyle(
                bgcolor='#1976D2' if not is_closed else '#BDBDBD',
                color='white',
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.Padding(30, 12, 30, 12),
            ),
        )

    # ---- 状态徽章 ----
    if all_submitted:
        status_badge = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.CHECK_CIRCLE, color='white', size=16),
                ft.Text('已完成', size=14, color='white', weight=ft.FontWeight.W_600),
            ], spacing=4),
            bgcolor='#4CAF50',
            border_radius=12,
            padding=ft.Padding(10, 4, 10, 4),
        )
        progress_section = ft.Row([
            status_badge,
            ft.Container(expand=True),
            ft.Text(f'{total} 个案例已全部提交', size=14, color='#757575'),
        ])
    else:
        progress_section = ft.Column([
            ft.Row([
                ft.Text(f'进度: {submitted_count}/{total} 已提交', size=14, color='#616161'),
                ft.Container(expand=True),
                ft.Text(f'{draft_count} 草稿' if draft_count > 0 else '', size=14, color='#FF9800'),
            ]),
            ft.ProgressBar(value=progress, bgcolor='#E0E0E0', color='#4CAF50', height=6),
        ], spacing=6)

    return ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Column([
                    ft.Text(task['name'], size=20, weight=ft.FontWeight.BOLD, color='#212121',
                            overflow=ft.TextOverflow.VISIBLE),
                    ft.Text(task.get('description', '')[:80], size=14, color='#757575',
                            overflow=ft.TextOverflow.VISIBLE),
                ], spacing=2, expand=True),
                ft.Column([
                    ft.Text('截止倒计时', size=12, color='#9E9E9E'),
                    ft.Text(remaining_str, size=20, weight=ft.FontWeight.BOLD, color=remaining_color),
                ], horizontal_alignment=ft.CrossAxisAlignment.END),
            ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.START),
            ft.Divider(height=10, color='transparent'),
            progress_section,
            ft.Divider(height=8, color='transparent'),
            ft.Row(case_chips, spacing=6, wrap=True),
            ft.Divider(height=12, color='transparent'),
            action_buttons,
        ], spacing=0),
        bgcolor='white',
        border_radius=16,
        padding=20,
        shadow=ft.BoxShadow(spread_radius=1, blur_radius=15, color='#00000015'),
        border=ft.Border.all(width=1, color='#E3F2FD'),
    )


def _build_background_survey_card(bg_task: dict, student_id: int, page: ft.Page,
                                  on_refresh: callable) -> ft.Container:
    """构建背景资料卡片（支持未完成/已完成两种状态）"""
    completed = is_background_completed(bg_task['id'], student_id)

    def go_fill(e):
        # 未完成时直接进入填写
        page.session.store.set('background_completed', False)
        page.go('/student/background')

    def show_restart_confirm(e):
        page.overlay.append(confirm_dlg)
        confirm_dlg.open = True
        page.update()

    def do_restart(e2):
        _close_overlay_dlg(confirm_dlg)
        result = delete_background_survey_responses(bg_task['id'], student_id)
        if result['success']:
            # 清除 session 中的背景资料完成标记
            page.session.store.set('background_completed', False)
            page.go('/student/background')
        else:
            snack = ft.SnackBar(ft.Text(result['message']), bgcolor='#FF5252')
            page.overlay.append(snack)
            snack.open = True
            page.update()

    confirm_dlg = ft.AlertDialog(
        title=ft.Text('确认重新填写背景资料'),
        content=ft.Text('删除背景资料作答后，之前填写的所有内容将丢失。\n\n确定要重新填写吗？'),
        actions=[
            ft.TextButton(content='取消', on_click=lambda e: _close_overlay_dlg(confirm_dlg)),
            ft.ElevatedButton(content='确认删除', on_click=do_restart,
                              style=ft.ButtonStyle(bgcolor='#FF5252', color='white')),
        ],
        modal=True,
    )

    status_badge = None
    if completed:
        status_badge = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.CHECK_CIRCLE, color='white', size=16),
                ft.Text('已完成', size=14, color='white', weight=ft.FontWeight.W_600),
            ], spacing=4),
            bgcolor='#4CAF50',
            border_radius=12,
            padding=ft.Padding(10, 4, 10, 4),
        )
    else:
        status_badge = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.ERROR_OUTLINE, color='white', size=16),
                ft.Text('未填写', size=14, color='white', weight=ft.FontWeight.W_600),
            ], spacing=4),
            bgcolor='#FF9800',
            border_radius=12,
            padding=ft.Padding(10, 4, 10, 4),
        )

    action_btn = None
    if completed:
        action_btn = ft.OutlinedButton(
            content='重新填写',
            icon=ft.Icons.REFRESH,
            on_click=show_restart_confirm,
            style=ft.ButtonStyle(
                color='#7B1FA2',
                shape=ft.RoundedRectangleBorder(radius=8),
                side=ft.BorderSide(color='#7B1FA2', width=1),
            ),
        )
    else:
        action_btn = ft.ElevatedButton(
            content='去填写',
            icon=ft.Icons.EDIT,
            on_click=go_fill,
            style=ft.ButtonStyle(
                bgcolor='#7B1FA2', color='white',
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
        )

    return ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.ASSIGNMENT_IND, color='white', size=16),
                        ft.Text('背景资料调查', size=16, color='white', weight=ft.FontWeight.W_600),
                    ], spacing=6),
                    bgcolor='#7B1FA2',
                    border_radius=12,
                    padding=ft.Padding(10, 4, 10, 4),
                ),
                ft.Container(expand=True),
                status_badge,
            ]),
            ft.Divider(height=12, color='transparent'),
            ft.Text(bg_task.get('description', '')[:80] or bg_task.get('name', '背景资料任务'),
                    size=14, color='#757575'),
            ft.Divider(height=12, color='transparent'),
            ft.Row([action_btn], alignment=ft.MainAxisAlignment.END),
        ], spacing=0),
        bgcolor='white',
        border_radius=16,
        padding=20,
        shadow=ft.BoxShadow(spread_radius=1, blur_radius=15, color='#00000015'),
        border=ft.Border.all(width=1, color='#F3E5F5'),
    )


def _add_history_tasks(container: ft.Column, student_id: int, page: ft.Page, on_enter_task):
    """添加历史任务（可折叠）"""
    from app.db import get_connection
    from datetime import datetime

    with get_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now()
        cursor.execute("""
            SELECT DISTINCT t.id, t.name, t.start_time, t.end_time
            FROM tasks t
            JOIN responses r ON t.id = r.task_id AND r.student_id = :sid
            WHERE t.status = 'closed' OR t.end_time < :now
            ORDER BY t.end_time DESC
        """, {'sid': student_id, 'now': now})
        rows = cursor.fetchall()

    if not rows:
        return

    container.controls.append(
        ft.Divider(height=15, color='transparent'),
    )

    expand = ft.Ref[bool]()
    expand.current = False

    history_list = ft.Column(spacing=6)

    def toggle_history(e):
        expand.current = not expand.current
        history_list.visible = expand.current
        toggle_btn.icon = ft.Icons.EXPAND_LESS if expand.current else ft.Icons.EXPAND_MORE
        toggle_btn.update()
        history_list.update()

    toggle_btn = ft.TextButton(
        content='历史任务 ▼',
        icon=ft.Icons.EXPAND_MORE,
        on_click=toggle_history,
        style=ft.ButtonStyle(color='#757575'),
    )

    for row in rows:
        t = {'id': row[0], 'name': row[1], 'start_time': row[2], 'end_time': row[3]}
        end_str = t['end_time'].strftime('%Y/%m/%d') if hasattr(t['end_time'], 'strftime') else str(t['end_time'])[:10]

        statuses = get_submission_status(t['id'], student_id)
        submitted = sum(1 for s in statuses.values() if s == 'submitted')

        history_list.controls.append(
            ft.Container(
                content=ft.Row([
                    ft.Column([
                        ft.Text(t['name'], size=15, weight=ft.FontWeight.W_500, color='#757575'),
                        ft.Text(f'截止: {end_str} | 已提交 {submitted}/{len(statuses)} 个案例', size=13, color='#BDBDBD'),
                    ], spacing=2, expand=True),
                    ft.TextButton(content='查看', on_click=lambda e, tid=t['id']: on_enter_task(tid, page, readonly=True),
                                  style=ft.ButtonStyle(color='#1565C0')),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor='#FAFAFA', border_radius=8, padding=ft.Padding(12, 8, 12, 8),
            )
        )

    container.controls.append(toggle_btn)
    container.controls.append(history_list)
    history_list.visible = False


def _maybe_add_feedback_entry(container: ft.Column, page: ft.Page, student_id: int,
                               user: dict, task: dict, bg_task: dict,
                               refresh_cb=None):
    """
    测试用户反馈区：
    - 已提交反馈 → 显示"查看反馈/删除反馈"卡片
    - 未提交反馈且（背景已完成 + 所有任务已提交）→ 显示"进入反馈"卡片
    """
    if user.get('user_type') != 'test':
        return

    # 已提交反馈：提供查看与删除入口
    if has_feedback(student_id):
        container.controls.append(ft.Divider(height=15, color='transparent'))
        container.controls.append(_build_feedback_view_card(page, student_id, refresh_cb))
        return

    # 检查背景是否完成
    bg_completed = False
    if bg_task:
        bg_completed = is_background_completed(bg_task['id'], student_id)
    else:
        bg_completed = True  # 无背景任务视为已完成

    if not bg_completed:
        return

    # 检查活跃任务
    if task:
        statuses = get_submission_status(task['id'], student_id)
        all_submitted = statuses and all(s == 'submitted' for s in statuses.values())
        if not all_submitted:
            return
    # 如果没有活跃任务（可能任务已关闭），也显示入口

    container.controls.append(ft.Divider(height=15, color='transparent'))
    container.controls.append(_build_feedback_entry_card(page))


def _build_feedback_entry_card(page: ft.Page) -> ft.Container:
    """测试用户反馈入口卡片"""

    def on_enter_feedback(e):
        page.go('/student/feedback')

    return ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.FEEDBACK, color='white', size=18),
                        ft.Text('预测试最终反馈', size=18, color='white', weight=ft.FontWeight.W_600),
                    ], spacing=8),
                    bgcolor='#FF9800',
                    border_radius=12,
                    padding=ft.Padding(14, 6, 14, 6),
                ),
                ft.Container(expand=True),
            ]),
            ft.Divider(height=12, color='transparent'),
            ft.Text(
                '请根据您完成所有情境任务的实际体验，对系统的各个方面进行评价反馈。',
                size=14, color='#616161',
            ),
            ft.Divider(height=12, color='transparent'),
            ft.Row([
                ft.Container(expand=True),
                ft.ElevatedButton(
                    content='进入反馈',
                    icon=ft.Icons.FEEDBACK,
                    on_click=on_enter_feedback,
                    style=ft.ButtonStyle(
                        bgcolor='#FF9800', color='white',
                        shape=ft.RoundedRectangleBorder(radius=8),
                    ),
                ),
            ]),
        ], spacing=0),
        bgcolor='#FFF3E0',
        border_radius=16,
        padding=ft.Padding(20, 16, 20, 16),
        shadow=ft.BoxShadow(spread_radius=1, blur_radius=15, color='#00000015'),
        border=ft.Border.all(width=1, color='#FFE0B2'),
    )


def _build_feedback_view_card(page: ft.Page, student_id: int,
                              refresh_cb=None) -> ft.Container:
    """已提交反馈后的"查看反馈 / 删除反馈"卡片"""

    def on_view_feedback(e):
        dlg = _build_feedback_view_dialog(page, student_id)
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    def on_delete_feedback(e):
        def do_delete(ev):
            dlg.open = False
            page.update()
            try:
                delete_student_feedback(student_id)
                snack = ft.SnackBar(ft.Text('反馈已删除，可重新填写', color='white'),
                                    bgcolor='#43A047')
            except Exception as ex:
                snack = ft.SnackBar(ft.Text(f'删除失败: {ex}', color='white'),
                                    bgcolor='#E53935')
            page.overlay.append(snack)
            snack.open = True
            page.update()
            if refresh_cb:
                refresh_cb()

        def cancel_delete(ev):
            dlg.open = False
            page.update()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text('删除反馈'),
            content=ft.Text('确定要删除已提交的反馈吗？删除后可以重新填写反馈内容。'),
            actions=[
                ft.TextButton(content='取消', on_click=cancel_delete),
                ft.ElevatedButton(
                    content='确认删除',
                    style=ft.ButtonStyle(
                        bgcolor='#E53935', color='white',
                        shape=ft.RoundedRectangleBorder(radius=8),
                    ),
                    on_click=do_delete,
                ),
            ],
        )
        page.overlay.append(dlg)
        dlg.open = True
        page.update()

    return ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.FEEDBACK, color='white', size=18),
                        ft.Text('预测试最终反馈', size=18, color='white', weight=ft.FontWeight.W_600),
                    ], spacing=8),
                    bgcolor='#1565C0',
                    border_radius=12,
                    padding=ft.Padding(14, 6, 14, 6),
                ),
                ft.Container(expand=True),
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.CHECK_CIRCLE, color='white', size=16),
                        ft.Text('已提交', size=14, color='white', weight=ft.FontWeight.W_600),
                    ], spacing=4),
                    bgcolor='#4CAF50',
                    border_radius=12,
                    padding=ft.Padding(10, 4, 10, 4),
                ),
            ]),
            ft.Divider(height=12, color='transparent'),
            ft.Text(
                '您已完成预测试反馈，可点击下方按钮查看已提交的反馈内容。',
                size=14, color='#616161',
            ),
            ft.Divider(height=12, color='transparent'),
            ft.Row([
                ft.Container(expand=True),
                ft.TextButton(
                    content='删除反馈',
                    icon=ft.Icons.DELETE_OUTLINE,
                    on_click=on_delete_feedback,
                    style=ft.ButtonStyle(
                        color='#D32F2F',
                        shape=ft.RoundedRectangleBorder(radius=8),
                    ),
                ),
                ft.ElevatedButton(
                    content='查看反馈',
                    icon=ft.Icons.VISIBILITY,
                    on_click=on_view_feedback,
                    style=ft.ButtonStyle(
                        bgcolor='#1565C0', color='white',
                        shape=ft.RoundedRectangleBorder(radius=8),
                    ),
                ),
            ]),
        ], spacing=0),
        bgcolor='#E3F2FD',
        border_radius=16,
        padding=ft.Padding(20, 16, 20, 16),
        shadow=ft.BoxShadow(spread_radius=1, blur_radius=15, color='#00000015'),
        border=ft.Border.all(width=1, color='#BBDEFB'),
    )


def _build_feedback_view_dialog(page: ft.Page, student_id: int) -> ft.AlertDialog:
    """查看反馈内容对话框"""
    items = get_student_feedback(student_id)

    def close_dlg(e):
        dlg.open = False
        page.update()

    if not items:
        body = ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.INFO_OUTLINE, size=48, color='#BDBDBD'),
                ft.Text('暂无反馈内容', size=16, color='#757575'),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
            padding=30,
            alignment=ft.Alignment.CENTER,
            width=540,
        )
    else:
        content_col = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
        last_group = None
        for item in items:
            if item['group_title'] != last_group:
                last_group = item['group_title']
                content_col.controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.SUBJECT, color='#1565C0', size=18),
                            ft.Text(item['group_title'], size=16,
                                    weight=ft.FontWeight.BOLD, color='#1565C0'),
                        ], spacing=6),
                        bgcolor='#E3F2FD',
                        border_radius=8,
                        padding=ft.Padding(12, 8, 12, 8),
                    )
                )
            answer_text = item['answer_text'] or '（未作答）'
            q_col = ft.Column(spacing=4)
            q_col.controls.append(
                ft.Text(item['question_text'], size=14, weight=ft.FontWeight.W_500, color='#212121')
            )
            q_col.controls.append(
                ft.Container(
                    content=ft.Text(answer_text, size=14, color='#1565C0'),
                    padding=ft.Padding(12, 8, 12, 8),
                    bgcolor='#FAFAFA',
                    border_radius=6,
                    width=500,
                )
            )
            content_col.controls.append(q_col)
        body = ft.Container(content=content_col, width=540, height=460)

    dlg = ft.AlertDialog(
        title=ft.Text('我的反馈内容'),
        content=body,
        actions=[
            ft.TextButton(content='关闭', on_click=close_dlg),
        ],
        modal=True,
    )
    return dlg
