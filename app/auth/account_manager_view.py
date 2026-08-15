"""
账号管理视图（管理员）
提供学生账号列表、创建、启用/禁用、重置密码、删除功能
"""

import flet as ft
from app.auth.auth_service import (
    register_user, get_student_list, toggle_student_status,
    reset_student_password, delete_student
)


def build_account_manager_view(page: ft.Page, on_back) -> list:
    """
    构建账号管理视图
    返回控件列表供 ft.Column 使用
    """

    # ---- 状态容器 ----
    student_list_col = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)

    # ---- 统计信息栏（需要动态刷新） ----
    stats_bar = ft.Row([], spacing=12)

    # ---- 显示 SnackBar ----
    def show_snack(msg: str, success: bool = True):
        snack = ft.SnackBar(
            ft.Text(msg),
            bgcolor='#4CAF50' if success else '#FF5252',
        )
        page.overlay.append(snack)
        snack.open = True
        page.update()

    # ---- 刷新统计栏 ----
    def refresh_stats():
        students = get_student_list()
        active_count = sum(1 for s in students if s['status'] == 'active')
        test_count = sum(1 for s in students if s.get('user_type') == 'test')
        stats_bar.controls = [
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.SCHOOL, color='#1565C0', size=20),
                    ft.Text(f'学生总数: {len(students)}', size=13, color='#424242', weight=ft.FontWeight.W_500),
                ], spacing=6),
                bgcolor='#E3F2FD',
                border_radius=8,
                padding=ft.Padding(12, 6, 12, 6),
            ),
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.CHECK_CIRCLE, color='#4CAF50', size=20),
                    ft.Text(f'启用: {active_count}', size=13, color='#424242', weight=ft.FontWeight.W_500),
                ], spacing=6),
                bgcolor='#E8F5E9',
                border_radius=8,
                padding=ft.Padding(12, 6, 12, 6),
            ),
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.BLOCK, color='#FF5252', size=20),
                    ft.Text(f'禁用: {len(students) - active_count}', size=13, color='#424242', weight=ft.FontWeight.W_500),
                ], spacing=6),
                bgcolor='#FFEBEE',
                border_radius=8,
                padding=ft.Padding(12, 6, 12, 6),
            ),
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.SCIENCE, color='#FF9800', size=20),
                    ft.Text(f'测试用户: {test_count}', size=13, color='#424242', weight=ft.FontWeight.W_500),
                ], spacing=6),
                bgcolor='#FFF3E0',
                border_radius=8,
                padding=ft.Padding(12, 6, 12, 6),
            ),
        ]
        if stats_bar.page:
            stats_bar.update()

    # ---- 构建单个学生行 ----
    def _build_student_row(s):
        is_active = s['status'] == 'active'
        status_color = '#4CAF50' if is_active else '#FF5252'
        status_text = '启用' if is_active else '禁用'
        student_id_display = f'学号: {s["student_id"]}' if s.get('student_id') else ''
        class_display = f'班级: {s["class_name"]}' if s.get('class_name') else ''
        real_name_display = s['real_name'] or '未设置姓名'
        # 用户类型标签
        user_type = s.get('user_type', 'formal')
        is_test = user_type == 'test'
        utype_label = '测试' if is_test else '正式'
        utype_bg = '#FFF3E0' if is_test else '#E3F2FD'
        utype_color = '#FF9800' if is_test else '#1565C0'

        info_parts = []
        if student_id_display:
            info_parts.append(student_id_display)
        if class_display:
            info_parts.append(class_display)
        info_text = '  |  '.join(info_parts) if info_parts else ''

        return ft.Container(
            content=ft.Row([
                ft.Container(
                    content=ft.Icon(ft.Icons.PERSON, color='#1976D2', size=32),
                    bgcolor='#E3F2FD',
                    border_radius=25,
                    width=50,
                    height=50,
                    alignment=ft.Alignment.CENTER,
                ),
                ft.Column([
                    ft.Text(s['username'], size=15, weight=ft.FontWeight.W_500, color='#212121'),
                    ft.Text(real_name_display, size=12, color='#616161'),
                    ft.Text(info_text, size=11, color='#9E9E9E') if info_text else ft.Text(''),
                ], spacing=2, expand=True),
                ft.Container(
                    content=ft.Text(utype_label, size=12, color=utype_color, weight=ft.FontWeight.W_500),
                    bgcolor=utype_bg,
                    border_radius=12,
                    padding=ft.Padding(12, 4, 12, 4),
                ),
                ft.Container(
                    content=ft.Text(status_text, size=12, color='white', weight=ft.FontWeight.W_500),
                    bgcolor=status_color,
                    border_radius=12,
                    padding=ft.Padding(12, 4, 12, 4),
                ),
                ft.PopupMenuButton(
                    icon=ft.Icons.MORE_VERT,
                    items=[
                        ft.PopupMenuItem(
                            content=ft.Row([
                                ft.Icon(ft.Icons.LOCK_RESET, size=18, color='#FF9800'),
                                ft.Text('重置密码', size=13),
                            ], spacing=8),
                            on_click=lambda e, sid=s['id']: open_reset_dlg(sid),
                        ),
                        ft.PopupMenuItem(
                            content=ft.Row([
                                ft.Icon(
                                    ft.Icons.BLOCK if is_active else ft.Icons.CHECK_CIRCLE,
                                    size=18,
                                    color='#757575'
                                ),
                                ft.Text('禁用' if is_active else '启用', size=13),
                            ], spacing=8),
                            on_click=lambda e, sid=s['id']: toggle_status(sid),
                        ),
                        ft.PopupMenuItem(
                            content=ft.Row([
                                ft.Icon(ft.Icons.DELETE, size=18, color='#FF5252'),
                                ft.Text('删除', size=13, color='#FF5252'),
                            ], spacing=8),
                            on_click=lambda e, sid=s['id'], uname=s['username']: open_delete_dlg(sid, uname),
                        ),
                    ],
                ),
            ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor='white',
            border_radius=12,
            padding=ft.Padding(16, 12, 8, 12),
            shadow=ft.BoxShadow(spread_radius=0.5, blur_radius=6, color='#00000010'),
        )

    # ---- 刷新列表（仅在页面已挂载后调用） ----
    def refresh_list():
        students = get_student_list()
        student_list_col.controls.clear()

        if not students:
            student_list_col.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.PEOPLE_OUTLINE, size=48, color='#BDBDBD'),
                        ft.Text('暂无学生账号', size=14, color='#9E9E9E'),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=40,
                    alignment=ft.Alignment.CENTER,
                )
            )
        else:
            for s in students:
                student_list_col.controls.append(_build_student_row(s))

        if student_list_col.page:
            student_list_col.update()

        refresh_stats()

    # ---- 创建账号对话框 ----
    def open_create_dlg(e):
        print("[DEBUG] open_create_dlg called!")
        create_username = ft.TextField(
            label='账号名', hint_text='请输入账号名',
            prefix_icon=ft.Icons.PERSON,
            border_color='#BBDEFB', focused_border_color='#1976D2',
        )
        create_student_id = ft.TextField(
            label='学号', hint_text='请输入学号',
            prefix_icon=ft.Icons.BADGE,
            border_color='#BBDEFB', focused_border_color='#1976D2',
        )
        create_password = ft.TextField(
            label='初始密码', hint_text='请输入初始密码（至少6位）',
            prefix_icon=ft.Icons.LOCK,
            border_color='#BBDEFB', focused_border_color='#1976D2',
            password=True, can_reveal_password=True,
        )
        user_type_dropdown = ft.Dropdown(
            label='用户类型',
            options=[
                ft.dropdown.Option('formal', '正式用户'),
                ft.dropdown.Option('test', '测试用户'),
            ],
            value='formal',
            border_color='#BBDEFB',
            focused_border_color='#1976D2',
        )
        create_error = ft.Text('', color='#FF5252', size=13)

        def cancel(e):
            ##page.overlay.remove(dlg)
            dlg.open = False
            page.update()

        def do_create(e):
            username = (create_username.value or '').strip()
            student_id_val = (create_student_id.value or '').strip()
            password = create_password.value or ''

            if not username:
                create_error.value = '请输入账号名'
                create_error.update()
                return
            if not student_id_val:
                create_error.value = '请输入学号'
                create_error.update()
                return
            if len(password) < 6:
                create_error.value = '密码长度至少6位'
                create_error.update()
                return

            try:
                result = register_user(
                    username=username,
                    password=password,
                    role='student',
                    student_id=student_id_val,
                    user_type=user_type_dropdown.value or 'formal',
                    must_change_password=1
                )
                if result['success']:
                    dlg.open = False
                    page.update()
                    show_snack(f'账号 "{username}" 创建成功')
                    refresh_list()
                else:
                    create_error.value = result['message']
                    create_error.update()
            except Exception as ex:
                create_error.value = f'创建失败: {ex}'
                create_error.update()

        dlg = ft.AlertDialog(
            title=ft.Text('创建学生账号', weight=ft.FontWeight.BOLD, size=18),
            content=ft.Column([
                create_username,
                ft.Divider(height=8, color='transparent'),
                create_student_id,
                ft.Divider(height=8, color='transparent'),
                create_password,
                ft.Divider(height=8, color='transparent'),
                user_type_dropdown,
                ft.Divider(height=4, color='transparent'),
                create_error,
            ], tight=True, width=380),
            actions=[
                ft.TextButton(content='取消', on_click=cancel),
                ft.ElevatedButton(
                    content='创建',
                    on_click=do_create,
                    style=ft.ButtonStyle(bgcolor='#1976D2', color='white', shape=ft.RoundedRectangleBorder(radius=8)),
                ),
            ],
            modal=True,
        )
        page.show_dialog(dlg)
        print(">>> 对话框已打开，open=", dlg.open)

    # ---- 重置密码对话框 ----
    def open_reset_dlg(sid):
        reset_password_field = ft.TextField(
            label='新密码（留空则自动生成）', hint_text='留空自动生成随机密码',
            prefix_icon=ft.Icons.LOCK,
            border_color='#BBDEFB', focused_border_color='#1976D2',
            password=True, can_reveal_password=True,
        )
        reset_info = ft.Text('', color='#757575', size=13)
        reset_error = ft.Text('', color='#FF5252', size=13)

        def cancel(e):
            ##page.overlay.remove(dlg)
            dlg.open = False
            page.update()

        def do_reset(e):
            new_pw = reset_password_field.value or None
            result = reset_student_password(sid, new_pw)
            if result['success']:
                reset_info.value = f'新密码: {result["new_password"]}'
                reset_error.value = ''
                reset_info.update()
            else:
                reset_info.value = ''
                reset_error.value = result['message']
                reset_error.update()

        dlg = ft.AlertDialog(
            title=ft.Text('重置密码', weight=ft.FontWeight.BOLD, size=18),
            content=ft.Column([
                reset_password_field,
                ft.Divider(height=4, color='transparent'),
                reset_info,
                reset_error,
            ], tight=True, width=380),
            actions=[
                ft.TextButton(content='取消', on_click=cancel),
                ft.ElevatedButton(
                    content='确认重置',
                    on_click=do_reset,
                    style=ft.ButtonStyle(bgcolor='#FF9800', color='white', shape=ft.RoundedRectangleBorder(radius=8)),
                ),
            ],
            modal=True,
        )
        page.show_dialog(dlg)

    # ---- 删除确认对话框 ----
    def open_delete_dlg(sid, uname):
        def cancel(e):
            ##page.overlay.remove(dlg)
            dlg.open = False
            page.update()
        def do_delete(e):
            result = delete_student(sid)
            ##page.overlay.remove(dlg)
            dlg.open = False
            page.update()
            if result['success']:
                show_snack('账号已删除')
                refresh_list()
            else:
                show_snack(result['message'], success=False)

        dlg = ft.AlertDialog(
            title=ft.Text('确认删除', weight=ft.FontWeight.BOLD, size=18),
            content=ft.Text(f'确定要删除学生账号 "{uname}" 吗？\n该操作将同时删除该学生的所有作答记录，且不可恢复。'),
            actions=[
                ft.TextButton(content='取消', on_click=cancel),
                ft.ElevatedButton(
                    content='确认删除',
                    on_click=do_delete,
                    style=ft.ButtonStyle(bgcolor='#FF5252', color='white', shape=ft.RoundedRectangleBorder(radius=8)),
                ),
            ],
            modal=True,
        )
        page.show_dialog(dlg)

    # ---- 切换启用/禁用状态 ----
    def toggle_status(sid):
        result = toggle_student_status(sid)
        show_snack(result['message'], result['success'])
        if result['success']:
            refresh_list()

    # ---- 初始数据填充（直接填充 controls，不调用 update） ----
    # 初始统计栏
    students = get_student_list()
    active_count = sum(1 for s in students if s['status'] == 'active')
    test_count = sum(1 for s in students if s.get('user_type') == 'test')
    stats_bar.controls = [
        ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.SCHOOL, color='#1565C0', size=20),
                ft.Text(f'学生总数: {len(students)}', size=13, color='#424242', weight=ft.FontWeight.W_500),
            ], spacing=6),
            bgcolor='#E3F2FD', border_radius=8, padding=ft.Padding(12, 6, 12, 6),
        ),
        ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.CHECK_CIRCLE, color='#4CAF50', size=20),
                ft.Text(f'启用: {active_count}', size=13, color='#424242', weight=ft.FontWeight.W_500),
            ], spacing=6),
            bgcolor='#E8F5E9', border_radius=8, padding=ft.Padding(12, 6, 12, 6),
        ),
        ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.BLOCK, color='#FF5252', size=20),
                ft.Text(f'禁用: {len(students) - active_count}', size=13, color='#424242', weight=ft.FontWeight.W_500),
            ], spacing=6),
            bgcolor='#FFEBEE', border_radius=8, padding=ft.Padding(12, 6, 12, 6),
        ),
        ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.SCIENCE, color='#FF9800', size=20),
                ft.Text(f'测试用户: {test_count}', size=13, color='#424242', weight=ft.FontWeight.W_500),
            ], spacing=6),
            bgcolor='#FFF3E0', border_radius=8, padding=ft.Padding(12, 6, 12, 6),
        ),
    ]

    # 初始学生列表
    if not students:
        student_list_col.controls.append(
            ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.PEOPLE_OUTLINE, size=48, color='#BDBDBD'),
                    ft.Text('暂无学生账号', size=14, color='#9E9E9E'),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=40,
                alignment=ft.Alignment.CENTER,
            )
        )
    else:
        for s in students:
            student_list_col.controls.append(_build_student_row(s))

    # ---- 创建账号处理函数 ----
    def handle_create(e):
        print(">>> 创建账号按钮被点击")   # 新增
        open_create_dlg(e)

    # ---- 头部操作栏 ----
    header_bar = ft.Row([
        ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=lambda e: on_back(),
                     icon_color='#1976D2', tooltip='返回仪表盘', icon_size=22),
        ft.Text('账号管理', size=22, weight=ft.FontWeight.BOLD, color='#212121'),
        ft.Container(expand=True),
        ft.ElevatedButton(
            content='创建账号',
            icon=ft.Icons.PERSON_ADD,
            on_click=handle_create,
            style=ft.ButtonStyle(
                bgcolor='#1976D2',
                color='white',
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
        ),
    ])

    return [
        header_bar,
        ft.Divider(height=12, color='transparent'),
        stats_bar,
        ft.Divider(height=16, color='transparent'),
        student_list_col,
    ]
