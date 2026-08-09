"""Test the actual _build_admin_dashboard function"""
import sys
sys.path.insert(0, 'c:/PythonProject')

import flet as ft

# Test importing the dashboard function
from app.db import _init_db
_init_db()

from app.case.case_service import get_case_count
from app.task.task_service import get_task_count, get_active_task_count, auto_update_task_statuses
from app.response.response_service import get_response_count
from app.analytics.analytics_service import get_student_count

print("All imports successful")

try:
    auto_update_task_statuses()
    print("auto_update_task_statuses: OK")
except Exception as e:
    print(f"auto_update_task_statuses ERROR: {e}")

try:
    case_count = get_case_count()
    print(f"get_case_count: {case_count}")
except Exception as e:
    print(f"get_case_count ERROR: {e}")

try:
    task_count = get_task_count()
    print(f"get_task_count: {task_count}")
except Exception as e:
    print(f"get_task_count ERROR: {e}")

try:
    active_count = get_active_task_count()
    print(f"get_active_task_count: {active_count}")
except Exception as e:
    print(f"get_active_task_count ERROR: {e}")

try:
    response_count = get_response_count()
    print(f"get_response_count: {response_count}")
except Exception as e:
    print(f"get_response_count ERROR: {e}")

try:
    student_count = get_student_count()
    print(f"get_student_count: {student_count}")
except Exception as e:
    print(f"get_student_count ERROR: {e}")

# Test padding=int
print("\n--- Testing Container(padding=int) ---")
try:
    c = ft.Container(content=ft.Text("test"), padding=24)
    print("Container(padding=24): OK")
except Exception as e:
    print(f"Container(padding=24) ERROR: {e}")

# Test a minimal dashboard-like view
print("\n--- Testing minimal dashboard view ---")
try:
    view = ft.View(
        route='/admin/dashboard',
        controls=[
            ft.Container(
                content=ft.Column([
                    # header
                    ft.Container(
                        content=ft.Column([
                            ft.Text("医学生伦理调查研究系统", size=24, weight=ft.FontWeight.BOLD, color='white'),
                            ft.Text("管理后台 - 数据概览", size=13, color='#FFFFFFCC'),
                        ], spacing=4),
                        padding=24,
                        gradient=ft.LinearGradient(
                            begin=ft.Alignment.TOP_LEFT,
                            end=ft.Alignment.BOTTOM_RIGHT,
                            colors=['#1565C0', '#1976D2']
                        ),
                    ),
                    # body
                    ft.Container(
                        content=ft.Column([
                            ft.Text('概览', size=18, weight=ft.FontWeight.BOLD, color='#37474F'),
                            ft.Divider(height=1, color='#E0E0E0'),
                            ft.Text(f'数据: 案例{case_count}, 任务{task_count}', size=14),
                        ], spacing=0),
                        padding=ft.padding.all(24),
                        expand=True,
                    ),
                ], spacing=0),
                bgcolor='#F5F7FA',
                expand=True,
            ),
        ],
        padding=0,
    )
    print("Dashboard view created successfully!")
    print(f"View controls: {len(view.controls)}")
    print(f"View route: {view.route}")
except Exception as e:
    import traceback
    traceback.print_exc()
    print(f"Dashboard view ERROR: {e}")
