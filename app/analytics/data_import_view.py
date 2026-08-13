"""
数据导入视图：管理员从导出的 Excel 恢复数据

- 从导出目录选择（或手动输入）xlsx 文件
- 载入后展示可导入的工作表，勾选需要导入的 sheet
- 可勾选导入前需要清空的目标表
- 导入结果通过 SnackBar 汇总展示
"""

import asyncio
import os

import flet as ft

from app.analytics.data_import_service import (
    list_excel_files,
    read_workbook_sheets,
    do_import,
)
from app.analytics.data_export_service import get_export_dir


def _snack(page: ft.Page, message: str, success: bool = True):
    snack = ft.SnackBar(
        content=ft.Text(message, color='white'),
        bgcolor='#4CAF50' if success else '#FF5252',
        duration=6000,
    )
    page.overlay.append(snack)
    snack.open = True
    page.update()


def build_data_import_view(page: ft.Page, on_back=None) -> list:
    """构建数据导入页面，返回控件列表"""

    sheet_rows = ft.Column(spacing=8)          # 工作表勾选列表
    clear_rows = ft.Column(spacing=8)          # 清空表勾选列表（与导入联动）
    import_dir = get_export_dir()
    files = list_excel_files(import_dir)

    file_dropdown = ft.Dropdown(
        label='选择导出文件',
        hint_text='从导出目录选择 xlsx 文件',
        options=[ft.dropdown.Option(f) for f in files],
        expand=True,
        border_color='#BBDEFB',
        focused_border_color='#1976D2',
    )
    file_field = ft.TextField(
        label='或手动输入文件路径',
        hint_text='例如: D:/exports/基础数据_20260813_200730.xlsx',
        border_color='#BBDEFB',
        focused_border_color='#1976D2',
        expand=True,
    )
    progress = ft.ProgressBar(visible=False)
    info_text = ft.Text(
        '载入文件后选择需要导入的工作表，并可勾选导入前要清空的目标表。',
        size=13, color='#757575',
    )

    # 各表导入状态缓存：{sheet名: {表名, 行数, 导入Checkbox, 清空Checkbox}}
    state = {}

    def clear_sheet_lists(message: str = None):
        """清空两个勾选列表（重新载入文件前调用，避免旧列表残留）"""
        sheet_rows.controls = []
        clear_rows.controls = []
        state.clear()
        if message:
            info_text.value = message
        info_text.update()
        sheet_rows.update()
        clear_rows.update()
        page.update()

    def rebuild_sheet_lists(sheets_info: dict):
        """根据载入的 sheet 信息重建两个勾选列表（先清空现有再重新加载）"""
        # 先清空现有列表并同步到界面
        clear_sheet_lists()

        if not sheets_info:
            info_text.value = '文件中没有可导入的工作表（需为本系统导出的 Excel）。'
            info_text.update()
            page.update()
            return

        info_text.value = f'共 {len(sheets_info)} 个工作表可导入，请勾选需要的项目。'
        new_sheet_controls = []
        new_clear_controls = []
        for sheet_name, info in sheets_info.items():
            import_cb = ft.Checkbox(
                label=f'{sheet_name}（{info["rows"]} 行）',
                value=False,
            )
            clear_cb = ft.Checkbox(
                label=f'{info["table"]}',
                value=False,
            )
            state[sheet_name] = {
                'table': info['table'],
                'rows': info['rows'],
                'import_cb': import_cb,
                'clear_cb': clear_cb,
            }
            new_sheet_controls.append(
                ft.Container(
                    content=ft.Row([
                        import_cb,
                        ft.Text(f'目标表: {info["table"]}', size=12, color='#9E9E9E'),
                    ], spacing=8),
                    bgcolor='#F5F7FA',
                    border_radius=8,
                    padding=10,
                )
            )
            new_clear_controls.append(clear_cb)
        # 整体赋值强制重建，保证客户端移除旧控件
        sheet_rows.controls = new_sheet_controls
        clear_rows.controls = new_clear_controls
        info_text.update()
        sheet_rows.update()
        clear_rows.update()
        page.update()

    def load_file(e):
        path = (file_field.value or '').strip().strip('"').strip("'")
        if not path and file_dropdown.value:
            path = os.path.join(import_dir, file_dropdown.value)
        if not path:
            _snack(page, '请选择文件或输入文件路径', success=False)
            return
        if not os.path.exists(path):
            _snack(page, f'文件不存在: {path}', success=False)
            return
        try:
            sheets_info = read_workbook_sheets(path)
            file_field.value = os.path.normpath(path)
            file_field.update()
            rebuild_sheet_lists(sheets_info)
            _snack(page, f'已载入文件，共 {len(sheets_info)} 个可导入工作表')
        except Exception as ex:
            clear_sheet_lists()
            _snack(page, f'载入文件失败: {ex}', success=False)

    def refresh_files(e):
        file_dropdown.options = [ft.dropdown.Option(f) for f in list_excel_files(import_dir)]
        file_dropdown.update()

    def select_all(e):
        for s in state.values():
            s['import_cb'].value = True
        page.update()

    def select_none(e):
        for s in state.values():
            s['import_cb'].value = False
        page.update()

    def run_import(e):
        filepath = (file_field.value or '').strip().strip('"').strip("'")
        if not filepath:
            _snack(page, '请先载入 Excel 文件', success=False)
            return
        sheets = [name for name, s in state.items() if s['import_cb'].value]
        if not sheets:
            _snack(page, '请至少勾选一个要导入的工作表', success=False)
            return
        tables = [s['table'] for s in state.values() if s['clear_cb'].value]
        # 去重并提示
        unique_tables = sorted(set(tables))

        progress.visible = True
        progress.update()

        async def run():
            try:
                result = await asyncio.to_thread(do_import, filepath, sheets, unique_tables)
                progress.visible = False
                progress.update()
                if result.get('error'):
                    _snack(page, f'导入失败: {result["error"]}（已整体回滚，数据未变更）', success=False)
                    return
                lines = []
                if result['cleared']:
                    lines.append('已清空表: ' + ', '.join(
                        f'{k}({v}行)' for k, v in result['cleared'].items()))
                for sheet_name, stat in result['imported'].items():
                    extra = f'，跳过 {stat["skipped"]} 行' if stat["skipped"] else ''
                    lines.append(f'{sheet_name}: 导入 {stat["imported"]} 行{extra}')
                _snack(page, '导入完成\n' + '\n'.join(lines), success=True)
            except Exception as ex:
                import traceback
                traceback.print_exc()
                progress.visible = False
                progress.update()
                _snack(page, f'导入失败: {str(ex)}', success=False)

        page.run_task(run)

    return [
        ft.Container(
            padding=20,
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.IconButton(
                                icon=ft.Icons.ARROW_BACK,
                                icon_size=24,
                                on_click=lambda e: on_back() if on_back else None,
                            ),
                            ft.Text('数据导入', size=26, weight=ft.FontWeight.BOLD, color='#1565C0'),
                        ],
                        spacing=8,
                    ),
                    ft.Divider(height=2, color='#E0E0E0'),

                    # ---- 文件选择 ----
                    ft.Container(
                        content=ft.Column([
                            ft.Row([
                                ft.Icon(ft.Icons.UPLOAD_FILE, color='#1976D2', size=22),
                                ft.Text('选择导出文件', size=18, weight=ft.FontWeight.W_600),
                            ], spacing=8),
                            ft.Text(
                                f'默认从导出目录读取: {import_dir}',
                                size=13, color='#757575',
                            ),
                            ft.Row([file_dropdown, ft.IconButton(
                                icon=ft.Icons.REFRESH, icon_size=20,
                                tooltip='刷新文件列表',
                                on_click=refresh_files)], spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER),
                            ft.Row([file_field, ft.ElevatedButton(
                                content='载入工作表',
                                icon=ft.Icons.SEARCH,
                                on_click=load_file,
                                style=ft.ButtonStyle(
                                    bgcolor='#1976D2', color='white',
                                    shape=ft.RoundedRectangleBorder(radius=8),
                                ),
                            )], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                            info_text,
                        ], spacing=10),
                        bgcolor='white',
                        border_radius=12,
                        padding=20,
                        shadow=ft.BoxShadow(spread_radius=0.5, blur_radius=8, color='#00000015'),
                    ),

                    # ---- 导入选择 ----
                    ft.Container(
                        content=ft.Column([
                            ft.Row([
                                ft.Icon(ft.Icons.CHECKLIST, color='#1565C0', size=22),
                                ft.Text('选择要导入的数据', size=18, weight=ft.FontWeight.W_600),
                                ft.TextButton('全选', on_click=select_all),
                                ft.TextButton('取消全选', on_click=select_none),
                            ], spacing=8),
                            sheet_rows,
                        ], spacing=10),
                        bgcolor='white',
                        border_radius=12,
                        padding=20,
                        shadow=ft.BoxShadow(spread_radius=0.5, blur_radius=8, color='#00000015'),
                    ),

                    # ---- 清空表 ----
                    ft.Container(
                        content=ft.Column([
                            ft.Row([
                                ft.Icon(ft.Icons.DELETE_SWEEP, color='#E65100', size=22),
                                ft.Text('导入前清空目标表（可选）', size=18, weight=ft.FontWeight.W_600),
                            ], spacing=8),
                            ft.Text(
                                '勾选后将在导入前删除对应表内全部数据（同一事务，失败自动回滚）。',
                                size=13, color='#757575',
                            ),
                            clear_rows,
                        ], spacing=10),
                        bgcolor='white',
                        border_radius=12,
                        padding=20,
                        shadow=ft.BoxShadow(spread_radius=0.5, blur_radius=8, color='#00000015'),
                    ),

                    # ---- 导入按钮 ----
                    ft.Container(
                        content=ft.Row([
                            ft.ElevatedButton(
                                content='开始导入',
                                icon=ft.Icons.IMPORT_EXPORT,
                                on_click=run_import,
                                style=ft.ButtonStyle(
                                    bgcolor='#E65100', color='white',
                                    shape=ft.RoundedRectangleBorder(radius=8),
                                ),
                            ),
                            progress,
                        ], spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        bgcolor='#FFF3E0',
                        border_radius=12,
                        padding=20,
                    ),
                ],
                spacing=20,
            ),
        ),
    ]
