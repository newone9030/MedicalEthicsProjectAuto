"""
任务编辑器视图（管理员）
"""

from datetime import datetime, timedelta
import threading
import flet as ft
from app.task.task_service import (
    create_task, update_task, get_task, list_tasks,
    publish_task, close_task, delete_task, set_task_background,
    move_task_up, move_task_down, reopen_task,
)
from app.case.case_service import list_cases
from app.response.response_service import (
    get_task_response_summary,
    admin_delete_student_responses,
    admin_delete_all_responses,
)


def build_task_list_view(page: ft.Page, on_create, on_edit) -> ft.Column:
    """任务列表视图"""
    status_dropdown = ft.Dropdown(
        label='状态筛选',
        options=[
            ft.DropdownOption(key='', text='全部'),
            ft.DropdownOption(key='draft', text='草稿'),
            ft.DropdownOption(key='published', text='已发布'),
            ft.DropdownOption(key='active', text='进行中'),
            ft.DropdownOption(key='closed', text='已关闭'),
        ],
        value='',
        border_color='#BBDEFB',
        focused_border_color='#1976D2',
        on_select=lambda e: refresh_list(),
        width=150,
    )

    search_field = ft.TextField(
        label='搜索任务',
        prefix_icon=ft.Icons.SEARCH,
        border_color='#BBDEFB',
        focused_border_color='#1976D2',
        on_change=lambda e: refresh_list(),
        expand=True,
    )

    task_list = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO)

    def refresh_list():
        status = status_dropdown.value or ''
        search = search_field.value or ''
        tasks = list_tasks(status_filter=status, search=search)

        task_list.controls.clear()
        if not tasks:
            task_list.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.ASSIGNMENT, size=48, color='#BDBDBD'),
                        ft.Text('暂无任务', color='#9E9E9E', size=14),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=40,
                    alignment=ft.Alignment.CENTER,
                )
            )
        else:
            for idx, t in enumerate(tasks):
                task_list.controls.append(_build_task_card(t, page, on_edit, refresh_list, position=idx + 1))

        if task_list.page:
            task_list.update()

    # 初始填充任务列表（不调用 update，控件尚未添加到页面）
    tasks = list_tasks()
    if not tasks:
        task_list.controls.append(
            ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.ASSIGNMENT, size=48, color='#BDBDBD'),
                    ft.Text('暂无任务', color='#9E9E9E', size=14),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=40,
                alignment=ft.Alignment.CENTER,
            )
        )
    else:
        for idx, t in enumerate(tasks):
            task_list.controls.append(_build_task_card(t, page, on_edit, refresh_list, position=idx + 1))

    return ft.Column([
        ft.Row([
            ft.Text('任务管理', size=22, weight=ft.FontWeight.BOLD, color='#1565C0'),
            ft.ElevatedButton(
                content='创建任务',
                icon=ft.Icons.ADD,
                on_click=lambda e: on_create(page),
                style=ft.ButtonStyle(bgcolor='#1976D2', color='white', shape=ft.RoundedRectangleBorder(radius=8)),
            ),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ft.Divider(height=10, color='transparent'),
        ft.Row([search_field, status_dropdown], spacing=10),
        ft.Divider(height=10, color='transparent'),
        task_list,
    ], expand=True, spacing=0)


def _build_task_card(task: dict, page: ft.Page, on_edit, on_refresh, position: int = None) -> ft.Container:
    """构建任务卡片"""
    status_config = {
        'draft': ('草稿', '#9E9E9E'),
        'published': ('已发布', '#2196F3'),
        'active': ('进行中', '#4CAF50'),
        'closed': ('已关闭', '#757575'),
    }
    label, color = status_config.get(task['status'], ('未知', '#9E9E9E'))

    # 时间格式化
    start_str = task['start_time'].strftime('%m/%d %H:%M') if hasattr(task['start_time'], 'strftime') else str(task['start_time'])[:16]
    end_str = task['end_time'].strftime('%m/%d %H:%M') if hasattr(task['end_time'], 'strftime') else str(task['end_time'])[:16]

    # 菜单项
    menu_items = [
        ft.PopupMenuItem(content='编辑', icon=ft.Icons.EDIT,
                         on_click=lambda e, t=task: on_edit(t['id'], page)),
        ft.PopupMenuItem(content='上移', icon=ft.Icons.ARROW_UPWARD,
                         on_click=lambda e, t=task: _do_move(t, 'up', page, on_refresh)),
        ft.PopupMenuItem(content='下移', icon=ft.Icons.ARROW_DOWNWARD,
                         on_click=lambda e, t=task: _do_move(t, 'down', page, on_refresh)),
    ]

    # 非草稿任务可以管理作答
    if task['status'] != 'draft':
        menu_items.append(
            ft.PopupMenuItem(content='管理作答', icon=ft.Icons.PEOPLE,
                             on_click=lambda e, t=task: _show_response_manager(t, page, on_refresh)),
        )

    # 背景资料标记（仅非草稿任务可操作）
    if task['status'] != 'draft':
        is_bg = task.get('task_type') == 'background'
        bg_text = '取消背景资料' if is_bg else '设为背景资料'
        bg_icon = ft.Icons.STAR if is_bg else ft.Icons.STAR_OUTLINE
        menu_items.append(
            ft.PopupMenuItem(content=bg_text, icon=bg_icon,
                             on_click=lambda e, t=task, bg=is_bg: _do_toggle_background(t, bg, page, on_refresh)),
        )

    if task['status'] == 'draft':
        menu_items.append(
            ft.PopupMenuItem(content='发布', icon=ft.Icons.PUBLISH,
                             on_click=lambda e, t=task: _do_publish(t, page, on_refresh)),
        )
        menu_items.append(
            ft.PopupMenuItem(content='删除', icon=ft.Icons.DELETE,
                             on_click=lambda e, t=task: _do_delete(t, page, on_refresh)),
        )
    elif task['status'] in ('published', 'active'):
        menu_items.append(
            ft.PopupMenuItem(content='关闭', icon=ft.Icons.CANCEL,
                             on_click=lambda e, t=task: _do_close(t, page, on_refresh)),
        )
    elif task['status'] == 'closed':
        menu_items.append(
            ft.PopupMenuItem(content='回退到草稿', icon=ft.Icons.UNDO,
                             on_click=lambda e, t=task: _do_reopen(t, page, on_refresh)),
        )
        menu_items.append(
            ft.PopupMenuItem(content='删除', icon=ft.Icons.DELETE,
                             on_click=lambda e, t=task: _do_delete(t, page, on_refresh)),
        )

    # 背景资料徽章
    bg_badge = None
    if task.get('task_type') == 'background':
        bg_badge = ft.Container(
            content=ft.Text('背景资料', size=11, color='#E65100'),
            bgcolor='#FFF3E0',
            border_radius=10,
            padding=ft.Padding(8, 2, 8, 2),
        )

    name_row_controls = [
        ft.Text(task['name'], size=15, weight=ft.FontWeight.W_500, color='#212121'),
        ft.Container(
            content=ft.Text(label, size=11, color='white'),
            bgcolor=color,
            border_radius=10,
            padding=ft.Padding(8, 2, 8, 2),
        ),
    ]
    if bg_badge:
        name_row_controls.append(bg_badge)

    return ft.Container(
        content=ft.Row([
            ft.Column([
                ft.Row(name_row_controls, spacing=8),
                ft.Text(
                    f'第 {position} 个任务 | {task["case_count"]} 个案例 | {start_str} ~ {end_str}'
                    if position else f'{task["case_count"]} 个案例 | {start_str} ~ {end_str}',
                    size=12, color='#9E9E9E',
                ),
            ], spacing=4, expand=True),
            ft.PopupMenuButton(icon=ft.Icons.MORE_VERT, items=menu_items),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        bgcolor='white',
        border_radius=12,
        padding=16,
        shadow=ft.BoxShadow(spread_radius=0.5, blur_radius=8, color='#00000015'),
    )


def _do_publish(task: dict, page: ft.Page, on_refresh):
    result = publish_task(task['id'])
    _show_snack(page, result)
    if result['success']:
        on_refresh()


def _do_close(task: dict, page: ft.Page, on_refresh):
    result = close_task(task['id'])
    _show_snack(page, result)
    if result['success']:
        on_refresh()


def _do_move(task: dict, direction: str, page: ft.Page, on_refresh):
    result = move_task_up(task['id']) if direction == 'up' else move_task_down(task['id'])
    _show_snack(page, result)
    if result['success']:
        on_refresh()


def _do_reopen(task: dict, page: ft.Page, on_refresh):
    result = reopen_task(task['id'])
    _show_snack(page, result)
    if result['success']:
        on_refresh()


def _do_delete(task: dict, page: ft.Page, on_refresh):
    def confirm(e):
        ##page.overlay.remove(dlg)
        dlg.open = False
        page.update()
        result = delete_task(task['id'])
        _show_snack(page, result)
        if result['success']:
            on_refresh()

    def cancel(e):
        ##page.overlay.remove(dlg)
        dlg.open = False
        page.update()

    dlg = ft.AlertDialog(
        title=ft.Text('确认删除'),
        content=ft.Text(f'确定要删除任务「{task["name"]}」吗？'),
        actions=[
            ft.TextButton(content=ft.Text('取消'), on_click=cancel),
            ft.ElevatedButton(content=ft.Text('确认删除'), on_click=confirm,
                            style=ft.ButtonStyle(bgcolor='#FF5252', color='white')),
        ],
        modal=True,
    )
    page.show_dialog(dlg)


def _show_snack(page: ft.Page, result: dict):
    snack = ft.SnackBar(
        ft.Text(result['message']),
        bgcolor='#4CAF50' if result['success'] else '#FF5252',
    )
    page.overlay.append(snack)
    snack.open = True
    page.update()


def _do_toggle_background(task: dict, is_background: bool, page: ft.Page, on_refresh):
    """切换任务背景资料标记"""
    if is_background:
        result = set_task_background(task['id'], False)
    else:
        result = set_task_background(task['id'], True)
    _show_snack(page, result)
    if result['success']:
        on_refresh()


def _show_response_manager(task: dict, page: ft.Page, on_refresh):
    """显示作答管理对话框：列出所有已提交作答的学生，支持删除单个或全部作答"""

    # -- 第一步：创建所有 UI 控件（不调用任何数据查询或 .update()） --

    response_list = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, height=300)
    count_text = ft.Text('加载中...', size=12, color='#757575')
    clear_all_btn = ft.OutlinedButton(
        content='清除全部作答',
        icon=ft.Icons.DELETE_SWEEP,
        style=ft.ButtonStyle(color='#FF5252',
                             side=ft.BorderSide(color='#FF5252', width=1)),
    )
    # 用一个可变容器持有 summary 数据，供内部闭包引用
    summary_holder = {'data': []}
    # 标志：对话框是否仍处于打开状态
    dlg_opened = {'value': True}

    def close_dlg(e=None):
        dlg_opened['value'] = False
        dlg2.open = False
        page.update()

    def clear_all(e):
        count = len(summary_holder['data'])
        confirm_text = f'确定要删除任务「{task["name"]}」下所有 {count} 名学生的作答记录吗？\n\n此操作不可撤销！'

        def do_clear(e2):
            confirm_dlg.open = False
            page.update()
            result = admin_delete_all_responses(task['id'])
            _show_snack(page, result)
            if result['success']:
                on_refresh()
                close_dlg()

        def close_confirm(e2):
            confirm_dlg.open = False
            page.update()

        confirm_dlg = ft.AlertDialog(
            title=ft.Text('确认清除全部作答'),
            content=ft.Text(confirm_text),
            actions=[
                ft.TextButton(content='取消', on_click=close_confirm),
                ft.ElevatedButton(content='确认清除', on_click=do_clear,
                                  style=ft.ButtonStyle(bgcolor='#FF5252', color='white')),
            ],
            modal=True,
        )
        page.show_dialog(confirm_dlg)

    clear_all_btn.on_click = clear_all

    dlg2 = ft.AlertDialog(
        title=ft.Row([
            ft.Text(f'作答管理 - {task["name"]}', size=16, weight=ft.FontWeight.W_500),
            ft.Container(expand=True),
            ft.IconButton(icon=ft.Icons.CLOSE, on_click=close_dlg, icon_size=20),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        content=ft.Column([
            count_text,
            ft.Divider(height=8, color='transparent'),
            response_list,
            ft.Divider(height=12, color='transparent'),
            ft.Row([
                ft.Container(expand=True),
                clear_all_btn,
            ]),
        ], spacing=0),
        actions=[
            ft.TextButton(content='关闭', on_click=close_dlg),
        ],
        modal=True,
    )
    # 对话框挂载到页面（官方 API，自动管理 on_dismiss 与出栈）
    page.show_dialog(dlg2)

    # -- 第二步：所有控件已加载到页面后，再查询数据并填充列表 --

    def build_response_list_content():
        """根据 summary_holder['data'] 重新构建列表内容"""
        if not dlg_opened['value']:
            return
        response_list.controls.clear()
        summary = summary_holder['data']
        count_text.value = f'共 {len(summary)} 名学生已提交作答'
        if not summary:
            response_list.controls.append(
                ft.Text('暂无学生作答记录', color='#9E9E9E', size=13)
            )
            clear_all_btn.visible = False
        else:
            clear_all_btn.visible = True
            for s in summary:
                sid = s['student_id']
                sname = s['real_name']

                def make_delete_handler(_sid=sid, _sname=sname):
                    def handler(e):
                        _do_delete_one_response(task['id'], _sid, _sname, page,
                                                summary_holder, build_response_list_content)
                    return handler

                response_list.controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Column([
                                ft.Text(sname, size=13, weight=ft.FontWeight.W_500),
                                ft.Text(
                                    f'{s["submitted_count"]}/{s["total_cases"]} 个案例已提交',
                                    size=11, color='#4CAF50',
                                ),
                            ], spacing=2, expand=True),
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE,
                                icon_color='#FF5252', icon_size=18,
                                tooltip=f'删除 {sname} 的作答',
                                on_click=make_delete_handler(),
                            ),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        bgcolor='#FAFAFA',
                        border_radius=8,
                        padding=ft.Padding(12, 8, 8, 8),
                    )
                )
        page.update()

    # 查询数据并填充
    summary_holder['data'] = get_task_response_summary(task['id'])
    build_response_list_content()


def _do_delete_one_response(task_id, student_id, student_name, page, summary_holder, refresh_callback):
    """删除单个学生的作答"""
    result = admin_delete_student_responses(task_id, student_id)
    _show_snack(page, result)
    if result['success']:
        # 从 summary 列表中移除该学生
        summary_holder['data'][:] = [s for s in summary_holder['data'] if s['student_id'] != student_id]
        refresh_callback()


def build_task_editor_view(page: ft.Page, task_id: int = None, on_back=None) -> list:
    """任务编辑器视图"""
    is_edit = task_id is not None
    task_data = get_task(task_id) if is_edit else None

    name_field = ft.TextField(
        label='任务名称',
        value=task_data['name'] if task_data else '',
        prefix_icon=ft.Icons.TITLE,
        border_color='#BBDEFB',
        focused_border_color='#1976D2',
    )

    desc_field = ft.TextField(
        label='任务描述',
        value=task_data['description'] if task_data else '',
        multiline=True,
        min_lines=3,
        max_lines=8,
        border_color='#BBDEFB',
        focused_border_color='#1976D2',
    )

    # 默认时间
    now = datetime.now()
    default_start = task_data['start_time'] if task_data else now + timedelta(hours=1)
    default_end = task_data['end_time'] if task_data else now + timedelta(days=7)

    start_picker = ft.TextField(
        label='开始时间 (YYYY-MM-DD HH:MI)',
        value=default_start.strftime('%Y-%m-%d %H:%M') if hasattr(default_start, 'strftime') else str(default_start)[:16],
        prefix_icon=ft.Icons.SCHEDULE,
        border_color='#BBDEFB',
        focused_border_color='#1976D2',
        hint_text='例如: 2026-08-05 08:00',
    )

    end_picker = ft.TextField(
        label='结束时间 (YYYY-MM-DD HH:MI)',
        value=default_end.strftime('%Y-%m-%d %H:%M') if hasattr(default_end, 'strftime') else str(default_end)[:16],
        prefix_icon=ft.Icons.SCHEDULE_SEND,
        border_color='#BBDEFB',
        focused_border_color='#1976D2',
        hint_text='例如: 2026-08-12 23:59',
    )

    # 案例选择区
    all_cases = list_cases()
    selected_case_ids = [c['id'] for c in task_data['cases']] if task_data else []

    # 已选案例 Chips
    selected_chips = ft.Row(spacing=8, wrap=True)

    def refresh_chips():
        selected_chips.controls.clear()
        for cid in selected_case_ids:
            case = next((c for c in all_cases if c['id'] == cid), None)
            if case:
                selected_chips.controls.append(
                    ft.Chip(
                        ft.Row([
                            ft.Text(case['title'][:15], size=12),
                            ft.IconButton(
                                icon=ft.Icons.CLOSE, icon_size=14, width=20, height=20,
                                on_click=lambda e, cid=cid: remove_case(cid),
                            ),
                        ], spacing=2, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        bgcolor='#E3F2FD',
                    )
                )

    def remove_case(case_id):
        if case_id in selected_case_ids:
            selected_case_ids.remove(case_id)
        # 延迟刷新，避免在事件处理中销毁控件导致事件管道崩溃
        threading.Timer(0.05, lambda: (refresh_chips(), refresh_checklist(), page.update())).start()

    # 案例选择列表
    case_checklist = ft.Column(spacing=4, height=250, scroll=ft.ScrollMode.AUTO)

    def refresh_checklist():
        case_checklist.controls.clear()
        for case in all_cases:
            is_selected = case['id'] in selected_case_ids
            case_checklist.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Checkbox(
                            value=is_selected,
                            on_change=lambda e, cid=case['id']: toggle_case(cid, e.control.value),
                            fill_color='#1976D2',
                        ),
                        ft.Column([
                            ft.Text(case['title'], size=13, weight=ft.FontWeight.W_500),
                            ft.Text(case['theme'], size=11, color='#9E9E9E'),
                        ], spacing=1, expand=True),
                    ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.Padding(0, 4, 0, 4),
                )
            )

    def toggle_case(case_id, is_checked):
        if is_checked and case_id not in selected_case_ids:
            selected_case_ids.append(case_id)
        elif not is_checked and case_id in selected_case_ids:
            selected_case_ids.remove(case_id)
        refresh_chips()
        page.update()

    # 初始构建已选案例 chips（直接填充，不调用 update）
    for cid in selected_case_ids:
        case = next((c for c in all_cases if c['id'] == cid), None)
        if case:
            selected_chips.controls.append(
                ft.Chip(
                    ft.Row([
                        ft.Text(case['title'][:15], size=12),
                        ft.IconButton(
                            icon=ft.Icons.CLOSE, icon_size=14, width=20, height=20,
                            on_click=lambda e, cid=cid: remove_case(cid),
                        ),
                    ], spacing=2, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    bgcolor='#E3F2FD',
                )
            )

    # 初始构建案例选择列表（直接填充，不调用 update）
    for case in all_cases:
        is_selected = case['id'] in selected_case_ids
        case_checklist.controls.append(
            ft.Container(
                content=ft.Row([
                    ft.Checkbox(
                        value=is_selected,
                        on_change=lambda e, cid=case['id']: toggle_case(cid, e.control.value),
                        fill_color='#1976D2',
                    ),
                    ft.Column([
                        ft.Text(case['title'], size=13, weight=ft.FontWeight.W_500),
                        ft.Text(case['theme'], size=11, color='#9E9E9E'),
                    ], spacing=1, expand=True),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding(0, 4, 0, 4),
            )
        )

    # 时间不重叠提示
    conflict_text = ft.Text('', size=12, color='#FF5252')

    def check_time_conflict(e=None):
        try:
            s = datetime.strptime(start_picker.value.strip(), '%Y-%m-%d %H:%M')
            e_time = datetime.strptime(end_picker.value.strip(), '%Y-%m-%d %H:%M')
            if s >= e_time:
                conflict_text.value = '开始时间必须早于结束时间'
            else:
                conflict_text.value = ''
        except ValueError:
            conflict_text.value = '时间格式不正确，请使用 YYYY-MM-DD HH:MI'
        conflict_text.update()

    start_picker.on_change = check_time_conflict
    end_picker.on_change = check_time_conflict

    def save_task(e):
        name = name_field.value.strip()
        if not name:
            _show_snack(page, {'success': False, 'message': '请填写任务名称'})
            return
        if not selected_case_ids:
            _show_snack(page, {'success': False, 'message': '请至少选择一个案例'})
            return

        try:
            s = datetime.strptime(start_picker.value.strip(), '%Y-%m-%d %H:%M')
            e_time = datetime.strptime(end_picker.value.strip(), '%Y-%m-%d %H:%M')
        except ValueError:
            _show_snack(page, {'success': False, 'message': '时间格式不正确'})
            return

        if s >= e_time:
            _show_snack(page, {'success': False, 'message': '开始时间必须早于结束时间'})
            return

        try:
            if is_edit:
                result = update_task(task_id, name, desc_field.value, s, e_time, selected_case_ids)
            else:
                user = page.session.store.get('user')
                result = create_task(name, desc_field.value, s, e_time, selected_case_ids, user['id'])
        except Exception as ex:
            _show_snack(page, {'success': False, 'message': f'保存失败: {ex}'})
            return

        _show_snack(page, result)
        if result['success'] and on_back:
            on_back()

    return [
        ft.Column([
            ft.Row([
                ft.IconButton(icon=ft.Icons.ARROW_BACK, icon_color='#1565C0',
                              on_click=lambda e: on_back() if on_back else None),
                ft.Text('编辑任务' if is_edit else '创建任务', size=22, weight=ft.FontWeight.BOLD, color='#1565C0'),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(height=15, color='transparent'),

            # 基本信息
            ft.Container(
                content=ft.Column([
                    ft.Text('基本信息', size=16, weight=ft.FontWeight.W_500),
                    name_field,
                    desc_field,
                    ft.Row([start_picker, end_picker], spacing=16),
                    conflict_text,
                ], spacing=10),
                bgcolor='white', border_radius=12, padding=20,
                shadow=ft.BoxShadow(spread_radius=0.5, blur_radius=8, color='#00000015'),
            ),
            ft.Divider(height=15, color='transparent'),

            # 案例选择
            ft.Container(
                content=ft.Column([
                    ft.Text('选择案例', size=16, weight=ft.FontWeight.W_500),
                    ft.Divider(height=5, color='transparent'),
                    ft.Text('已选案例:', size=12, color='#757575'),
                    selected_chips,
                    ft.Divider(height=10, color='transparent'),
                    ft.Text('案例库:', size=12, color='#757575'),
                    case_checklist,
                ], spacing=6),
                bgcolor='white', border_radius=12, padding=20,
                shadow=ft.BoxShadow(spread_radius=0.5, blur_radius=8, color='#00000015'),
                expand=True,
            ),
            ft.Divider(height=15, color='transparent'),

            # 保存按钮
            ft.Container(
                content=ft.Row([
                    ft.ElevatedButton(
                        content=ft.Text('保存任务'), icon=ft.Icons.SAVE,
                        on_click=save_task,
                        style=ft.ButtonStyle(bgcolor='#1976D2', color='white',
                            shape=ft.RoundedRectangleBorder(radius=8),
                            padding=ft.Padding(40, 15, 40, 15)),
                    ),
                ], alignment=ft.MainAxisAlignment.END),
            ),
        ], expand=True, spacing=0, scroll=ft.ScrollMode.AUTO),
    ]
