"""Minimal dashboard test to isolate the rendering issue"""
import flet as ft

def main(page: ft.Page):
    page.title = "Dashboard Test"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 0
    page.scroll = ft.ScrollMode.AUTO
    
    page.theme = ft.Theme(
        color_scheme=ft.ColorScheme(
            primary='#1565C0',
            primary_container='#BBDEFB',
            on_primary='#FFFFFF',
            background='#F5F7FA',
        ),
    )
    
    def _stat_card(title, value, icon, color):
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(icon, color=color, size=24),
                    ft.Text(title, size=12, color='#757575'),
                ], spacing=8),
                ft.Text(str(value), size=28, weight=ft.FontWeight.BOLD, color='#1565C0'),
            ], spacing=4),
            padding=ft.padding.all(16),
            border_radius=8,
            bgcolor='white',
            shadow=ft.BoxShadow(
                spread_radius=0.5, blur_radius=4,
                color=ft.colors.with_opacity(0.08, '#000000'),
            ),
        )
    
    stats = ft.Row([
        _stat_card('案例总数', 0, ft.Icons.LIBRARY_BOOKS, '#1565C0'),
        _stat_card('任务总数', 0, ft.Icons.ASSIGNMENT, '#1976D2'),
    ], spacing=16, wrap=True)
    
    header = ft.Container(
        content=ft.Column([
            ft.Text("Test Dashboard", size=24, weight=ft.FontWeight.BOLD, color='white'),
            ft.Text("Admin Panel", size=13, color='#FFFFFFCC'),
        ], spacing=4),
        padding=24,
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=['#1565C0', '#1976D2']
        ),
    )
    
    view = ft.View(
        route='/dashboard',
        controls=[
            ft.Container(
                content=ft.Column([
                    header,
                    ft.Container(
                        content=ft.Column([
                            ft.Text('Section 1', size=18, weight=ft.FontWeight.W_500, color='#212121'),
                            ft.Text("Hello World", size=14, color='#666666'),
                            ft.Divider(height=10, color='transparent'),
                            stats,
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
    
    print(f'View created: {len(view.controls)} controls')
    page.views.append(view)
    page.update()
    print('Page updated')

ft.app(target=main)
