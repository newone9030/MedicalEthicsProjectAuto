"""
数据导出视图：管理员导出基础数据 / 学生数据 Excel

- 导出目录设置：手动输入路径并持久化保存
- 基础数据导出：案例、案例题目、任务、任务关联案例、反馈任务、反馈题目、
  反馈题目选项、反馈任务映射、账户信息
- 学生数据导出：背景资料答案、任务答案、反馈答案
"""

import asyncio
import os

import flet as ft

from app.analytics.data_export_service import (
    get_export_dir,
    set_export_dir,
    do_export,
)


def _snack(page: ft.Page, message: str, success: bool = True):
    """标准 SnackBar 提示"""
    snack = ft.SnackBar(
        content=ft.Text(message, color='white'),
        bgcolor='#4CAF50' if success else '#FF5252',
        duration=5000,
    )
    page.overlay.append(snack)
    snack.open = True
    page.update()


def build_data_export_view(page: ft.Page, on_back=None) -> list:
    """构建数据导出页面，返回控件列表（由调用方包裹进 View）"""

    dir_field = ft.TextField(
        label='导出目录',
        value=get_export_dir(),
        hint_text='请输入用于保存导出文件的本地目录路径',
        border_color='#BBDEFB',
        focused_border_color='#1976D2',
        prefix_icon=ft.Icons.FOLDER_OPEN,
        expand=True,
    )

    basic_desc = (
        '导出系统基础配置数据，包含 9 个工作表：\n'
        '案例、案例题目、任务、任务关联案例、反馈任务、反馈题目、'
        '反馈题目选项、反馈任务映射、账户信息（不含密码信息）。'
    )
    student_desc = (
        '导出学生作答数据，包含 3 个工作表：\n'
        '背景资料答案、任务答案、反馈答案。'
    )

    progress = ft.ProgressBar(visible=False)

    def do_save_dir(e):
        try:
            path = set_export_dir(dir_field.value)
            dir_field.value = path
            dir_field.update()
            _snack(page, f'导出目录已保存: {path}')
        except ValueError as ex:
            _snack(page, str(ex), success=False)

    def start_export(scope: str):
        """后台执行导出，避免阻塞 UI"""
        export_dir = dir_field.value.strip() if dir_field.value else get_export_dir()
        progress.visible = True
        progress.update()
        scope_cn = {'basic': '基础数据', 'student': '学生数据', 'all': '全部数据'}[scope]

        async def run():
            try:
                # 阻塞 IO 导出放到线程池执行，避免阻塞事件循环
                results = await asyncio.to_thread(do_export, scope, export_dir)
                progress.visible = False
                progress.update()
                _snack(page, f'{scope_cn}导出成功，共 {len(results)} 个文件，保存在:\n' + '\n'.join(
                    res['filepath'] for res in results), success=True)
            except Exception as ex:
                import traceback
                traceback.print_exc()
                progress.visible = False
                progress.update()
                _snack(page, f'{scope_cn}导出失败: {str(ex)}', success=False)

        page.run_task(run)

    return [
        ft.Container(
            padding=20,
            content=ft.Column(
                controls=[
                        # ---- 顶部导航 ----
                        ft.Row(
                            controls=[
                                ft.IconButton(
                                    icon=ft.Icons.ARROW_BACK,
                                    icon_size=24,
                                    on_click=lambda e: on_back() if on_back else None,
                                ),
                                ft.Text('数据导出', size=26, weight=ft.FontWeight.BOLD, color='#1565C0'),
                            ],
                            spacing=8,
                        ),
                        ft.Divider(height=2, color='#E0E0E0'),

                        # ---- 导出目录设置 ----
                        ft.Container(
                            content=ft.Column([
                                ft.Row([
                                    ft.Icon(ft.Icons.FOLDER, color='#1976D2', size=22),
                                    ft.Text('导出目录设置', size=18, weight=ft.FontWeight.W_600),
                                ], spacing=8),
                                ft.Text(
                                    '导出文件将保存到下方指定的本地目录，路径保存在本机配置文件中，'
                                    '设置后长期生效。',
                                    size=13, color='#757575',
                                ),
                                ft.Row([
                                    dir_field,
                                    ft.ElevatedButton(
                                        content='保存设置',
                                        icon=ft.Icons.SAVE,
                                        on_click=do_save_dir,
                                        style=ft.ButtonStyle(
                                            bgcolor='#1976D2', color='white',
                                            shape=ft.RoundedRectangleBorder(radius=8),
                                        ),
                                    ),
                                ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                            ], spacing=10),
                            bgcolor='white',
                            border_radius=12,
                            padding=20,
                            shadow=ft.BoxShadow(spread_radius=0.5, blur_radius=8, color='#00000015'),
                        ),

                        # ---- 基础数据导出 ----
                        ft.Container(
                            content=ft.Column([
                                ft.Row([
                                    ft.Icon(ft.Icons.DATASET, color='#1565C0', size=22),
                                    ft.Text('基础数据导出', size=18, weight=ft.FontWeight.W_600),
                                ], spacing=8),
                                ft.Text(basic_desc, size=13, color='#616161'),
                                ft.Row([
                                    ft.ElevatedButton(
                                        content='导出基础数据',
                                        icon=ft.Icons.DOWNLOAD,
                                        on_click=lambda e: start_export('basic'),
                                        style=ft.ButtonStyle(
                                            bgcolor='#1565C0', color='white',
                                            shape=ft.RoundedRectangleBorder(radius=8),
                                        ),
                                    ),
                                ]),
                            ], spacing=10),
                            bgcolor='white',
                            border_radius=12,
                            padding=20,
                            shadow=ft.BoxShadow(spread_radius=0.5, blur_radius=8, color='#00000015'),
                        ),

                        # ---- 学生数据导出 ----
                        ft.Container(
                            content=ft.Column([
                                ft.Row([
                                    ft.Icon(ft.Icons.SCHOOL, color='#4CAF50', size=22),
                                    ft.Text('学生数据导出', size=18, weight=ft.FontWeight.W_600),
                                ], spacing=8),
                                ft.Text(student_desc, size=13, color='#616161'),
                                ft.Row([
                                    ft.ElevatedButton(
                                        content='导出学生数据',
                                        icon=ft.Icons.DOWNLOAD,
                                        on_click=lambda e: start_export('student'),
                                        style=ft.ButtonStyle(
                                            bgcolor='#4CAF50', color='white',
                                            shape=ft.RoundedRectangleBorder(radius=8),
                                        ),
                                    ),
                                ]),
                            ], spacing=10),
                            bgcolor='white',
                            border_radius=12,
                            padding=20,
                            shadow=ft.BoxShadow(spread_radius=0.5, blur_radius=8, color='#00000015'),
                        ),

                        # ---- 全部导出 ----
                        ft.Container(
                            content=ft.Row([
                                ft.ElevatedButton(
                                    content='一键导出全部数据',
                                    icon=ft.Icons.FILE_DOWNLOAD,
                                    on_click=lambda e: start_export('all'),
                                    style=ft.ButtonStyle(
                                        bgcolor='#FF9800', color='white',
                                        shape=ft.RoundedRectangleBorder(radius=8),
                                    ),
                                ),
                                progress,
                            ], spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                            bgcolor='#FFF8E1',
                            border_radius=12,
                            padding=20,
                        ),
                    ],
                    spacing=20,
                ),
            ),
    ]
