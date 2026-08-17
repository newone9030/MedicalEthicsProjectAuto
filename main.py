"""
医学生伦理调查研究系统 - 主入口
基于 Flet 框架，支持 Web / iOS / Android 三端
"""

import flet as ft
from app.config import TASK_STATUS, THEME_OPTIONS
from app.db import test_connection, close_db
from app.auth import login_view
from app.case.case_service import get_case_count
from app.task.task_service import (get_background_task, get_task,
                                    get_active_task_for_student, get_active_tasks_for_student)
from app.response.response_service import is_background_completed, get_submission_status
from app.student.background_survey_view import build_background_survey_view
from app.case.case_manager_view import build_case_list_view, build_case_editor_view
from app.task.task_service import get_task_count, get_active_task_count, auto_update_task_statuses
from app.task.task_manager_view import build_task_list_view, build_task_editor_view
from app.student.student_dashboard_view import build_student_dashboard
from app.student.survey_taker_view import build_survey_taker_view
from app.analytics.analytics_view import build_analytics_view
from app.analytics.export import build_export_buttons
from app.analytics.data_export_view import build_data_export_view
from app.analytics.data_import_view import build_data_import_view
from app.response.response_service import get_response_count
from app.analytics.analytics_service import get_student_count
from app.auth.account_manager_view import build_account_manager_view
from app.auth.feedback_task_manager_view import build_feedback_task_list_view, build_feedback_task_editor
from app.student.feedback_view import build_feedback_view
from app.student.feedback_service import has_feedback


# ============================================
# 导航回调设置
# ============================================
login_view.navigation.after_login = lambda page: _navigate(page, 'dashboard')


def _navigate(page: ft.Page, target: str, **kwargs):
    """统一导航方法 - 仅通过 page.go() 触发路由，让 route_change 处理视图"""
    user = page.session.store.get('user')
    print(f'[NAV] _navigate called, target={target}, user={user}')
    if not user:
        page.go('/login')
        return

    if target == 'dashboard':
        if user['role'] == 'admin':
            print('[NAV] going to /admin/dashboard')
            page.go('/admin/dashboard')
        else:
            # 学生需先通过知情同意确认
            if page.session.store.get('student_consented'):
                print('[NAV] going to /student/dashboard')
                page.go('/student/dashboard')
            else:
                print('[NAV] going to /student/consent')
                page.go('/student/consent')
    else:
        # 将额外参数暂存到 session，供 route_change 使用
        page.session.store.set('_nav_params', kwargs)
        # 确保路径以 / 开头
        route = target if target.startswith('/') else '/' + target
        page.go(route)


def _build_view(route: str, page: ft.Page, **kwargs):
    """构建视图"""
    user = page.session.store.get('user')

    # 从 session 读取导航参数（由 _navigate 暂存）
    nav_params = page.session.store.get('_nav_params')
    if nav_params and not kwargs:
        kwargs = nav_params
        page.session.store.remove('_nav_params')

    if route == '/login':
        return ft.View(
            route='/login',
            scroll=ft.ScrollMode.AUTO,
            controls=login_view.build_login_view(page),
            padding=0,
        )

    # 鉴权检查
    if not user:
        return ft.View(
            route='/login',
            scroll=ft.ScrollMode.AUTO,
            controls=login_view.build_login_view(page),
            padding=0,
        )

    # 管理员视图
    if route == '/admin/dashboard':
        return _build_admin_dashboard(page)

    elif route == '/admin/cases':
        return _build_case_management(page)

    elif route == '/admin/case/editor':
        case_id = kwargs.get('case_id')
        return _build_case_editor(page, case_id)

    elif route == '/admin/tasks':
        return _build_task_management(page)

    elif route == '/admin/task/editor':
        task_id = kwargs.get('task_id')
        return _build_task_editor(page, task_id)

    elif route == '/admin/analytics':
        return _build_admin_analytics(page)

    elif route == '/admin/accounts':
        return _build_account_management(page)

    elif route == '/admin/feedback/tasks':
        return _build_feedback_task_list(page)

    elif route == '/admin/feedback/task/editor':
        page_category = kwargs.get('page_category')
        task_id = kwargs.get('task_id')
        return _build_feedback_task_editor(page, page_category, task_id)

    elif route == '/admin/data-export':
        return _build_admin_data_export(page)

    elif route == '/admin/data-import':
        return _build_admin_data_import(page)

    # 学生视图
    elif route == '/student/consent':
        return _build_consent_page(page)

    elif route == '/student/background':
        return _build_background_page(page)

    elif route == '/student/dashboard':
        return _build_student_page(page)

    elif route == '/student/survey':
        task_id = kwargs.get('task_id')
        readonly = kwargs.get('readonly', False)
        return _build_survey_page(page, task_id, readonly)

    elif route == '/student/feedback':
        return _build_student_feedback_page(page)

    else:
        return ft.View(
            route=route,
            scroll=ft.ScrollMode.AUTO,
            controls=[ft.Text(f'页面不存在: {route}', color='#FF5252')],
        )


# ============================================
# 管理员仪表盘
# ============================================
def _build_admin_dashboard(page: ft.Page) -> ft.View:
    """管理员仪表盘"""
    auto_update_task_statuses()

    case_count = get_case_count()
    task_count = get_task_count()
    active_count = get_active_task_count()
    response_count = get_response_count()
    student_count = get_student_count()

    def navigate(target):
        _navigate(page, target)

    def on_logout(e):
        _logout(page)

    header = ft.Container(
        content=ft.Row([
            ft.Row([
                ft.Icon(ft.Icons.LOCAL_HOSPITAL, color='white', size=28),
                ft.Text('医学生伦理调查', size=16, weight=ft.FontWeight.BOLD, color='white',
                        overflow=ft.TextOverflow.ELLIPSIS, no_wrap=True),
            ], spacing=10, expand=True),
            ft.Row([
                ft.Text(f'管理员: {(page.session.store.get("user") or {}).get("username", "")}', size=13,
                        color='rgba(255,255,255,0.9)', overflow=ft.TextOverflow.ELLIPSIS, no_wrap=True),
                ft.IconButton(icon=ft.Icons.LOGOUT, icon_color='white', on_click=on_logout,
                             icon_size=20, tooltip='退出登录'),
            ], spacing=5, alignment=ft.MainAxisAlignment.END),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=['#1565C0', '#1976D2']
        ),
        padding=ft.Padding(24, 16, 24, 16),
    )

    stats = ft.Row([
        _stat_card('案例总数', case_count, ft.Icons.LIBRARY_BOOKS, '#1565C0'),
        _stat_card('任务总数', task_count, ft.Icons.ASSIGNMENT, '#1976D2'),
        _stat_card('进行中', active_count, ft.Icons.PLAY_CIRCLE, '#4CAF50'),
        _stat_card('总提交', response_count, ft.Icons.CHECK_CIRCLE, '#FF9800'),
        _stat_card('学生总数', student_count, ft.Icons.SCHOOL, '#9C27B0'),
    ], spacing=16, wrap=True)

    entries = ft.Row([
        _entry_card('案例管理', '创建和维护伦理案例库，添加单选、多选、开放题', ft.Icons.LIBRARY_BOOKS,
                     lambda e: navigate('admin/cases')),
        _entry_card('任务管理', '创建调研任务，设置时间窗口，关联案例', ft.Icons.ASSIGNMENT,
                     lambda e: navigate('admin/tasks')),
        _entry_card('数据分析', '查看作答统计，生成图表，导出数据', ft.Icons.ANALYTICS,
                     lambda e: navigate('admin/analytics')),
        _entry_card('账号管理', '创建医学生账号，管理账号状态，重置密码', ft.Icons.MANAGE_ACCOUNTS,
                     lambda e: navigate('admin/accounts')),
        _entry_card('反馈任务维护', '创建和维护预测试反馈任务，管理题目和选项', ft.Icons.FEEDBACK,
                     lambda e: navigate('admin/feedback/tasks')),
        _entry_card('数据导出', '导出基础数据和学生数据为 Excel 文件', ft.Icons.FILE_DOWNLOAD,
                     lambda e: navigate('admin/data-export')),
        _entry_card('数据导入', '从导出的 Excel 中选择工作表恢复数据', ft.Icons.IMPORT_EXPORT,
                     lambda e: navigate('admin/data-import')),
    ], spacing=16, wrap=True)

    return ft.View(
        route='/admin/dashboard',
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Container(
                content=ft.Column([
                    header,
                    ft.Container(
                        content=ft.Column([
                            ft.Text('概览', size=18, weight=ft.FontWeight.W_500, color='#212121'),
                            ft.Divider(height=10, color='transparent'),
                            stats,
                            ft.Divider(height=25, color='transparent'),
                            ft.Text('功能入口', size=18, weight=ft.FontWeight.W_500, color='#212121'),
                            ft.Divider(height=10, color='transparent'),
                            entries,
                        ], spacing=0),
                        padding=24,
                        expand=True,
                    ),
                ], spacing=0),
                bgcolor='#F5F7FA',
                expand=True,
            ),
        ],
        padding=0,
    )


def _stat_card(title: str, value, icon, color: str) -> ft.Container:
    return ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Icon(icon, color=color, size=24),
                ft.Container(expand=True),
                ft.Text(str(value), size=28, weight=ft.FontWeight.BOLD, color='#212121'),
            ]),
            ft.Text(title, size=12, color='#757575'),
        ], spacing=4),
        bgcolor='white',
        border_radius=12,
        padding=ft.Padding(20, 16, 20, 16),
        shadow=ft.BoxShadow(spread_radius=0.5, blur_radius=8, color='#00000015'),
        width=175,
    )


def _entry_card(title: str, desc: str, icon, on_click) -> ft.Container:
    return ft.Container(
        content=ft.Column([
            ft.Icon(icon, color='#1976D2', size=40),
            ft.Text(title, size=16, weight=ft.FontWeight.BOLD, color='#212121'),
            ft.Text(desc, size=12, color='#757575', text_align=ft.TextAlign.CENTER),
            ft.Divider(height=10, color='transparent'),
            ft.ElevatedButton(
                '进入',
                on_click=on_click,
                style=ft.ButtonStyle(bgcolor='#1976D2', color='white', shape=ft.RoundedRectangleBorder(radius=8)),
            ),
        ], spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        bgcolor='white',
        border_radius=16,
        padding=24,
        shadow=ft.BoxShadow(spread_radius=0.5, blur_radius=10, color='#00000015'),
        width=260,
        height=200,
        alignment=ft.Alignment.CENTER,
        on_click=on_click,
    )


# ============================================
# 案例管理页
# ============================================
def _build_case_management(page: ft.Page) -> ft.View:
    def on_create(case_id, page):
        _navigate(page, 'admin/case/editor', case_id=None)

    def on_edit(case_id, page):
        _navigate(page, 'admin/case/editor', case_id=case_id)

    def go_back():
        _navigate(page, 'dashboard')

    # 读取从编辑页传来的保存成功消息
    save_msg = page.session.store.get('_case_save_message')
    if save_msg:
        page.session.store.remove('_case_save_message')
        page.snack_bar = ft.SnackBar(ft.Text(save_msg), bgcolor='#4CAF50')
        page.snack_bar.open = True

    return ft.View(
        route='/admin/cases',
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=lambda e: go_back(),
                                     icon_color='#1976D2', tooltip='返回仪表盘', icon_size=22),
                        ft.Text('案例管理', size=20, weight=ft.FontWeight.BOLD, color='#212121'),
                    ], spacing=8),
                    build_case_list_view(page, on_create, on_edit),
                ], expand=True, spacing=16),
                padding=24,
                expand=True,
            ),
        ],
        bgcolor='#F5F7FA',
    )


def _build_case_editor(page: ft.Page, case_id: int = None) -> ft.View:
    def go_back():
        _navigate(page, 'admin/cases')

    return ft.View(
        route='/admin/case/editor',
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Container(
                content=ft.Column(build_case_editor_view(page, case_id, on_back=go_back)),
                padding=24,
                expand=True,
            ),
        ],
        bgcolor='#F5F7FA',
    )


# ============================================
# 任务管理页
# ============================================
def _build_task_management(page: ft.Page) -> ft.View:
    def on_create(page):
        _navigate(page, 'admin/task/editor', task_id=None)

    def on_edit(task_id, page):
        _navigate(page, 'admin/task/editor', task_id=task_id)

    def go_back():
        _navigate(page, 'dashboard')

    return ft.View(
        route='/admin/tasks',
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=lambda e: go_back(),
                                     icon_color='#1976D2', tooltip='返回仪表盘', icon_size=22),
                        ft.Text('任务管理', size=20, weight=ft.FontWeight.BOLD, color='#212121'),
                    ], spacing=8),
                    build_task_list_view(page, on_create, on_edit),
                ], expand=True, spacing=16),
                padding=24,
                expand=True,
            ),
        ],
        bgcolor='#F5F7FA',
    )


def _build_task_editor(page: ft.Page, task_id: int = None) -> ft.View:
    def go_back():
        _navigate(page, 'admin/tasks')

    return ft.View(
        route='/admin/task/editor',
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Container(
                content=ft.Column(build_task_editor_view(page, task_id, on_back=go_back)),
                padding=24,
                expand=True,
            ),
        ],
        bgcolor='#F5F7FA',
    )


# ============================================
# 数据分析页
# ============================================
def _build_admin_analytics(page: ft.Page) -> ft.View:
    def go_back():
        _navigate(page, 'dashboard')

    return ft.View(
        route='/admin/analytics',
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Container(
                content=ft.Column(build_analytics_view(page, on_back=go_back)),
                padding=24,
                expand=True,
            ),
        ],
        bgcolor='#F5F7FA',
    )


# ============================================
# 数据导出页
# ============================================
def _build_admin_data_export(page: ft.Page) -> ft.View:
    def go_back():
        _navigate(page, 'dashboard')

    return ft.View(
        route='/admin/data-export',
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Container(
                content=ft.Column(build_data_export_view(page, on_back=go_back)),
                padding=24,
                expand=True,
            ),
        ],
        bgcolor='#F5F7FA',
    )


# ============================================
# 数据导入页
# ============================================
def _build_admin_data_import(page: ft.Page) -> ft.View:
    def go_back():
        _navigate(page, 'dashboard')

    return ft.View(
        route='/admin/data-import',
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Container(
                content=ft.Column(build_data_import_view(page, on_back=go_back)),
                padding=24,
                expand=True,
            ),
        ],
        bgcolor='#F5F7FA',
    )


# ============================================
# 账号管理页
# ============================================
def _build_account_management(page: ft.Page) -> ft.View:
    def go_back():
        _navigate(page, 'dashboard')

    return ft.View(
        route='/admin/accounts',
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Container(
                content=ft.Column(build_account_manager_view(page, on_back=go_back)),
                padding=24,
                expand=True,
            ),
        ],
        bgcolor='#F5F7FA',
    )


# ============================================
# 学生知情同意页
def _placeholder_view() -> ft.View:
    """空过渡视图，用于 page.go() 重定向间隙显示"""
    return ft.View(
        route='/placeholder',
        controls=[
            ft.Container(
                content=ft.ProgressRing(width=32, height=32, color='#1976D2'),
                expand=True,
                alignment=ft.Alignment(0, 0),
                bgcolor='#F5F7FA',
            ),
        ],
        padding=0,
    )


# ============================================
def _build_consent_page(page: ft.Page) -> ft.View:
    """学生知情同意页，必须勾选确认后才能进入系统"""

    def on_logout(e):
        _logout(page)

    consent_checkbox_control = ft.Checkbox(
        label='我已阅读上述说明，并愿意继续进入本研究系统',
        value=False,
        fill_color='#1976D2',
    )
    consent_checkbox = ft.Container(
        content=consent_checkbox_control,
        # 整体向左移动两个中文字符宽度
        margin=ft.Margin(-32, 0, 0, 0),
    )

    continue_btn = ft.ElevatedButton(
        content='继续进入',
        disabled=False,
        icon=ft.Icons.ARROW_FORWARD,
        style=ft.ButtonStyle(
            bgcolor='#1976D2', color='white',
            shape=ft.RoundedRectangleBorder(radius=8),
        ),
    )

    def on_continue(e):
        if not consent_checkbox_control.value:
            snack = ft.SnackBar(
                ft.Text('请先勾选"我已阅读上述说明"后再继续进入'),
                bgcolor='#FF5252',
            )
            page.overlay.append(snack)
            snack.open = True
            page.update()
            return
        page.session.store.set('student_consented', True)
        page.go('/student/dashboard')

    continue_btn.on_click = on_continue

    header = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.LOCAL_HOSPITAL, color='white', size=28),
            ft.Text('医学生伦理调查研究系统', size=22, weight=ft.FontWeight.BOLD, color='white'),
        ], spacing=10),
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=['#1565C0', '#1976D2']
        ),
        padding=ft.Padding(24, 40, 24, 40),
    )

    content_card = ft.Container(
        content=ft.Column([
            ft.Text('研究知情同意书', size=22, weight=ft.FontWeight.BOLD, color='#1565C0'),
            ft.Divider(height=16, color='#E0E0E0'),
            ft.Text(
                '您已接受研究人员提供的研究说明，并已知情同意参加本研究。\n\n'
                '本系统仅用于研究资料采集和管理，研究结果将用于优化医患沟通相关课程教学。\n\n'
                '非常感谢您参与本次研究！',
                size=16, color='#424242',
            ),
            ft.Divider(height=24, color='transparent'),
            consent_checkbox,
            ft.Divider(height=20, color='transparent'),
            ft.Row([
                ft.OutlinedButton(
                    content='退出登录',
                    on_click=on_logout,
                    icon=ft.Icons.LOGOUT,
                    style=ft.ButtonStyle(color='#757575'),
                ),
                continue_btn,
            ], alignment=ft.MainAxisAlignment.END, spacing=12),
        ], spacing=0),
        bgcolor='white',
        border_radius=16,
        padding=30,
        shadow=ft.BoxShadow(spread_radius=1, blur_radius=20, color='#00000020'),
    )

    return ft.View(
        route='/student/consent',
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Container(
                content=ft.Column([
                    header,
                    ft.Container(
                        content=content_card,
                        padding=ft.Padding(20, 30, 20, 30),
                    ),
                ], spacing=0),
                bgcolor='#F5F7FA',
                expand=True,
            ),
        ],
        padding=0,
    )


# ============================================
# 学生背景资料问卷页
# ============================================
def _build_background_page(page: ft.Page) -> ft.View:
    """背景资料问卷页，学生必须完成才能进入仪表盘"""

    user = page.session.store.get('user') or {}

    # 检查是否有背景资料任务
    bg_task = get_background_task()
    if not bg_task:
        # 无背景资料任务，直接跳转仪表盘
        page.session.store.set('background_completed', True)
        page.go('/student/dashboard')
        return _placeholder_view()

    task = get_task(bg_task['id'])
    if not task or not task.get('cases'):
        # 背景资料任务无案例，直接跳转
        page.session.store.set('background_completed', True)
        page.go('/student/dashboard')
        return _placeholder_view()

    # 检查是否已完成
    if is_background_completed(bg_task['id'], user['id']):
        page.session.store.set('background_completed', True)
        page.go('/student/dashboard')
        return _placeholder_view()

    def go_dashboard():
        page.session.store.set('background_completed', True)
        page.update()
        page.go('/student/dashboard')

    def do_logout():
        _logout(page)

    return build_background_survey_view(
        page=page,
        on_navigate_dashboard=go_dashboard,
        on_logout=do_logout,
        student_id=user.get('id'),
        student_name=user.get('real_name') or user.get('username', ''),
        task=task,
    )


# ============================================
# 学生仪表盘
# ============================================
def _test_user_requires_feedback(page: ft.Page) -> bool:
    """
    测试用户是否处于"必须完成反馈"状态：
    测试用户 + 背景已完成 + 所有活跃任务已提交 + 未提交反馈
    """
    user = page.session.store.get('user') or {}
    if user.get('user_type') != 'test':
        return False
    student_id = user.get('id')
    if has_feedback(student_id):
        return False
    bg_task = get_background_task()
    if bg_task and not is_background_completed(bg_task['id'], student_id):
        return False
    tasks = get_active_tasks_for_student(student_id)
    if not tasks:
        # 无活跃任务（任务已关闭/尚未发布）：反馈页无法加载，不强制
        return False
    for task in tasks:
        statuses = get_submission_status(task['id'], student_id)
        if not statuses or not all(s == 'submitted' for s in statuses.values()):
            return False
    return True


def _show_feedback_required_dialog(page: ft.Page):
    """测试用户任务已作答完但反馈未完成：阻止退出，引导先完成反馈"""

    def _close_dlg(e):
        dlg.open = False
        page.update()

    def _go_feedback(e):
        dlg.open = False
        page.update()
        _navigate(page, 'student/feedback')

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text('请先完成反馈任务', size=16, weight=ft.FontWeight.BOLD, color='#E65100'),
        content=ft.Text(
            '您已完成所有任务作答。\n\n'
            '请先完成预测试反馈任务，反馈完成后才能退出系统。',
            size=14, color='#424242',
        ),
        actions=[
            ft.TextButton('暂不退出', on_click=_close_dlg),
            ft.ElevatedButton('去填写反馈', on_click=_go_feedback,
                              style=ft.ButtonStyle(bgcolor='#FF9800', color='white')),
        ],
    )
    page.show_dialog(dlg)


def _build_student_page(page: ft.Page) -> ft.View:
    def on_enter_task(task_id, page, readonly=False):
        _navigate(page, 'student/survey', task_id=task_id, readonly=readonly)

    def on_logout(e):
        # 测试用户：任务已作答完但反馈未完成 → 必须先完成反馈才能退出系统
        if _test_user_requires_feedback(page):
            _show_feedback_required_dialog(page)
            return
        _logout(page)

    user = page.session.store.get('user') or {}

    header = ft.Container(
        content=ft.Row([
            ft.Row([
                ft.Icon(ft.Icons.LOCAL_HOSPITAL, color='white', size=22),
                ft.Text('医学生伦理调研', size=17, weight=ft.FontWeight.BOLD, color='white',
                        overflow=ft.TextOverflow.ELLIPSIS, no_wrap=True),
            ], spacing=8, expand=True),
            ft.Row([
                ft.Text(f'{user.get("real_name") or user["username"]}', size=15,
                        color='rgba(255,255,255,0.9)', overflow=ft.TextOverflow.ELLIPSIS, no_wrap=True),
                ft.IconButton(icon=ft.Icons.LOGOUT, icon_color='white', on_click=on_logout,
                             icon_size=20, tooltip='退出登录'),
            ], spacing=5, alignment=ft.MainAxisAlignment.END),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=['#1565C0', '#1976D2']
        ),
        padding=ft.Padding(20, 12, 20, 12),
    )

    return ft.View(
        route='/student/dashboard',
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Container(
                content=ft.Column([
                    header,
                    ft.Container(
                        content=ft.Column(build_student_dashboard(page, on_enter_task)),
                        padding=24,
                        expand=True,
                    ),
                ], spacing=0),
                bgcolor='#F5F7FA',
                expand=True,
            ),
        ],
        padding=0,
    )


def _build_survey_page(page: ft.Page, task_id: int, readonly: bool = False) -> ft.View:
    def go_back():
        _navigate(page, 'dashboard')

    compact = bool(page.width) and page.width < 600
    return ft.View(
        route='/student/survey',
        scroll=ft.ScrollMode.AUTO,
        padding=0,
        controls=[
            ft.Container(
                content=ft.Column(build_survey_taker_view(page, task_id, on_back=go_back, readonly=readonly)),
                padding=12 if compact else 24,
                expand=True,
            ),
        ],
        bgcolor='#F5F7FA',
    )


# ============================================
# 管理员反馈任务维护页
# ============================================
def _build_feedback_task_list(page: ft.Page) -> ft.View:
    def go_back():
        _navigate(page, 'dashboard')

    def on_create_task(e, page_category: str, task_id: int = None):
        _navigate(page, 'admin/feedback/task/editor',
                  page_category=page_category, task_id=task_id)

    return ft.View(
        route='/admin/feedback/tasks',
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Container(
                content=ft.Column(
                    build_feedback_task_list_view(page, on_back=go_back, on_create_task=on_create_task),
                    expand=True, spacing=16,
                ),
                padding=24,
                expand=True,
            ),
        ],
        bgcolor='#F5F7FA',
    )


def _build_feedback_task_editor(page: ft.Page, page_category: str = None,
                                task_id: int = None) -> ft.View:
    nav_params = page.session.store.get('_nav_params')
    if nav_params:
        page_category = nav_params.get('page_category') or page_category
        task_id = nav_params.get('task_id') or task_id
        page.session.store.remove('_nav_params')

    def go_back():
        _navigate(page, 'admin/feedback/tasks')

    return ft.View(
        route='/admin/feedback/task/editor',
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Container(
                content=ft.Column(
                    build_feedback_task_editor(page, page_category or 'case', task_id, on_back=go_back),
                ),
                padding=24,
                expand=True,
            ),
        ],
        bgcolor='#F5F7FA',
    )


# ============================================
# 学生反馈页
# ============================================
def _build_student_feedback_page(page: ft.Page) -> ft.View:
    user = page.session.store.get('user') or {}
    student_id = user.get('id')

    # 仅测试用户可填写反馈任务
    if user.get('user_type') != 'test':
        return ft.View(
            route='/student/feedback',
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.LOCK_OUTLINE, size=64, color='#FF5252'),
                        ft.Text('无权访问', size=18, weight=ft.FontWeight.W_500, color='#757575'),
                        ft.Text('反馈任务仅对测试用户开放', size=14, color='#BDBDBD'),
                        ft.ElevatedButton(
                            content='返回仪表盘',
                            on_click=lambda e: _navigate(page, 'dashboard'),
                            icon=ft.Icons.ARROW_BACK,
                        ),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
                    padding=60,
                ),
            ],
            bgcolor='#F5F7FA',
        )

    # 测试用户必须完成所有已开放任务后才能填写反馈
    tasks = get_active_tasks_for_student(student_id)
    unfinished = []
    for task in tasks:
        statuses = get_submission_status(task['id'], student_id)
        if not statuses or not all(s == 'submitted' for s in statuses.values()):
            unfinished.append(task['name'])
    if unfinished:
        return ft.View(
            route='/student/feedback',
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.PENDING_ACTIONS, size=64, color='#FF9800'),
                        ft.Text('请先完成所有任务', size=18, weight=ft.FontWeight.W_500, color='#E65100'),
                        ft.Text('反馈任务需在完成所有已开放任务后才能填写。\n'
                                f'尚未完成：{"、".join(unfinished[:3])}'
                                + (' 等' if len(unfinished) > 3 else ''),
                                size=14, color='#757575', text_align=ft.TextAlign.CENTER),
                        ft.ElevatedButton(
                            content='返回仪表盘',
                            on_click=lambda e: _navigate(page, 'dashboard'),
                            icon=ft.Icons.ARROW_BACK,
                        ),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
                    padding=60,
                ),
            ],
            bgcolor='#F5F7FA',
        )

    # 获取当前活跃任务（用于查找已回答题目）
    from app.task.task_service import get_active_task_for_student

    active_task = get_active_task_for_student(student_id)

    if not active_task:
        return ft.View(
            route='/student/feedback',
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.ERROR_OUTLINE, size=64, color='#FF9800'),
                        ft.Text('无法加载反馈', size=18, weight=ft.FontWeight.W_500, color='#757575'),
                        ft.Text('未找到活跃任务', size=14, color='#BDBDBD'),
                        ft.ElevatedButton(
                            content='返回仪表盘',
                            on_click=lambda e: _navigate(page, 'dashboard'),
                            icon=ft.Icons.ARROW_BACK,
                        ),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
                    padding=60,
                ),
            ],
            bgcolor='#F5F7FA',
        )

    def on_feedback_complete():
        """反馈完成后退出系统"""
        _logout(page)

    return ft.View(
        route='/student/feedback',
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Container(
                content=ft.Column(
                    build_feedback_view(page, student_id, active_task['id'],
                                        on_complete=on_feedback_complete),
                    expand=True,
                ),
                padding=24,
                expand=True,
            ),
        ],
        bgcolor='#F5F7FA',
    )


# ============================================
# 退出登录
# ============================================
def _logout(page: ft.Page):
    page.session.store.clear()
    page.views.clear()
    page.views.append(_build_view('/login', page))
    page.go('/login')


# ============================================
# 应用入口
# ============================================
def main(page: ft.Page):
    """Flet 应用主入口"""
    # 页面配置
    page.title = '医学生伦理调查研究系统'
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = '#F5F7FA'
    page.theme = ft.Theme(
        color_scheme=ft.ColorScheme(
            primary='#1976D2',
            primary_container='#BBDEFB',
            secondary='#1565C0',
            error='#FF5252',
        ),
        font_family='Roboto',
    )

    # 响应式窗口尺寸
    page.window_min_width = 800
    page.window_min_height = 600
    page.window_width = 1200
    page.window_height = 800

    # 启动时尝试连接数据库
    try:
        test_connection()
        # 连接成功：暂存提示标记，等首个视图渲染完成后由 route_change 弹出 SnackBar
        page.session.store.set('_db_connected', True)
    except Exception as e:
        page.add(ft.Text(f'数据库连接失败: {e}', color='#FF5252'))
        return

    # 路由变化处理
    def route_change(e):
        route = getattr(e, 'route', None) or page.route or '/login'
        print(f'[ROUTE] route_change fired, route={route}')
        if not route or route == '/':
            route = '/login'

        # 已登录用户不能通过浏览器返回键回到登录页，重定向到 dashboard 或知情同意页
        user = page.session.store.get('user')
        if route == '/login' and user:
            print('[ROUTE] 已登录用户尝试访问 /login，重定向到 dashboard')
            if user['role'] == 'admin':
                route = '/admin/dashboard'
            elif page.session.store.get('student_consented'):
                route = '/student/dashboard'
            else:
                route = '/student/consent'

        # 学生已同意但未完成背景资料 → 提示先完成背景资料（不再强制跳转，
        # 改为在 dashboard 上通过背景资料卡片引导填写）

        # 视图代际递增：旧视图的延迟加载/刷新调度检测到代际变化后立即停止，
        # 避免页面切换后旧 Timer 继续操作已移除的控件导致界面卡死
        page.session.store.set('_view_generation', (page.session.store.get('_view_generation') or 0) + 1)

        page.views.clear()
        try:
            view = _build_view(route, page)
            if view:
                print(f'[ROUTE] built view type={type(view).__name__}, controls count={len(view.controls)}')
                page.views.append(view)
        except Exception as ex:
            import traceback
            traceback.print_exc()
            print(f'[ROUTE] ERROR building view: {ex}')
            page.views.append(ft.View(
                route=route,
                controls=[ft.Container(
                    content=ft.Text(f'页面加载错误: {ex}', color='red', size=16),
                    padding=24
                )]
            ))
        page.update()
        print(f'[ROUTE] page updated, views count={len(page.views)}')

        # 数据库连接成功提示：首次页面渲染完成后展示一次
        if page.session.store.get('_db_connected'):
            page.session.store.remove('_db_connected')
            snack = ft.SnackBar(ft.Text('数据库连接成功'), bgcolor='#4CAF50')
            page.overlay.append(snack)
            snack.open = True
            page.update()

    page.on_route_change = route_change

    # 阻止从 dashboard / 知情同意页 / 背景资料页通过返回手势回退到登录页
    def view_pop(e: ft.ViewPopEvent):
        if len(page.views) <= 1:
            return  # 没有可弹出的视图，阻止默认行为
        current_route = page.views[-1].route if page.views else ''
        if current_route in ('/student/consent', '/student/background'):
            return  # 阻止从关键页面通过返回键跳过
        page.views.pop()
        page.update()

    page.on_view_pop = view_pop

    # 窗口关闭清理
    def on_window_close(e):
        close_db()

    page.on_window_close = on_window_close

    # 初始路由
    page.go('/login')


import os
##mount_path = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "./data")
##DB_PATH = os.path.join(mount_path, "survey.db")

if __name__ == '__main__':
   ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=int(os.environ.get('PORT', 8000))
       , host='0.0.0.0',web_renderer=ft.WebRenderer.CANVAS_KIT)
    ##ft.app(target=main, view=ft.AppView.WEB_BROWSER)
