"""
案例编辑器视图（管理员）
"""

import json
import threading
import flet as ft
from app.db import get_connection
from app.case.case_service import create_case, update_case, get_case, list_cases, delete_case
from app.case.question_service import add_question, update_question, delete_question, get_questions_by_case


def build_case_list_view(page: ft.Page, on_create, on_edit) -> ft.Column:
    """案例列表视图"""
    # 加载所有案例用于下拉选项
    all_cases = list_cases()
    case_options = [ft.DropdownOption(key=str(c['id']), text=c['title']) for c in all_cases]

    case_dropdown = ft.Dropdown(
        label='搜索并选择案例（下拉查看已创建的案例）',
        options=case_options,
        border_color='#BBDEFB',
        focused_border_color='#1976D2',
        autofocus=False,
        expand=True,
        on_select=lambda e: _on_case_selected(e, page, on_edit),
    )

    def _on_case_selected(e, page, on_edit):
        if e.control.value:
            on_edit(int(e.control.value), page)

    case_list = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO)

    def refresh_list():
        cases = list_cases()

        case_list.controls.clear()
        if not cases:
            case_list.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.FOLDER_OPEN, size=48, color='#BDBDBD'),
                        ft.Text('暂无案例', color='#9E9E9E', size=14),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=40,
                    alignment=ft.Alignment.CENTER,
                )
            )
        else:
            for c in cases:
                case_list.controls.append(_build_case_card(c, page, on_edit, refresh_list))

        if case_list.page:
            case_list.update()
        # 同步更新下拉选项
        case_dropdown.options = [ft.DropdownOption(key=str(c['id']), text=c['title']) for c in cases]
        if case_dropdown.page:
            case_dropdown.update()

    def handle_create(e):
        on_create(None, page)

    # 初始化时直接填充 controls
    if not all_cases:
        case_list.controls.append(
            ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.FOLDER_OPEN, size=48, color='#BDBDBD'),
                    ft.Text('暂无案例', color='#9E9E9E', size=14),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=40,
                alignment=ft.Alignment.CENTER,
            )
        )
    else:
        for c in all_cases:
            case_list.controls.append(_build_case_card(c, page, on_edit, refresh_list))

    return ft.Column([
        ft.Row([
            ft.Text('案例管理', size=22, weight=ft.FontWeight.BOLD, color='#1565C0'),
            ft.ElevatedButton(
                content='创建案例',
                icon=ft.Icons.ADD,
                on_click=handle_create,
                style=ft.ButtonStyle(
                    bgcolor='#1976D2',
                    color='white',
                    shape=ft.RoundedRectangleBorder(radius=8),
                ),
            ),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        ft.Divider(height=10, color='transparent'),
        ft.Row([case_dropdown], spacing=10),
        ft.Divider(height=10, color='transparent'),
        case_list,
    ], expand=True, spacing=0)


def _build_case_card(case: dict, page: ft.Page, on_edit, on_refresh) -> ft.Container:
    """构建案例卡片"""
    question_count = len(get_questions_by_case(case['id']))

    return ft.Container(
        content=ft.Row([
            ft.Column([
                ft.Text(case['title'], size=15, weight=ft.FontWeight.W_500, color='#212121'),
                ft.Row([
                    ft.Container(
                        content=ft.Text(case['theme'], size=11, color='white'),
                        bgcolor='#1976D2',
                        border_radius=12,
                        padding=ft.Padding(10, 3, 10, 3),
                    ),
                    ft.Text(f'{question_count} 道题目', size=12, color='#9E9E9E'),
                ], spacing=8),
            ], spacing=4, expand=True),
            ft.PopupMenuButton(
                icon=ft.Icons.MORE_VERT,
                items=[
                    ft.PopupMenuItem(
                        content=ft.Text('编辑'),
                        icon=ft.Icons.EDIT,
                        on_click=lambda e, cid=case['id']: on_edit(cid, page),
                    ),
                    ft.PopupMenuItem(
                        content=ft.Text('删除'),
                        icon=ft.Icons.DELETE,
                        on_click=lambda e, c=case: _confirm_delete(c, page, on_refresh),
                    ),
                ],
            ),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        bgcolor='white',
        border_radius=12,
        padding=16,
        shadow=ft.BoxShadow(spread_radius=0.5, blur_radius=8, color='#00000015'),
    )


def _confirm_delete(case: dict, page: ft.Page, on_refresh):
    """确认删除案例对话框"""
    def do_delete(e):
        try:
            result = delete_case(case['id'])
        except Exception as ex:
            page.overlay.remove(dlg)
            snack = ft.SnackBar(ft.Text(f'删除失败: {ex}'), bgcolor='#FF5252')
            page.overlay.append(snack)
            snack.open = True
            page.update()
            return
        ##page.overlay.remove(dlg)
        dlg.open = False
        if result['success']:
            snack = ft.SnackBar(ft.Text(result['message']), bgcolor='#4CAF50')
            page.overlay.append(snack)
            snack.open = True
            page.update()
            on_refresh()
        else:
            snack = ft.SnackBar(ft.Text(result['message']), bgcolor='#FF5252')
            page.overlay.append(snack)
            snack.open = True
            page.update()

    def cancel(e):
        ##page.overlay.remove(dlg)
        dlg.open = False
        page.update()

    dlg = ft.AlertDialog(
        title=ft.Text('确认删除'),
        content=ft.Text(f'确定要删除案例「{case["title"]}」吗？此操作不可撤销。'),
        actions=[
            ft.TextButton(content='取消', on_click=cancel),
            ft.ElevatedButton(content='确认删除', on_click=do_delete,
                              style=ft.ButtonStyle(bgcolor='#FF5252', color='white')),
        ],
        modal=True,
    )
    page.overlay.append(dlg)
    dlg.open = True
    page.update()


def build_case_editor_view(page: ft.Page, case_id: int = None, on_back=None) -> list:
    """案例编辑器视图（创建/编辑）"""

    is_edit = case_id is not None
    case_data = get_case(case_id) if is_edit else None

    # 表单字段
    title_field = ft.TextField(
        label='案例标题',
        value=case_data['title'] if case_data else '',
        prefix_icon=ft.Icons.TITLE,
        border_color='#BBDEFB',
        focused_border_color='#1976D2',
    )

    # 题目列表区
    questions = case_data['questions'] if case_data else []
    question_container = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)

    def refresh_questions():
        nonlocal questions
        if case_id:
            questions = get_questions_by_case(case_id)
        question_container.controls.clear()
        for i, q in enumerate(questions):
            question_container.controls.append(_build_question_card(q, i, refresh_questions, questions, refresh_single_question))
        if question_container.page:
            question_container.update()

    def refresh_single_question(index: int):
        """只重建单个题目卡片，不丢失其他题目的编辑内容"""
        q = questions[index]
        question_container.controls[index] = _build_question_card(q, index, refresh_questions, questions, refresh_single_question)
        if question_container.page:
            question_container.update()

    def add_question_handler(e):
        # 添加默认单选题，题目标题默认为空，1个选项
        if is_edit and case_id:
            result = add_question(case_id, '', 'single_choice', options=['选项A'], sort_order=len(questions))
            if result['success']:
                new_q = {'id': result['question_id'], 'case_id': case_id, 'question_text': '', 
                         'question_type': 'single_choice', 'options': ['选项A'], 'sort_order': len(questions), 'is_new': False, 'hint': ''}
                questions.append(new_q)
                question_container.controls.append(_build_question_card(new_q, len(questions) - 1, refresh_questions, questions, refresh_single_question))
                if question_container.page:
                    question_container.update()
        else:
            # 新建模式暂存到 questions 列表
            new_q = {
                'id': -len(questions) - 1,  # 临时ID
                'case_id': case_id,
                'question_text': '',
                'question_type': 'single_choice',
                'options': ['选项A'],
                'sort_order': len(questions),
                'is_new': True,
                'hint': '',
            }
            questions.append(new_q)
            question_container.controls.append(_build_question_card(new_q, len(questions) - 1, refresh_questions, questions, refresh_single_question))
            if question_container.page:
                question_container.update()

    def _read_question_from_ui(card) -> dict:
        """从题目的 UI 卡片控件中读取实际值
        
        UI 结构: Container.content = Column(controls=[Row(badge), Row(title+type), Divider, options_col, Divider, hint_field])
        """
        card_col = card.content
        if not isinstance(card_col, ft.Column) or len(card_col.controls) < 2:
            return None
        # controls[1] = Row([question_text_field, type_dropdown])
        title_row = card_col.controls[1]
        if not isinstance(title_row, ft.Row) or len(title_row.controls) < 2:
            return None
        q_title_field = title_row.controls[0]
        q_type_dropdown = title_row.controls[1]
        title_val = (q_title_field.value or '').strip() if isinstance(q_title_field, ft.TextField) else ''
        type_val = q_type_dropdown.value if isinstance(q_type_dropdown, ft.Dropdown) else 'single_choice'
        # controls[3] = options_column
        opts = []
        if type_val != 'open' and len(card_col.controls) > 3:
            options_col = card_col.controls[3]
            if isinstance(options_col, ft.Column):
                for opt_ctrl in options_col.controls:
                    if isinstance(opt_ctrl, ft.Row) and opt_ctrl.controls:
                        opt_field = opt_ctrl.controls[0]
                        if isinstance(opt_field, ft.TextField):
                            opts.append((opt_field.value or '').strip())
        # Find hint field (key='hint_field')
        hint_val = ''
        for ctrl in card_col.controls:
            if isinstance(ctrl, ft.TextField) and hasattr(ctrl, 'key') and ctrl.key == 'hint_field':
                hint_val = (ctrl.value or '').strip()
                break
        return {'title': title_val, 'type': type_val, 'options': opts, 'hint': hint_val}

    def _show_sn(msg: str, success: bool = True):
        snack = ft.SnackBar(ft.Text(msg), bgcolor='#4CAF50' if success else '#FF5252')
        page.overlay.append(snack)
        snack.open = True
        page.update()

    def save_case(e):
        title = title_field.value.strip()

        if not title:
            _show_sn('请填写案例标题', False)
            return

        # 校验题目标题不能为空 - 直接从 UI 控件中读取实际值
        for card in question_container.controls:
            q_data = _read_question_from_ui(card)
            if q_data and not q_data['title']:
                _show_sn('请完善所有题目的标题', False)
                return

        try:
            if is_edit:
                result = update_case(case_id, title, '', '')
                # 编辑模式：从 UI 控件读取题目数据并保存到数据库
                if result['success']:
                    for idx, card in enumerate(question_container.controls):
                        q = questions[idx] if idx < len(questions) else None
                        if q is None:
                            continue
                        q_data = _read_question_from_ui(card)
                        if not q_data:
                            continue
                        # 从 UI 重新获取题目标题和选项
                        new_title = q_data['title']
                        new_type = q_data['type']
                        new_options = q_data['options'] if q_data['options'] else None
                        new_hint = q_data.get('hint', '') or None

                        if q.get('is_new', False):
                            # 新增的题目：先插入数据库
                            add_result = add_question(case_id, new_title, new_type,
                                                      options=new_options, sort_order=idx, hint=new_hint)
                            if add_result['success']:
                                q['id'] = add_result['question_id']
                                q['is_new'] = False
                        else:
                            # 已有的题目：直接更新
                            update_question(q['id'], new_title, new_type, options=new_options, hint=new_hint)
            else:
                user = page.session.store.get('user')
                result = create_case(title, '', '', user['id'])
                new_case_id = result.get('case_id')

                # 创建新案例后处理题目 - 从 UI 控件读取
                if result['success'] and new_case_id:
                    for idx, card in enumerate(question_container.controls):
                        q_data = _read_question_from_ui(card)
                        if q_data and q_data['title']:
                            add_question(new_case_id, q_data['title'], q_data['type'], 
                                        options=q_data['options'] if q_data['options'] else [],
                                        sort_order=idx, hint=q_data.get('hint', '') or None)

            if result['success']:
                # 将成功消息存入 session，由列表页读取并显示
                page.session.store.set('_case_save_message', result['message'])
                if on_back:
                    on_back()
            else:
                _show_sn(result['message'], False)
        except Exception as ex:
            _show_sn(f'保存失败: {ex}', False)

    # 初始构建题目卡片（不调用 update，待页面渲染后自动显示）
    for i, q in enumerate(questions):
        question_container.controls.append(
            _build_question_card(q, i, refresh_questions, questions, refresh_single_question)
        )

    # 返回按钮
    back_btn = ft.IconButton(
        icon=ft.Icons.ARROW_BACK,
        icon_color='#1565C0',
        on_click=lambda e: on_back() if on_back else None,
    )

    return [
        ft.Column([
            ft.Row([
                back_btn,
                ft.Text('编辑案例' if is_edit else '创建案例', size=22, weight=ft.FontWeight.BOLD, color='#1565C0'),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(height=15, color='transparent'),
            ft.Container(
                content=ft.Column([
                    ft.Text('基本信息', size=16, weight=ft.FontWeight.W_500, color='#212121'),
                    ft.Divider(height=5, color='transparent'),
                    title_field,
                ], spacing=8),
                bgcolor='white',
                border_radius=12,
                padding=20,
                shadow=ft.BoxShadow(spread_radius=0.5, blur_radius=8, color='#00000015'),
            ),
            ft.Divider(height=15, color='transparent'),
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Text('题目列表', size=16, weight=ft.FontWeight.W_500, color='#212121'),
                        ft.Text(f'共 {len(questions)} 题', size=13, color='#9E9E9E'),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Divider(height=5, color='transparent'),
                    question_container,
                    ft.Divider(height=5, color='transparent'),
                    ft.OutlinedButton(
                        content='添加题目',
                        icon=ft.Icons.ADD,
                        on_click=add_question_handler,
                        style=ft.ButtonStyle(
                            shape=ft.RoundedRectangleBorder(radius=8),
                            side=ft.BorderSide(1, '#1976D2'),
                        ),
                    ),
                ], spacing=8),
                bgcolor='white',
                border_radius=12,
                padding=20,
                shadow=ft.BoxShadow(spread_radius=0.5, blur_radius=8, color='#00000015'),
                expand=True,
            ),
            ft.Divider(height=15, color='transparent'),
            ft.Container(
                content=ft.Row([
                    ft.ElevatedButton(
                        content='保存案例',
                        icon=ft.Icons.SAVE,
                        on_click=save_case,
                        style=ft.ButtonStyle(
                            bgcolor='#1976D2',
                            color='white',
                            shape=ft.RoundedRectangleBorder(radius=8),
                            padding=ft.Padding(40, 15, 40, 15),
                        ),
                    ),
                ], alignment=ft.MainAxisAlignment.END),
            ),
        ], expand=True, spacing=0, scroll=ft.ScrollMode.AUTO),
    ]


def _build_question_card(question: dict, index: int, on_refresh, temp_questions=None, on_single_refresh=None) -> ft.Container:
    """构建题目编辑卡片"""
    qid = question['id']
    is_new = question.get('is_new', False)

    type_map = {
        'single_choice': '单选题',
        'multiple_choice': '多选题',
        'open': '开放题'
    }
    type_display = type_map.get(question['question_type'], '')

    question_text_field = ft.TextField(
        value=question['question_text'],
        label=f'题目 {index + 1}',
        border_color='#E0E0E0',
        focused_border_color='#1976D2',
        expand=True,
        on_change=lambda e, q=qid: _on_question_text_change(q, e.control.value, temp_questions),
    )

    type_dropdown = ft.Dropdown(
        value=question['question_type'],
        options=[
            ft.DropdownOption(key='single_choice', text='单选题'),
            ft.DropdownOption(key='multiple_choice', text='多选题'),
            ft.DropdownOption(key='open', text='开放题'),
        ],
        border_color='#E0E0E0',
        width=130,
        on_select=lambda e, q=qid, idx=index: _on_question_type_change(q, e.control.value, idx, temp_questions, on_single_refresh),
    )

    # 选项编辑器（仅单选和多选显示）
    options_column = ft.Column(spacing=4)

    def build_options():
        options_column.controls.clear()
        if question['question_type'] in ('single_choice', 'multiple_choice'):
            opts = question.get('options', [])
            for i, opt in enumerate(opts):
                opt_field = ft.Row([
                    ft.TextField(
                        value=opt,
                        dense=True,
                        border_color='#E0E0E0',
                        expand=True,
                        on_change=lambda e, idx=i, q=qid: _on_option_change(q, idx, e.control.value, temp_questions),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
                        icon_color='#FF5252',
                        icon_size=20,
                        on_click=lambda e, idx=i, q=qid: _remove_option(q, idx, on_refresh, temp_questions),
                    ),
                ], spacing=4)
                options_column.controls.append(opt_field)
            # 添加选项按钮
            options_column.controls.append(
                ft.TextButton(
                    content='添加选项', icon=ft.Icons.ADD,
                    on_click=lambda e, q=qid: _add_option(q, on_refresh, temp_questions),
                    style=ft.ButtonStyle(color='#1976D2'),
                )
            )
        else:
            options_column.controls.append(
                ft.TextField(
                    value='请在此输入您的答案',
                    multiline=True,
                    min_lines=3,
                    max_lines=8,
                    read_only=True,
                    border_color='#E0E0E0',
                    text_style=ft.TextStyle(color='#BDBDBD', italic=True),
                )
            )

    build_options()

    hint_field = ft.TextField(
        value=question.get('hint', ''),
        label='作答提示（选填）',
        hint_text='为作答者提供提示信息',
        border_color='#E0E0E0',
        focused_border_color='#1976D2',
        text_style=ft.TextStyle(size=12),
        dense=True,
        key='hint_field',
    )

    delete_btn = ft.IconButton(
        icon=ft.Icons.DELETE,
        icon_color='#FF5252',
        on_click=lambda e, q=qid: _delete_question_handler(q, is_new, on_refresh, temp_questions),
    )

    return ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Container(
                    content=ft.Text(type_display, size=11, color='white'),
                    bgcolor='#1976D2',
                    border_radius=10,
                    padding=ft.Padding(8, 2, 8, 2),
                ),
                ft.Container(expand=True),
                delete_btn,
            ], spacing=8),
            ft.Row([question_text_field, type_dropdown], spacing=10),
            ft.Divider(height=5, color='transparent'),
            options_column,
            ft.Divider(height=5, color='transparent'),
            hint_field,
        ], spacing=6),
        bgcolor='#FAFAFA',
        border_radius=10,
        border=ft.Border.all(width=1, color='#E8E8E8'),
        padding=14,
    )


# --- 题目编辑辅助函数 ---

def _on_question_text_change(question_id: int, new_text: str, temp_questions=None):
    """题目文本变更"""
    if question_id > 0:
        # 从 temp_questions 获取原题目的 question_type、options 和 hint，避免覆盖为 NULL
        qtype = None
        qopts = None
        qhint = None
        if temp_questions:
            for q in temp_questions:
                if q['id'] == question_id:
                    qtype = q.get('question_type')
                    qopts = q.get('options')
                    qhint = q.get('hint')
                    q['question_text'] = new_text
                    break
        update_question(question_id, new_text, qtype, qopts, hint=qhint)
    else:
        # 新建模式，只更新内存中的题目列表
        if temp_questions:
            for q in temp_questions:
                if q['id'] == question_id:
                    q['question_text'] = new_text
                    break


def _on_question_type_change(question_id: int, new_type: str, question_index: int, 
                            temp_questions, on_single_refresh):
    """题目类型变更 - 只重建当前题目卡片"""
    if question_id > 0:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT question_text, options, hint FROM case_questions WHERE id = :qid", {'qid': question_id})
            row = cursor.fetchone()
            if row:
                if new_type == 'single_choice':
                    opts = ['选项A']
                elif new_type == 'multiple_choice':
                    opts = ['选项A', '选项B']
                else:
                    opts = None
                update_question(question_id, row[0], new_type, options=opts, hint=row[2])
        # 更新内存中的题目数据
        for q in temp_questions:
            if q['id'] == question_id:
                q['question_type'] = new_type
                if new_type == 'single_choice':
                    q['options'] = ['选项A']
                elif new_type == 'multiple_choice':
                    q['options'] = ['选项A', '选项B']
                else:
                    q['options'] = []
                break
    elif temp_questions:
        for q in temp_questions:
            if q['id'] == question_id:
                q['question_type'] = new_type
                if new_type == 'single_choice':
                    q['options'] = ['选项A']
                elif new_type == 'multiple_choice':
                    q['options'] = ['选项A', '选项B']
                else:
                    q['options'] = []
                break
    # 只重建当前卡片（延迟执行，避免在事件处理中销毁控件）
    if on_single_refresh:
        threading.Timer(0.05, lambda: on_single_refresh(question_index)).start()


def _on_option_change(question_id: int, option_idx: int, new_value: str, temp_questions=None):
    """选项文本变更"""
    if question_id > 0:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT question_text, question_type, options, hint FROM case_questions WHERE id = :qid", {'qid': question_id})
            row = cursor.fetchone()
            if row and row[2]:
                opts = json.loads(row[2])
                if option_idx < len(opts):
                    opts[option_idx] = new_value
                    update_question(question_id, row[0], row[1], options=opts, hint=row[3])
    # 无论新建还是编辑模式，都要更新内存中的题目列表
    if temp_questions:
        for q in temp_questions:
            if q['id'] == question_id:
                opts = q.get('options', [])
                if option_idx < len(opts):
                    opts[option_idx] = new_value
                    q['options'] = opts
                break


def _add_option(question_id: int, on_refresh, temp_questions=None):
    """添加选项"""
    if question_id > 0:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT question_text, question_type, options, hint FROM case_questions WHERE id = :qid", {'qid': question_id})
            row = cursor.fetchone()
            if row:
                opts = json.loads(row[2]) if row[2] else []
                opts.append(f'选项{chr(65 + len(opts))}')  # 选项A, B, C...
                update_question(question_id, row[0], row[1], options=opts, hint=row[3])
    elif temp_questions:
        # 新建模式：更新临时 questions 列表
        for q in temp_questions:
            if q['id'] == question_id:
                opts = q.get('options', [])
                opts.append(f'选项{chr(65 + len(opts))}')
                q['options'] = opts
                break
    threading.Timer(0.05, on_refresh).start()


def _remove_option(question_id: int, option_idx: int, on_refresh, temp_questions=None):
    """删除选项"""
    if question_id > 0:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT question_text, question_type, options, hint FROM case_questions WHERE id = :qid", {'qid': question_id})
            row = cursor.fetchone()
            if row and row[2]:
                opts = json.loads(row[2])
                if option_idx < len(opts):
                    opts.pop(option_idx)
                    update_question(question_id, row[0], row[1], options=opts, hint=row[3])
    elif temp_questions:
        for q in temp_questions:
            if q['id'] == question_id:
                opts = q.get('options', [])
                if option_idx < len(opts):
                    opts.pop(option_idx)
                    q['options'] = opts
                break
    threading.Timer(0.05, on_refresh).start()


def _delete_question_handler(question_id: int, is_new: bool, on_refresh, temp_questions=None):
    """删除题目"""
    if question_id > 0 and not is_new:
        delete_question(question_id)
    elif temp_questions:
        # 新建模式：从临时列表中移除
        temp_questions[:] = [q for q in temp_questions if q['id'] != question_id]
    threading.Timer(0.05, on_refresh).start()
