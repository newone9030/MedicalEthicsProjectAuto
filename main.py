"""
医学生伦理调查研究系统 - 主入口
基于 Flet 框架，支持 Web / iOS / Android 三端
"""

import flet as ft
from app.config import TASK_STATUS, THEME_OPTIONS
from app.db import test_connection, close_db
from app.auth import login_view
from app.case.case_service import get_case_count
from app.case.case_manager_view import build_case_list_view, build_case_editor_view
from app.task.task_service import get_task_count, get_active_task_count, auto_update_task_statuses
from app.task.task_manager_view import build_task_list_view, build_task_editor_view
from app.student.student_dashboard_view import build_student_dashboard
from app.student.survey_taker_view import build_survey_taker_view
from app.analytics.analytics_view import build_analytics_view
from app.analytics.export import build_export_buttons
from app.response.response_service import get_response_count
from app.analytics.analytics_service import get_student_count
from app.auth.account_manager_view import build_account_manager_view


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
            print('[NAV] going to /student/dashboard')
            page.go('/student/dashboard')
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

    # 学生视图
    elif route == '/student/dashboard':
        return _build_student_page(page)

    elif route == '/student/survey':
        task_id = kwargs.get('task_id')
        readonly = kwargs.get('readonly', False)
        return _build_survey_page(page, task_id, readonly)

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
# 学生仪表盘
# ============================================
def _build_student_page(page: ft.Page) -> ft.View:
    def on_enter_task(task_id, page, readonly=False):
        _navigate(page, 'student/survey', task_id=task_id, readonly=readonly)

    def on_logout(e):
        _logout(page)

    user = page.session.store.get('user') or {}

    header = ft.Container(
        content=ft.Row([
            ft.Row([
                ft.Icon(ft.Icons.LOCAL_HOSPITAL, color='white', size=22),
                ft.Text('医学生伦理调研', size=15, weight=ft.FontWeight.BOLD, color='white',
                        overflow=ft.TextOverflow.ELLIPSIS, no_wrap=True),
            ], spacing=8, expand=True),
            ft.Row([
                ft.Text(f'{user.get("real_name") or user["username"]}', size=13,
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

    return ft.View(
        route='/student/survey',
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Container(
                content=ft.Column(build_survey_taker_view(page, task_id, on_back=go_back, readonly=readonly)),
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
    except Exception as e:
        page.add(ft.Text(f'数据库连接失败: {e}', color='#FF5252'))
        return

    # 路由变化处理
    def route_change(e):
        route = getattr(e, 'route', None) or page.route or '/login'
        print(f'[ROUTE] route_change fired, route={route}')
        if not route or route == '/':
            route = '/login'

        # 已登录用户不能通过浏览器返回键回到登录页，重定向到 dashboard
        user = page.session.store.get('user')
        if route == '/login' and user:
            print('[ROUTE] 已登录用户尝试访问 /login，重定向到 dashboard')
            route = '/admin/dashboard' if user['role'] == 'admin' else '/student/dashboard'

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

    page.on_route_change = route_change

    # 阻止从 dashboard 通过返回手势回退到登录页
    def view_pop(e: ft.ViewPopEvent):
        if len(page.views) <= 1:
            return  # 没有可弹出的视图，阻止默认行为
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
mount_path = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "./data")
DB_PATH = os.path.join(mount_path, "survey.db")

if __name__ == '__main__':
    ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=int(os.environ.get('PORT', 8000))
           , host='0.0.0.0',web_renderer=ft.WebRenderer.CANVAS_KIT)
    