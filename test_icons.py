import flet as ft
# Test all icons used in dashboard
icons_to_test = [
    'LIBRARY_BOOKS', 'ASSIGNMENT', 'PLAY_CIRCLE', 'CHECK_CIRCLE', 
    'SCHOOL', 'ADD_BOX', 'TASK_ALT', 'PLAY_ARROW', 'BAR_CHART', 'HOME',
    'SETTINGS', 'PERSON', 'MENU', 'ACCOUNT_CIRCLE', 'NOTIFICATIONS', 
    'EDIT', 'VISIBILITY', 'VISIBILITY_OFF'
]
try:
    print(f"Flet version: {ft.__version__}")
except:
    print("Flet version: unknown")
for name in icons_to_test:
    try:
        getattr(ft.icons, name)
        print(f"  OK: {name}")
    except AttributeError:
        print(f"  MISSING: {name}")

# Try building a simple view
try:
    view = ft.View(
        route='/test',
        controls=[
            ft.Container(
                content=ft.Column([
                    ft.Text("Test Header", size=20, weight="bold"),
                    ft.Container(
                        content=ft.Text("Content area"),
                        padding=24,
                        expand=True,
                    ),
                ]),
                bgcolor='#F5F7FA',
                expand=True,
            ),
        ],
    )
    print("\nView created successfully")
except Exception as e:
    print(f"\nView creation error: {type(e).__name__}: {e}")
