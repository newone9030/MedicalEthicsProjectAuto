"""
反馈任务管理视图（管理员）
按 page_category 分组展示反馈任务，支持创建/编辑/删除
"""

import flet as ft
from app.auth.feedback_admin_service import (
    create_feedback_task, update_feedback_task, delete_feedback_task,
    get_feedback_task_list, get_feedback_task_detail,
    add_feedback_question, update_feedback_question, delete_feedback_question,
    add_feedback_option, update_feedback_option, delete_feedback_option,
    get_feedback_task_mappings, add_feedback_task_mapping, remove_feedback_task_mapping,
    get_all_survey_questions,
)
from app.student.feedback_service import (
    get_feedback_submitters, get_student_feedback, delete_student_feedback,
)

CATEGORY_LABELS = {
    'case': '案例评价',
    'task_burden': '作答要求与任务负担',
    'course_impact': '课程影响、系统与隐私体验',
    'open_feedback': '开放式反馈',
}

CATEGORY_COLORS = {
    'case': '#1976D2',
    'task_burden': '#FF9800',
    'course_impact': '#4CAF50',
    'open_feedback': '#9C27B0',
}


def build_feedback_task_list_view(page: ft.Page, on_back, on_create_task) -> list:
    """构建反馈任务列表视图"""

    task_list_col = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
    category_order = ['case', 'task_burden', 'course_impact', 'open_feedback']

    def show_snack(msg: str, success: bool = True):
        snack = ft.SnackBar(
            ft.Text(msg),
            bgcolor='#4CAF50' if success else '#FF5252',
        )
        page.overlay.append(snack)
        snack.open = True
        page.update()

    def _populate_task_list():
        """填充任务列表 controls（不调用 update，适用于初始加载和刷新）"""
        tasks = get_feedback_task_list()
        task_list_col.controls.clear()

        # 按 page_category 分组
        groups = {}
        for t in tasks:
            cat = t['page_category']
            if cat not in groups:
                groups[cat] = []
            groups[cat].append(t)

        for cat in category_order:
            cat_tasks = groups.get(cat, [])
            if not cat_tasks:
                continue

            label = CATEGORY_LABELS.get(cat, cat)
            color = CATEGORY_COLORS.get(cat, '#757575')

            task_list_col.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.FOLDER, color=color, size=20),
                        ft.Text(f'{label} ({len(cat_tasks)})', size=15,
                                weight=ft.FontWeight.W_600, color=color),
                    ], spacing=8),
                    bgcolor=color + '15',
                    border_radius=8,
                    padding=ft.Padding(12, 8, 12, 8),
                )
            )

            for t in cat_tasks:
                task_list_col.controls.append(_build_task_card(page, t, refresh_list,
                                                                show_snack, on_create_task))

        if not tasks:
            task_list_col.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.ASSIGNMENT_OUTLINED, size=48, color='#BDBDBD'),
                        ft.Text('暂无反馈任务', size=14, color='#9E9E9E'),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=40,
                    alignment=ft.Alignment.CENTER,
                )
            )

    def refresh_list():
        """刷新列表（控件已挂载时调用 update）"""
        _populate_task_list()
        if task_list_col.page:
            task_list_col.update()

    def handle_create(e):
        choice_dlg = ft.AlertDialog(
            title=ft.Text('选择反馈任务分类', weight=ft.FontWeight.BOLD, size=18),
            content=ft.Column([
                ft.Text('请选择要创建的反馈任务所属页面分类：', size=13, color='#616161'),
                ft.Divider(height=12, color='transparent'),
                *[
                    ft.OutlinedButton(
                        content=ft.Row([
                            ft.Icon(ft.Icons.FOLDER, color=CATEGORY_COLORS.get(cat, '#757575'), size=16),
                            ft.Text(CATEGORY_LABELS.get(cat, cat), size=13),
                        ], spacing=8),
                        on_click=lambda e, c=cat: on_create_task(e, c),
                        style=ft.ButtonStyle(
                            shape=ft.RoundedRectangleBorder(radius=8),
                            side=ft.BorderSide(color=CATEGORY_COLORS.get(cat, '#757575'), width=1),
                        ),
                        width=280,
                    )
                    for cat in category_order
                ],
            ], tight=True, width=320),
            actions=[
                ft.TextButton(content='取消', on_click=lambda e: (setattr(choice_dlg, 'open', False), page.update())),
            ],
            modal=True,
        )
        page.show_dialog(choice_dlg)

    def _open_submitters_dialog(e=None):
        """打开"反馈作答管理"对话框：查看 / 删除作答者的反馈内容"""
        list_col = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)

        def refresh():
            list_col.controls.clear()
            submitters = get_feedback_submitters()
            if not submitters:
                list_col.controls.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Icon(ft.Icons.INBOX_OUTLINED, size=48, color='#BDBDBD'),
                            ft.Text('暂无作答者，尚无学生提交反馈', size=14, color='#9E9E9E'),
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                        padding=40,
                        alignment=ft.Alignment.CENTER,
                    )
                )
            else:
                for s in submitters:
                    list_col.controls.append(_build_submitter_card(page, s, refresh, show_snack))
            try:
                if list_col.page is not None:
                    list_col.update()
            except Exception:
                pass

        def close(e):
            dlg.open = False
            page.update()

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text('反馈作答管理', size=18, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=list_col,
                width=620,
                height=480,
                padding=ft.Padding(0, 4, 0, 4),
            ),
            actions=[
                ft.TextButton('关闭', on_click=close),
            ],
        )
        page.show_dialog(dlg)
        refresh()

    _populate_task_list()

    header_bar = ft.Row([
        ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=lambda e: on_back(),
                     icon_color='#1976D2', tooltip='返回仪表盘', icon_size=22),
        ft.Text('反馈任务维护', size=22, weight=ft.FontWeight.BOLD, color='#212121'),
        ft.Container(expand=True),
        ft.OutlinedButton(
            content='作答管理',
            icon=ft.Icons.RATE_REVIEW,
            on_click=lambda e: _open_submitters_dialog(),
            style=ft.ButtonStyle(
                color='#1976D2',
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
        ),
        ft.ElevatedButton(
            content='创建任务',
            icon=ft.Icons.ADD,
            on_click=handle_create,
            style=ft.ButtonStyle(
                bgcolor='#1976D2', color='white',
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
        ),
    ])

    return [
        header_bar,
        ft.Divider(height=12, color='transparent'),
        task_list_col,
    ]


def _build_task_card(page, task, refresh_list, show_snack, on_create_task):
    """构建单个反馈任务卡片"""
    color = CATEGORY_COLORS.get(task['page_category'], '#757575')

    def do_delete(e):
        dlg = ft.AlertDialog(
            title=ft.Text('确认删除', weight=ft.FontWeight.BOLD, size=18),
            content=ft.Text(f'确定要删除反馈任务 "{task["title"]}" 吗？\n该操作将同时删除关联题目和选项，且不可恢复。'),
            actions=[
                ft.TextButton('取消', on_click=lambda _: (setattr(dlg, 'open', False), page.update())),
                ft.ElevatedButton(
                    '确认删除',
                    on_click=lambda _: _exec_delete(),
                    style=ft.ButtonStyle(bgcolor='#FF5252', color='white', shape=ft.RoundedRectangleBorder(radius=8)),
                ),
            ],
            modal=True,
        )
        page.show_dialog(dlg)

        def _exec_delete():
            dlg.open = False
            page.update()
            result = delete_feedback_task(task['id'])
            show_snack(result['message'], result['success'])
            if result['success']:
                refresh_list()

    return ft.Container(
        content=ft.Row([
            ft.Column([
                ft.Text(task['title'], size=15, weight=ft.FontWeight.W_500, color='#212121'),
                ft.Text(task['description'] or '', size=12, color='#757575', max_lines=2),
            ], spacing=4, expand=True),
            ft.Container(
                content=ft.Text(f'{task["question_count"]} 题', size=12, color=color, weight=ft.FontWeight.W_500),
                bgcolor=color + '20',
                border_radius=12,
                padding=ft.Padding(12, 4, 12, 4),
            ),
            ft.IconButton(
                icon=ft.Icons.EDIT, icon_color='#1976D2', tooltip='编辑',
                on_click=lambda e, c=task['page_category'], tid=task['id']: on_create_task(e, c, tid),
            ),
            ft.IconButton(
                icon=ft.Icons.DELETE, icon_color='#FF5252', tooltip='删除',
                on_click=lambda e: do_delete(e),
            ),
        ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        bgcolor='white',
        border_radius=12,
        padding=ft.Padding(16, 12, 8, 12),
        shadow=ft.BoxShadow(spread_radius=0.5, blur_radius=6, color='#00000010'),
    )


def _fmt_time(ts):
    """格式化时间字符串，仅显示到分钟"""
    if not ts:
        return '—'
    s = str(ts)
    return s[:16] if len(s) > 16 else s


def _build_feedback_detail_dialog(page: ft.Page, student_label: str, items: list) -> ft.AlertDialog:
    """作答者反馈内容明细对话框"""

    def close_dlg(e):
        dlg.open = False
        page.update()

    if not items:
        body = ft.Container(
            content=ft.Column([
                ft.Icon(ft.Icons.INFO_OUTLINE, size=48, color='#BDBDBD'),
                ft.Text('暂无反馈内容', size=16, color='#757575'),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
            padding=30,
            alignment=ft.Alignment.CENTER,
            width=560,
        )
    else:
        content_col = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
        last_group = None
        for item in items:
            if item['group_title'] != last_group:
                last_group = item['group_title']
                content_col.controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.SUBJECT, color='#1565C0', size=18),
                            ft.Text(item['group_title'], size=16,
                                    weight=ft.FontWeight.BOLD, color='#1565C0'),
                        ], spacing=6),
                        bgcolor='#E3F2FD',
                        border_radius=8,
                        padding=ft.Padding(12, 8, 12, 8),
                    )
                )
            answer_text = item['answer_text'] or '（未作答）'
            q_col = ft.Column(spacing=4)
            q_col.controls.append(
                ft.Text(item['question_text'], size=14, weight=ft.FontWeight.W_500, color='#212121')
            )
            q_col.controls.append(
                ft.Container(
                    content=ft.Text(answer_text, size=14, color='#1565C0'),
                    padding=ft.Padding(12, 8, 12, 8),
                    bgcolor='#FAFAFA',
                    border_radius=6,
                    width=520,
                )
            )
            content_col.controls.append(q_col)
        body = ft.Container(content=content_col, width=560, height=460)

    dlg = ft.AlertDialog(
        title=ft.Text(f'{student_label} 的反馈内容', size=17, weight=ft.FontWeight.BOLD),
        content=body,
        actions=[
            ft.TextButton('关闭', on_click=close_dlg),
        ],
        modal=True,
    )
    return dlg


def _build_submitter_card(page: ft.Page, s: dict, refresh, show_snack) -> ft.Container:
    """构建单个作答者卡片：查看 / 删除反馈内容"""
    sid = s['student_id']
    display = (f"{s['real_name']}（{s['username']}）"
               if s['real_name'] and s['real_name'] != s['username'] else s['username'])

    def on_view(e):
        items = get_student_feedback(sid)
        page.show_dialog(_build_feedback_detail_dialog(page, display, items))

    def on_delete(e):
        def do_delete(ev):
            confirm_dlg.open = False
            page.update()
            try:
                delete_student_feedback(sid)
                show_snack(f'已删除「{display}」的反馈内容', True)
                refresh()
            except Exception as ex:
                show_snack(f'删除失败: {ex}', False)

        def cancel_delete(ev):
            confirm_dlg.open = False
            page.update()

        confirm_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text('删除反馈内容', size=17, weight=ft.FontWeight.BOLD),
            content=ft.Text(
                f'确定要删除「{display}」的全部反馈内容吗？\n'
                f'共 {s["answer_count"]} 条作答记录，删除后不可恢复。'
            ),
            actions=[
                ft.TextButton('取消', on_click=cancel_delete),
                ft.ElevatedButton(
                    '确认删除',
                    on_click=do_delete,
                    style=ft.ButtonStyle(bgcolor='#E53935', color='white',
                                          shape=ft.RoundedRectangleBorder(radius=8)),
                ),
            ],
        )
        page.show_dialog(confirm_dlg)

    return ft.Container(
        content=ft.Row([
            ft.Container(
                content=ft.Icon(ft.Icons.PERSON, color='white', size=18),
                bgcolor='#1976D2',
                border_radius=20,
                padding=ft.Padding(9, 9, 9, 9),
            ),
            ft.Column([
                ft.Text(display, size=14, weight=ft.FontWeight.W_600, color='#212121'),
                ft.Text(
                    f"班级：{s['class_name'] or '—'}    {s['answer_count']} 条作答",
                    size=12, color='#757575',
                ),
            ], spacing=2, expand=True),
            ft.Column([
                ft.Text('最近提交', size=11, color='#9E9E9E'),
                ft.Text(_fmt_time(s['last_submitted_at']), size=12, color='#616161'),
            ], spacing=1, horizontal_alignment=ft.CrossAxisAlignment.END),
            ft.TextButton(
                content='查看',
                icon=ft.Icons.VISIBILITY,
                on_click=on_view,
                style=ft.ButtonStyle(color='#1976D2'),
            ),
            ft.TextButton(
                content='删除',
                icon=ft.Icons.DELETE_OUTLINE,
                on_click=on_delete,
                style=ft.ButtonStyle(color='#E53935'),
            ),
        ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        bgcolor='white',
        border_radius=10,
        padding=ft.Padding(12, 10, 12, 10),
        shadow=ft.BoxShadow(spread_radius=0.5, blur_radius=6, color='#0000000A'),
    )


def build_feedback_task_editor(page: ft.Page, page_category: str, task_id: int = None,
                                on_back=None) -> list:
    """构建反馈任务编辑视图"""

    is_new = task_id is None

    show_snack = lambda msg, success=True: (
        snack := ft.SnackBar(ft.Text(msg), bgcolor='#4CAF50' if success else '#FF5252'),
        page.overlay.append(snack),
        setattr(snack, 'open', True),
        page.update(),
    )

    # ---- 表单字段 ----
    title_field = ft.TextField(
        label='任务标题', hint_text='请输入反馈任务标题',
        prefix_icon=ft.Icons.TITLE,
        border_color='#BBDEFB', focused_border_color='#1976D2',
    )
    desc_field = ft.TextField(
        label='描述', hint_text='请输入任务描述（可选）',
        prefix_icon=ft.Icons.DESCRIPTION,
        multiline=True, min_lines=2, max_lines=4,
        border_color='#BBDEFB', focused_border_color='#1976D2',
    )

    # 加载已有数据
    if not is_new:
        detail = get_feedback_task_detail(task_id)
        if detail['success']:
            t = detail['task']
            title_field.value = t['title']
            desc_field.value = t['description']
            page_category = t['page_category']

    category_label = CATEGORY_LABELS.get(page_category, page_category)
    category_color = CATEGORY_COLORS.get(page_category, '#757575')

    # ---- 动态内容区 ----
    form_section = ft.Column(spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
    # 将在 build_editor_content 中填充

    # 暂存数据（用于新增/修改题目后刷新）
    questions_data = []  # [{'id': int, 'question_text': str, 'question_type': str, 'options': [...]}, ...]

    def _populate_editor_content():
        """填充编辑区 controls（不调用 update，适用于初始加载）"""
        _fill_editor_controls()

    def build_editor_content():
        """（重新）构建编辑区内容，并刷新 UI"""
        _fill_editor_controls()
        if form_section.page:
            form_section.update()

    def _fill_editor_controls():
        """填充 form_section.controls（公共逻辑）"""
        form_section.controls.clear()

        if not is_new:
            detail = get_feedback_task_detail(task_id)
            if detail['success']:
                nonlocal questions_data
                questions_data = detail['task']['questions']
        else:
            questions_data.clear()

        form_section.controls.append(
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Container(
                            content=ft.Text(category_label, size=13, color=category_color,
                                           weight=ft.FontWeight.W_600),
                            bgcolor=category_color + '20',
                            border_radius=8,
                            padding=ft.Padding(12, 4, 12, 4),
                        ),
                        ft.Text('分类不可更改' if not is_new else '已选择分类', size=12, color='#9E9E9E'),
                    ], spacing=8),
                    ft.Divider(height=12, color='transparent'),
                    title_field,
                    ft.Divider(height=8, color='transparent'),
                    desc_field,
                ]),
            )
        )

        # 保存按钮（仅新建时需要先保存获得 task_id）
        if is_new:
            form_section.controls.append(
                ft.Container(
                    content=ft.ElevatedButton(
                        content='保存任务（创建题目将在保存后进行）',
                        icon=ft.Icons.SAVE,
                        on_click=do_save_create,
                        style=ft.ButtonStyle(bgcolor='#1976D2', color='white',
                                            shape=ft.RoundedRectangleBorder(radius=8)),
                    ),
                )
            )
        else:
            form_section.controls.append(
                ft.Container(
                    content=ft.ElevatedButton(
                        content='保存任务信息',
                        icon=ft.Icons.SAVE,
                        on_click=do_save_update,
                        style=ft.ButtonStyle(bgcolor='#1976D2', color='white',
                                            shape=ft.RoundedRectangleBorder(radius=8)),
                    ),
                )
            )

        # 题目管理区域（仅已有 task_id 时显示）
        if not is_new:
            form_section.controls.append(ft.Divider(height=16, color='#E0E0E0'))
            form_section.controls.append(
                ft.Row([
                    ft.Text('反馈题目', size=16, weight=ft.FontWeight.W_600, color='#212121'),
                    ft.Container(expand=True),
                    ft.OutlinedButton(
                        content='添加单选题', icon=ft.Icons.RADIO_BUTTON_CHECKED,
                        on_click=lambda e: open_add_question_dlg('radio'),
                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                    ),
                    ft.OutlinedButton(
                        content='添加开放题', icon=ft.Icons.TEXT_FIELDS,
                        on_click=lambda e: open_add_question_dlg('open'),
                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                    ),
                ], spacing=8),
            )

            for q in questions_data:
                form_section.controls.append(_build_question_card(page, q, task_id,
                                                                   show_snack, build_editor_content,
                                                                   open_add_option_dlg=open_add_option_dlg))

            # 仅 case 类显示关联调查题
            if page_category == 'case':
                form_section.controls.append(ft.Divider(height=16, color='#E0E0E0'))
                form_section.controls.append(
                    ft.Row([
                        ft.Text('关联调查题', size=16, weight=ft.FontWeight.W_600, color='#212121'),
                        ft.Container(expand=True),
                        ft.OutlinedButton(
                            content='添加关联', icon=ft.Icons.LINK,
                            on_click=open_add_mapping_dlg,
                            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                        ),
                    ], spacing=8),
                )
                # 显示已有映射
                mappings = get_feedback_task_mappings(task_id)
                for m in mappings:
                    form_section.controls.append(_build_mapping_row(page, task_id, m,
                                                                    show_snack, build_editor_content))

    def do_save_create(e):
        title = (title_field.value or '').strip()
        if not title:
            show_snack('请输入任务标题', success=False)
            return
        result = create_feedback_task(title=title, description=desc_field.value or '',
                                      page_category=page_category)
        if result['success']:
            nonlocal task_id
            task_id = result['task_id']
            is_new = False
            show_snack('任务创建成功，请添加反馈题目')
            build_editor_content()
        else:
            show_snack(result['message'], success=False)

    def do_save_update(e):
        title = (title_field.value or '').strip()
        if not title:
            show_snack('请输入任务标题', success=False)
            return
        result = update_feedback_task(task_id, title=title, description=desc_field.value or '')
        show_snack(result['message'], result['success'])
        if result['success']:
            build_editor_content()

    # ---- 添加单选题选项对话框 ----
    def open_add_option_dlg(question_id):
        """添加单选选项对话框"""
        label_field = ft.TextField(
            label='选项文字', hint_text='如：非常同意',
            border_color='#BBDEFB', focused_border_color='#1976D2',
        )
        value_field = ft.TextField(
            label='值', hint_text='如：5（用于评分）',
            border_color='#BBDEFB', focused_border_color='#1976D2',
            input_filter=ft.NumbersOnlyInputFilter(),
        )
        requires_comment_switch = ft.Checkbox(label='勾选此项后，需填写补充说明', value=False)
        comment_hint_field = ft.TextField(
            label='补充说明提示文字', hint_text='如：请具体说明原因...',
            border_color='#BBDEFB', focused_border_color='#1976D2',
            visible=False,
        )

        def toggle_hint_visible(e):
            comment_hint_field.visible = bool(e.control.value)
            if comment_hint_field.page:
                comment_hint_field.update()

        requires_comment_switch.on_change = toggle_hint_visible

        def save_option(e):
            label = (label_field.value or '').strip()
            val_str = (value_field.value or '').strip()
            if not label or not val_str:
                show_snack('请填写选项文字和值', success=False)
                return
            result = add_feedback_option(question_id, label=label, value=int(val_str),
                                          requires_comment=1 if requires_comment_switch.value else 0,
                                          comment_hint=(comment_hint_field.value or '').strip() or None)
            if result['success']:
                dlg.open = False
                page.update()
                show_snack('选项添加成功')
                build_editor_content()
            else:
                show_snack(result['message'], success=False)

        dlg = ft.AlertDialog(
            title=ft.Text('添加选项', weight=ft.FontWeight.BOLD, size=18),
            content=ft.Column([
                label_field,
                ft.Divider(height=8, color='transparent'),
                value_field,
                ft.Divider(height=8, color='transparent'),
                requires_comment_switch,
                ft.Divider(height=8, color='transparent'),
                comment_hint_field,
            ], tight=True, width=350),
            actions=[
                ft.TextButton('取消', on_click=lambda e: (setattr(dlg, 'open', False), page.update())),
                ft.ElevatedButton('添加', on_click=save_option,
                                 style=ft.ButtonStyle(bgcolor='#1976D2', color='white',
                                                     shape=ft.RoundedRectangleBorder(radius=8))),
            ],
            modal=True,
        )
        page.show_dialog(dlg)

    # ---- 添加题目对话框 ----
    def open_add_question_dlg(qtype):
        qtext_field = ft.TextField(
            label='题目内容', hint_text='请输入反馈题目',
            multiline=True, min_lines=2, max_lines=4,
            border_color='#BBDEFB', focused_border_color='#1976D2',
        )
        # 仅开放题支持"必答"设置
        required_switch = ft.Checkbox(
            label='该题为必答题（学生必须填写才能提交）', value=False,
            visible=(qtype == 'open'),
        )

        def save_question(e):
            qtext = (qtext_field.value or '').strip()
            if not qtext:
                show_snack('请输入题目内容', success=False)
                return
            result = add_feedback_question(
                task_id, question_text=qtext, question_type=qtype,
                required=1 if (qtype == 'open' and required_switch.value) else 0,
            )
            if result['success']:
                dlg.open = False
                page.update()
                show_snack('题目添加成功')
                build_editor_content()
                # 如果是单选题，自动弹出添加选项对话框
                if qtype == 'radio':
                    open_add_option_dlg(result['question_id'])
            else:
                show_snack(result['message'], success=False)

        dlg = ft.AlertDialog(
            title=ft.Text(f'添加{"单选题" if qtype == "radio" else "开放题"}', weight=ft.FontWeight.BOLD, size=18),
            content=ft.Column([
                qtext_field,
                ft.Divider(height=8, color='transparent'),
                required_switch,
            ], tight=True, width=380),
            actions=[
                ft.TextButton('取消', on_click=lambda e: (setattr(dlg, 'open', False), page.update())),
                ft.ElevatedButton('添加', on_click=save_question,
                                 style=ft.ButtonStyle(bgcolor='#1976D2', color='white',
                                                     shape=ft.RoundedRectangleBorder(radius=8))),
            ],
            modal=True,
        )
        page.show_dialog(dlg)

    # ---- 添加关联调查题对话框 ----
    def open_add_mapping_dlg(e):
        all_qs = get_all_survey_questions()
        current_mappings = get_feedback_task_mappings(task_id)
        mapped_ids = {m['survey_question_id'] for m in current_mappings}

        checks = []
        for q in all_qs:
            if q['id'] in mapped_ids:
                continue
            checks.append(
                ft.Checkbox(
                    label=f"[{q['case_title']}] {q['question_text'][:60]}",
                    data=q['id'],
                )
            )

        if not checks:
            show_snack('没有可关联的调查题（或全部已关联）', success=False)
            return

        def save_mappings(e):
            count = 0
            for cb in checks:
                if cb.value:
                    add_feedback_task_mapping(task_id, cb.data)
                    count += 1
            dlg.open = False
            page.update()
            if count > 0:
                show_snack(f'已添加 {count} 个关联')
                build_editor_content()
            else:
                show_snack('未选择任何调查题', success=False)

        dlg = ft.AlertDialog(
            title=ft.Text('关联调查题', weight=ft.FontWeight.BOLD, size=18),
            content=ft.Column(
                [ft.Text('请选择本任务需要关联的调查题：', size=13, color='#616161'),
                 ft.Divider(height=8, color='transparent'),
                 *checks],
                tight=True, width=400, height=350, scroll=ft.ScrollMode.AUTO,
            ),
            actions=[
                ft.TextButton('取消', on_click=lambda e: (setattr(dlg, 'open', False), page.update())),
                ft.ElevatedButton('确认关联', on_click=save_mappings,
                                 style=ft.ButtonStyle(bgcolor='#1976D2', color='white',
                                                     shape=ft.RoundedRectangleBorder(radius=8))),
            ],
            modal=True,
        )
        page.show_dialog(dlg)

    # 初始构建
    _populate_editor_content()

    header_bar = ft.Row([
        ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=lambda e: on_back(),
                     icon_color='#1976D2', tooltip='返回列表', icon_size=22),
        ft.Text('编辑反馈任务' if not is_new else f'新建反馈任务 - {category_label}',
               size=20, weight=ft.FontWeight.BOLD, color='#212121'),
    ])

    return [
        header_bar,
        ft.Divider(height=12, color='transparent'),
        form_section,
    ]


def _build_question_card(page, q, task_id, show_snack, refresh_content,
                        open_add_option_dlg=None):
    """构建单个题目卡片"""
    qtype_label = '单选题' if q['question_type'] == 'radio' else '开放题'
    qtype_icon = ft.Icons.RADIO_BUTTON_CHECKED if q['question_type'] == 'radio' else ft.Icons.TEXT_FIELDS

    options_col = ft.Column(spacing=4)
    if q['question_type'] == 'radio':
        for o in q.get('options', []):
            comment_note = ' (需补充说明)' if o.get('requires_comment') else ''
            if o.get('requires_comment') and (o.get('comment_hint') or '').strip():
                comment_note += f'（提示：{o["comment_hint"]}）'
            options_col.controls.append(
                ft.Row([
                    ft.Icon(ft.Icons.CIRCLE_OUTLINED, size=14, color='#9E9E9E'),
                    ft.Text(f'{o["label"]} ({o["value"]}){comment_note}', size=13, color='#616161'),
                    ft.IconButton(
                        icon=ft.Icons.EDIT, icon_size=14, icon_color='#1976D2',
                        tooltip='编辑选项',
                        on_click=lambda e, o=o: _exec_edit_option(o),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE, icon_size=14, icon_color='#FF5252',
                        on_click=lambda e, oid=o['id']: _exec_delete_option(oid),
                    ),
                ], spacing=4),
            )
        if open_add_option_dlg:
            options_col.controls.append(
                ft.TextButton(
                    content='+ 添加选项',
                    on_click=lambda e, qid=q['id']: open_add_option_dlg(qid),
                )
            )
    else:
        options_col.controls.append(
            ft.Text('（开放题，无需选项）', size=12, color='#9E9E9E')
        )

    def _exec_delete_option(oid):
        delete_feedback_option(oid)
        show_snack('选项已删除')
        refresh_content()

    def _exec_edit_option(o):
        """编辑选项对话框"""
        label_field = ft.TextField(
            label='选项文字', value=o['label'],
            border_color='#BBDEFB', focused_border_color='#1976D2',
        )
        value_field = ft.TextField(
            label='值', value=str(o['value']),
            border_color='#BBDEFB', focused_border_color='#1976D2',
            input_filter=ft.NumbersOnlyInputFilter(),
        )
        requires_comment_switch = ft.Checkbox(
            label='勾选此项后，需填写补充说明',
            value=o.get('requires_comment', False),
        )
        comment_hint_field = ft.TextField(
            label='补充说明提示文字', hint_text='如：请具体说明原因...',
            value=o.get('comment_hint', ''),
            border_color='#BBDEFB', focused_border_color='#1976D2',
            visible=o.get('requires_comment', False),
        )

        def toggle_hint_visible(e):
            comment_hint_field.visible = bool(e.control.value)
            if comment_hint_field.page:
                comment_hint_field.update()

        requires_comment_switch.on_change = toggle_hint_visible

        def save_option(e):
            label = (label_field.value or '').strip()
            val_str = (value_field.value or '').strip()
            if not label or not val_str:
                show_snack('请填写选项文字和值', success=False)
                return
            result = update_feedback_option(o['id'], label=label, value=int(val_str),
                                             requires_comment=1 if requires_comment_switch.value else 0,
                                             comment_hint=(comment_hint_field.value or '').strip() or '')
            if result['success']:
                dlg.open = False
                page.update()
                show_snack('选项已更新')
                refresh_content()
            else:
                show_snack(result['message'], success=False)

        dlg = ft.AlertDialog(
            title=ft.Text('编辑选项', weight=ft.FontWeight.BOLD, size=18),
            content=ft.Column([
                label_field,
                ft.Divider(height=8, color='transparent'),
                value_field,
                ft.Divider(height=8, color='transparent'),
                requires_comment_switch,
                ft.Divider(height=8, color='transparent'),
                comment_hint_field,
            ], tight=True, width=350),
            actions=[
                ft.TextButton('取消', on_click=lambda e: (setattr(dlg, 'open', False), page.update())),
                ft.ElevatedButton('保存', on_click=save_option,
                                 style=ft.ButtonStyle(bgcolor='#1976D2', color='white',
                                                     shape=ft.RoundedRectangleBorder(radius=8))),
            ],
            modal=True,
        )
        page.show_dialog(dlg)

    def _exec_edit_question():
        """编辑题目对话框（内容 + 类型）"""
        qtext_field = ft.TextField(
            label='题目内容', value=q['question_text'],
            multiline=True, min_lines=2, max_lines=4,
            border_color='#BBDEFB', focused_border_color='#1976D2',
        )
        type_dropdown = ft.Dropdown(
            label='题目类型',
            options=[
                ft.DropdownOption(key='radio', text='单选题'),
                ft.DropdownOption(key='open', text='开放题'),
            ],
            value=q['question_type'],
        )
        # 必答开关：仅开放题生效
        required_switch = ft.Checkbox(
            label='该题为必答题（学生必须填写才能提交）',
            value=bool(q.get('required', False)),
            visible=(q['question_type'] == 'open'),
        )

        def toggle_required_visible(e):
            required_switch.visible = (type_dropdown.value == 'open')
            if required_switch.page:
                required_switch.update()

        type_dropdown.on_change = toggle_required_visible

        def save_question(e):
            qtext = (qtext_field.value or '').strip()
            if not qtext:
                show_snack('请输入题目内容', success=False)
                return
            result = update_feedback_question(
                q['id'], question_text=qtext, question_type=type_dropdown.value,
                required=1 if (type_dropdown.value == 'open' and required_switch.value) else 0,
            )
            if result['success']:
                dlg.open = False
                page.update()
                show_snack('题目已更新')
                refresh_content()
            else:
                show_snack(result['message'], success=False)

        dlg = ft.AlertDialog(
            title=ft.Text('编辑题目', weight=ft.FontWeight.BOLD, size=18),
            content=ft.Column([
                qtext_field,
                ft.Divider(height=8, color='transparent'),
                type_dropdown,
                ft.Divider(height=8, color='transparent'),
                required_switch,
            ], tight=True, width=380),
            actions=[
                ft.TextButton('取消', on_click=lambda e: (setattr(dlg, 'open', False), page.update())),
                ft.ElevatedButton('保存', on_click=save_question,
                                 style=ft.ButtonStyle(bgcolor='#1976D2', color='white',
                                                     shape=ft.RoundedRectangleBorder(radius=8))),
            ],
            modal=True,
        )
        page.show_dialog(dlg)

    def _exec_delete_question(qid):
        dlg = ft.AlertDialog(
            title=ft.Text('确认删除', weight=ft.FontWeight.BOLD, size=18),
            content=ft.Text('确定要删除此题吗？关联的选项和作答记录也将被删除。'),
            actions=[
                ft.TextButton('取消', on_click=lambda _: (setattr(dlg, 'open', False), page.update())),
                ft.ElevatedButton('确认删除', on_click=lambda _: _do_delete(),
                                 style=ft.ButtonStyle(bgcolor='#FF5252', color='white',
                                                     shape=ft.RoundedRectangleBorder(radius=8))),
            ],
            modal=True,
        )
        page.show_dialog(dlg)

        def _do_delete():
            dlg.open = False
            page.update()
            delete_feedback_question(qid)
            show_snack('题目已删除')
            refresh_content()

    return ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Container(
                    content=ft.Row([
                        ft.Icon(qtype_icon, size=14, color='white'),
                        ft.Text(qtype_label, size=12, color='white', weight=ft.FontWeight.W_500),
                    ], spacing=4),
                    bgcolor='#1976D2' if q['question_type'] == 'radio' else '#9C27B0',
                    border_radius=8,
                    padding=ft.Padding(8, 2, 8, 2),
                ),
                ft.Text(q['question_text'], size=14, weight=ft.FontWeight.W_500, color='#212121'),
                ft.Container(
                    content=ft.Text('必答', size=11, weight=ft.FontWeight.W_600, color='#FF5252'),
                    visible=(q['question_type'] == 'open' and bool(q.get('required', False))),
                ),
                ft.Container(expand=True),
                ft.IconButton(
                    icon=ft.Icons.EDIT, icon_size=16, icon_color='#1976D2',
                    tooltip='编辑题目',
                    on_click=lambda e: _exec_edit_question(),
                ),
                ft.IconButton(
                    icon=ft.Icons.DELETE, icon_size=16, icon_color='#FF5252',
                    tooltip='删除题目',
                    on_click=lambda e, qid=q['id']: _exec_delete_question(qid),
                ),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.START),
            options_col,
        ], spacing=6),
        bgcolor='#FAFAFA',
        border_radius=10,
        border=ft.BorderSide(color='#E0E0E0', width=1),
        padding=ft.Padding(12, 10, 8, 10),
    )


def _build_mapping_row(page, task_id, mapping, show_snack, refresh_content):
    """构建关联调查题行"""
    def _exec_remove_mapping():
        remove_feedback_task_mapping(task_id, mapping['survey_question_id'])
        show_snack('关联已移除')
        refresh_content()

    return ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.LINK, size=16, color='#1976D2'),
            ft.Column([
                ft.Text(f'[{mapping["case_title"]}]', size=12, color='#1976D2', weight=ft.FontWeight.W_500),
                ft.Text(mapping['question_text'][:80], size=13, color='#424242'),
            ], spacing=2, expand=True),
            ft.IconButton(
                icon=ft.Icons.CLOSE, icon_size=16, icon_color='#FF5252',
                on_click=lambda e: _exec_remove_mapping(),
            ),
        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        bgcolor='#E3F2FD',
        border_radius=10,
        padding=ft.Padding(12, 8, 8, 8),
    )
