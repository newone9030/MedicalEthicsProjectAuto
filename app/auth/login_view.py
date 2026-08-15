"""
登录/注册页面视图
"""

import flet as ft
import asyncio
from app.auth.auth_service import login, register_user


def build_login_view(page: ft.Page) -> list:
    """
    构建登录/注册页面
    返回 Flet Control 列表
    """

    # --- 状态变量 ---
    username_field = ft.Ref[ft.TextField]()
    password_field = ft.Ref[ft.TextField]()
    confirm_password_field = ft.Ref[ft.TextField]()
    real_name_field = ft.Ref[ft.TextField]()
    class_name_field = ft.Ref[ft.TextField]()
    error_text = ft.Ref[ft.Text]()
    is_registering = {'value': False}

    # 学生注册额外字段容器
    student_fields = ft.Ref[ft.Column]()
    confirm_field = ft.Ref[ft.Column]()

    selected_role_index = 0

    def on_role_change(e):
        """角色切换时显示/隐藏学生注册字段"""
        nonlocal selected_role_index
        # SegmentedButton on_change 的 selected 是列表
        selected_role_index = 0 if 'admin' in (e.control.selected or []) else 1
        if student_fields.current and confirm_field.current:
            if selected_role_index == 1:  # 医学生
                student_fields.current.visible = is_registering['value']
                confirm_field.current.visible = is_registering['value']
            else:
                student_fields.current.visible = False
                confirm_field.current.visible = False
            student_fields.current.update()
            confirm_field.current.update()

    def toggle_mode(e):
        """切换登录/注册模式"""
        is_registering['value'] = not is_registering['value']
        register_link = e.control

        if is_registering['value']:
            register_link.value = "已有账号？去登录"
            if confirm_field.current:
                confirm_field.current.visible = True
                confirm_field.current.update()
            # 检查是否选了学生角色
            if student_fields.current:
                if selected_role_index == 1:
                    student_fields.current.visible = True
                student_fields.current.update()
        else:
            register_link.value = "没有账号？去注册"
            if confirm_field.current:
                confirm_field.current.visible = False
                confirm_field.current.update()
            if student_fields.current:
                student_fields.current.visible = False
                student_fields.current.update()

        # 切换按钮文字
        submit_btn = page.get_control('submit_btn')
        if submit_btn:
            submit_btn.text = '注 册' if is_registering['value'] else '登 录'
            submit_btn.update()

        if error_text.current:
            error_text.current.value = ''
            error_text.current.update()

    def on_submit(e):
        """提交登录/注册"""
        username = username_field.current.value.strip() if username_field.current else ''
        password = password_field.current.value if password_field.current else ''

        if is_registering['value']:
            # 注册模式
            role = 'student' if selected_role_index == 1 else 'admin'
            confirm_pwd = confirm_password_field.current.value if confirm_password_field.current else ''

            if not username or not password:
                if error_text.current:
                    error_text.current.value = '请填写所有必填项'
                    error_text.current.update()
                return

            if password != confirm_pwd:
                if error_text.current:
                    error_text.current.value = '两次输入的密码不一致'
                    error_text.current.update()
                return

            real_name = real_name_field.current.value.strip() if real_name_field.current else None
            class_name = class_name_field.current.value.strip() if class_name_field.current else None

            result = register_user(
                username=username,
                password=password,
                role=role,
                real_name=real_name,
                class_name=class_name,
                must_change_password=1 if role == 'student' else 0
            )

            if result['success']:
                page.session.store.set('user', {
                    'id': result['user_id'],
                    'username': username,
                    'role': role,
                    'real_name': real_name,
                    'class_name': class_name,
                    'must_change_password': True
                })
                navigation.after_login(page)
            else:
                if error_text.current:
                    error_text.current.value = result['message']
                    error_text.current.update()
        else:
            # 登录模式
            result = login(username, password)
            if result['success']:
                page.session.store.set('user', result['user'])
                navigation.after_login(page)
            else:
                if error_text.current:
                    error_text.current.value = result['message']
                    error_text.current.update()

    # --- 构建 UI ---
    header = ft.Container(
        content=ft.Column([
            ft.Text('医学生伦理调查研究系统', size=28, weight=ft.FontWeight.BOLD, color='white'),
            ft.Text('Medical Ethics Survey System', size=14, color='rgba(255,255,255,0.8)'),
        ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=['#1565C0', '#42A5F5', '#1976D2']
        ),
        padding=ft.Padding(20, 50, 20, 50),
        alignment=ft.Alignment.CENTER,
    )

    role_tabs = ft.SegmentedButton(
        on_change=on_role_change,
        selected=['admin'],
        segments=[
            ft.Segment(
                value='admin',
                label=ft.Text('管理员'),
                icon=ft.Icon(ft.Icons.ADMIN_PANEL_SETTINGS),
            ),
            ft.Segment(
                value='student',
                label=ft.Text('医学生'),
                icon=ft.Icon(ft.Icons.SCHOOL),
            ),
        ],
    )

    error_label = ft.Text(
        ref=error_text,
        value='',
        color='#FF5252',
        size=13,
        text_align=ft.TextAlign.CENTER,
    )

    student_extra_fields = ft.Column(
        ref=student_fields,
        visible=False,
        controls=[
            ft.TextField(
                ref=real_name_field,
                label='姓名',
                prefix_icon=ft.Icons.PERSON,
                border_color='#BBDEFB',
                focused_border_color='#1976D2',
            ),
            ft.TextField(
                ref=class_name_field,
                label='班级',
                prefix_icon=ft.Icons.CLASS_,
                border_color='#BBDEFB',
                focused_border_color='#1976D2',
            ),
        ],
        spacing=12,
    )

    confirm_pwd_field = ft.Column(
        ref=confirm_field,
        visible=False,
        controls=[
            ft.TextField(
                ref=confirm_password_field,
                label='确认密码',
                password=True,
                can_reveal_password=True,
                prefix_icon=ft.Icons.LOCK_OUTLINE,
                border_color='#BBDEFB',
                focused_border_color='#1976D2',
            ),
        ],
        spacing=12,
    )

    submit_btn = ft.ElevatedButton(
        key='submit_btn',
        content='登 录',
        on_click=on_submit,
        style=ft.ButtonStyle(
            bgcolor='#1976D2',
            color='white',
            padding=ft.Padding(0, 15, 0, 15),
            shape=ft.RoundedRectangleBorder(radius=8),
        ),
        width=float('inf'),
    )

    login_card = ft.Container(
        content=ft.Column([
            ft.Row([role_tabs]),
            ft.Divider(height=10, color='transparent'),
            ft.TextField(
                ref=username_field,
                label='用户名',
                prefix_icon=ft.Icons.PERSON_OUTLINE,
                border_color='#BBDEFB',
                focused_border_color='#1976D2',
            ),
            ft.TextField(
                ref=password_field,
                label='密码',
                password=True,
                can_reveal_password=True,
                prefix_icon=ft.Icons.LOCK_OUTLINE,
                border_color='#BBDEFB',
                focused_border_color='#1976D2',
            ),
            confirm_pwd_field,
            student_extra_fields,
            error_label,
            ft.Divider(height=5, color='transparent'),
            submit_btn,
        ], spacing=12),
        bgcolor='white',
        border_radius=16,
        padding=30,
        shadow=ft.BoxShadow(
            spread_radius=1,
            blur_radius=20,
            color='#00000020',
        ),
    )

    version_label = ft.Text(
        'v1.0 | 医学生伦理调查研究系统 © 2026',
        size=11,
        color='#9E9E9E',
        text_align=ft.TextAlign.CENTER,
    )

    # 延迟刷新 SegmentedButton，修复首次加载时中文文字宽度计算不准确的问题
    async def _fix_segmented_button():
        await asyncio.sleep(0.05)
        # 延迟期间用户可能已快速登录、页面被切换，控件已脱离页面树，
        # 此时直接 update 会抛 "Control must be added to the page first"，需兜底
        try:
            if role_tabs.parent is not None:
                role_tabs.update()
        except Exception:
            pass

    page.run_task(_fix_segmented_button)

    return [
        ft.Container(
            content=ft.Column([
                header,
                ft.Container(
                    content=ft.Column([
                        login_card,
                        version_label,
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=16),
                    padding=ft.Padding(0, 30, 0, 30),
                    expand=True,
                ),
            ], spacing=0),
            bgcolor='#F5F7FA',
            expand=True,
        )
    ]


# 导航辅助函数，在 main.py 中赋值
class _Navigation:
    def after_login(self, page: ft.Page):
        """登录/注册成功后的导航"""
        pass


navigation = _Navigation()
