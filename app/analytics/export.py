"""
数据导出：CSV / Excel 格式
"""

import csv
import io
import os
from datetime import datetime
import flet as ft
from app.db import get_connection


def export_task_csv(task_id: int) -> str:
    """导出任务作答数据为CSV字符串"""
    output = io.StringIO()
    writer = csv.writer(output)

    with get_connection() as conn:
        cursor = conn.cursor()

        # 获取任务信息
        cursor.execute("SELECT name FROM tasks WHERE id = :tid", {'tid': task_id})
        task_name = cursor.fetchone()[0]

        # 获取所有题目（按案例和排序）
        cursor.execute("""
            SELECT q.id, q.question_text, q.question_type, c.title as case_title, tc.sort_order as case_order, q.sort_order
            FROM case_questions q
            JOIN task_cases tc ON q.case_id = tc.case_id
            JOIN cases c ON q.case_id = c.id
            WHERE tc.task_id = :tid
            ORDER BY tc.sort_order, q.sort_order
        """, {'tid': task_id})
        questions = cursor.fetchall()

        # 获取所有提交
        cursor.execute("""
            SELECT r.id, r.student_id, u.username, u.real_name, u.class_name, c.title as case_title, r.submitted_at
            FROM responses r
            JOIN users u ON r.student_id = u.id
            JOIN cases c ON r.case_id = c.id
            WHERE r.task_id = :tid AND r.status = 'submitted'
            ORDER BY c.id, u.class_name, u.username
        """, {'tid': task_id})
        submissions = cursor.fetchall()

        # 写表头
        header = ['学生用户名', '姓名', '班级', '案例', '提交时间'] + \
                 [f'Q{i+1}: {q[1][:30]}' for i, q in enumerate(questions)]
        writer.writerow(header)

        # 写数据
        for sub in submissions:
            response_id = sub[0]
            username = sub[2]
            real_name = sub[3] or ''
            class_name = sub[4] or ''
            case_title = sub[5]
            submitted_at = sub[6]

            row = [username, real_name, class_name, case_title,
                   submitted_at.strftime('%Y-%m-%d %H:%M:%S') if hasattr(submitted_at, 'strftime') else str(submitted_at)]

            for q in questions:
                qid = q[0]
                cursor.execute("""
                    SELECT answer FROM response_details
                    WHERE response_id = :rid AND question_id = :qid
                """, {'rid': response_id, 'qid': qid})
                ans_row = cursor.fetchone()
                ans = ans_row[0] if ans_row else ''
                row.append(ans)

            writer.writerow(row)

    return output.getvalue()


def export_task_excel(task_id: int) -> bytes:
    """导出任务作答数据为Excel字节流"""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM tasks WHERE id = :tid", {'tid': task_id})
        task_name = cursor.fetchone()[0]
        ws.title = task_name[:31]

        cursor.execute("""
            SELECT q.id, q.question_text, q.question_type, c.title as case_title, tc.sort_order as case_order, q.sort_order
            FROM case_questions q
            JOIN task_cases tc ON q.case_id = tc.case_id
            JOIN cases c ON q.case_id = c.id
            WHERE tc.task_id = :tid
            ORDER BY tc.sort_order, q.sort_order
        """, {'tid': task_id})
        questions = cursor.fetchall()

        cursor.execute("""
            SELECT r.id, r.student_id, u.username, u.real_name, u.class_name, c.title, r.submitted_at
            FROM responses r
            JOIN users u ON r.student_id = u.id
            JOIN cases c ON r.case_id = c.id
            WHERE r.task_id = :tid AND r.status = 'submitted'
            ORDER BY c.id, u.class_name, u.username
        """, {'tid': task_id})
        submissions = cursor.fetchall()

        header = ['学生用户名', '姓名', '班级', '案例', '提交时间'] + \
                 [f'Q{i+1}: {q[1][:30]}' for i, q in enumerate(questions)]
        ws.append(header)

        for sub in submissions:
            response_id = sub[0]
            row = [sub[2], sub[3] or '', sub[4] or '', sub[5],
                   sub[6].strftime('%Y-%m-%d %H:%M:%S') if hasattr(sub[6], 'strftime') else str(sub[6])]

            for q in questions:
                cursor.execute("""
                    SELECT answer FROM response_details
                    WHERE response_id = :rid AND question_id = :qid
                """, {'rid': response_id, 'qid': q[0]})
                ans_row = cursor.fetchone()
                row.append(ans_row[0] if ans_row else '')
            ws.append(row)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def handle_export(page: ft.Page, task_id: int, export_type: str):
    """处理导出，弹出文件保存对话框"""
    try:
        if export_type == 'csv':
            content = export_task_csv(task_id)
            ext = 'csv'
            data = content.encode('utf-8-sig')
        else:
            data = export_task_excel(task_id)
            ext = 'xlsx'

        # 使用文件选择器保存
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        def on_save_result(e: ft.FilePickerResultEvent):
            if e.path:
                filepath = e.path
                if not filepath.endswith(f'.{ext}'):
                    filepath += f'.{ext}'
                with open(filepath, 'wb') as f:
                    f.write(data)
                page.snack_bar = ft.SnackBar(
                    ft.Text(f'导出成功: {os.path.basename(filepath)}'),
                    bgcolor='#4CAF50',
                )
                page.snack_bar.open = True
                page.update()

        file_picker = ft.FilePicker(on_result=on_save_result)
        page.overlay.append(file_picker)
        page.update()

        file_picker.save_file(
            file_name=f'task_{task_id}_export_{timestamp}.{ext}',
            allowed_extensions=[ext],
        )
    except Exception as ex:
        page.snack_bar = ft.SnackBar(
            ft.Text(f'导出失败: {str(ex)}'),
            bgcolor='#FF5252',
        )
        page.snack_bar.open = True
        page.update()


def build_export_buttons(page: ft.Page, task_id: int) -> ft.Row:
    """构建导出按钮"""
    return ft.Row([
        ft.ElevatedButton(
            content='导出 CSV',
            icon=ft.Icons.TABLE_CHART,
            on_click=lambda e: handle_export(page, task_id, 'csv'),
            style=ft.ButtonStyle(
                bgcolor='#1976D2', color='white',
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
        ),
        ft.ElevatedButton(
            content='导出 Excel',
            icon=ft.Icons.GRID_ON,
            on_click=lambda e: handle_export(page, task_id, 'excel'),
            style=ft.ButtonStyle(
                bgcolor='#4CAF50', color='white',
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
        ),
    ], spacing=10)
