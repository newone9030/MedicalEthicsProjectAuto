"""
问卷作答视图
"""

import json
import flet as ft
from app.task.task_service import get_task
from app.case.question_service import get_questions_by_case
from app.response.response_service import save_draft, submit_response, get_draft_answers, get_submitted_answers


def build_survey_taker_view(page: ft.Page, task_id: int, on_back=None, readonly: bool = False) -> list:
    """问卷作答视图"""
    user = page.session.store.get('user')
    student_id = user['id']
    task = get_task(task_id)

    if not task:
        return [ft.Text('任务不存在', color='#FF5252')]

    cases = task['cases']
    if not cases:
        return [ft.Text('该任务没有关联案例', color='#FF5252')]

    current_case_idx = [0]  # 使用 list 作为可变 int 容器，避免 ft.Ref[int] 弱引用错误

    # 收集所有题目和答案
    all_questions_map = {}  # case_id -> [questions]
    all_answers = {}  # key: "case_id_qid" or composite
    not_submitted_case_ids = set()

    # 加载所有案例的题目和暂存答案
    for case in cases:
        qs = get_questions_by_case(case['id'])
        all_questions_map[case['id']] = qs

        # 加载答案：只读模式加载已提交答案，否则加载暂存答案
        if readonly:
            saved = get_submitted_answers(task_id, case['id'], student_id)
        else:
            saved = get_draft_answers(task_id, case['id'], student_id)
        for qid, ans in saved.items():
            all_answers[f"{case['id']}_{qid}"] = ans

        # 检查提交状态 - 只显示未提交的
        from app.response.response_service import get_submission_status
        statuses = get_submission_status(task_id, student_id)
        if statuses.get(case['id']) != 'submitted':
            not_submitted_case_ids.add(case['id'])

    # 如果只读模式，所有案例都标记为已提交
    if readonly:
        not_submitted_case_ids.clear()

    # 筛选未提交案例
    active_cases = [c for c in cases if c['id'] in not_submitted_case_ids] if not readonly else cases

    if not active_cases:
        return [
            ft.Column([
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.CHECK_CIRCLE, size=64, color='#4CAF50'),
                        ft.Text('所有案例已提交', size=20, weight=ft.FontWeight.BOLD, color='#4CAF50'),
                        ft.TextButton('返回', on_click=lambda e: on_back() if on_back else None),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                    padding=60,
                    alignment=ft.Alignment.CENTER,
                    expand=True,
                )
            ], expand=True),
        ]

    # --- 初始化第一个案例的数据 ---
    first_case = active_cases[0]
    first_questions = all_questions_map.get(first_case['id'], [])
    initial_question_widgets = [
        _build_question_widget(q, f"{first_case['id']}_{q['id']}", all_answers, readonly)
        for q in first_questions
    ]
    is_single_case = len(active_cases) == 1

    # --- UI 组件（带初始值，避免控件挂载前调用 refresh_ui）---
    progress_bar = ft.ProgressBar(
        value=(0 + 0.5) / len(active_cases) if first_questions else 0,
        bgcolor='#E0E0E0', color='#1976D2', height=8,
    )
    case_title = ft.Text(
        f'案例 1/{len(active_cases)}: {first_case["title"]}',
        size=18, weight=ft.FontWeight.BOLD, color='#212121',
    )
    question_area = ft.Column(
        initial_question_widgets, spacing=16, scroll=ft.ScrollMode.AUTO, expand=True,
    )
    if readonly:
        prev_btn_visible, next_btn_visible, submit_btn_visible, save_draft_visible = \
            False, (not is_single_case), False, False
    else:
        prev_btn_visible, next_btn_visible, submit_btn_visible, save_draft_visible = \
            False, (not is_single_case), is_single_case, True

    prev_btn = ft.ElevatedButton(content='上一案例', icon=ft.Icons.ARROW_BACK, visible=prev_btn_visible,
                                  style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)))
    next_btn = ft.ElevatedButton(content='下一案例', icon=ft.Icons.ARROW_FORWARD,
                                  visible=next_btn_visible,
                                  style=ft.ButtonStyle(bgcolor='#1976D2', color='white', shape=ft.RoundedRectangleBorder(radius=8)))
    submit_btn = ft.ElevatedButton(content='提交全部案例', icon=ft.Icons.CHECK, visible=submit_btn_visible,
                                    style=ft.ButtonStyle(bgcolor='#4CAF50', color='white', shape=ft.RoundedRectangleBorder(radius=8)))
    save_draft_btn = ft.OutlinedButton(content='暂存', icon=ft.Icons.SAVE_OUTLINED,
                                        visible=save_draft_visible,
                                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)))

    def refresh_ui():
        """刷新当前案例的题目显示"""
        if current_case_idx[0] >= len(active_cases):
            return
        case = active_cases[current_case_idx[0]]
        questions = all_questions_map.get(case['id'], [])

        case_title.value = f'案例 {current_case_idx[0] + 1}/{len(active_cases)}: {case["title"]}'
        progress_bar.value = (current_case_idx[0] + 0.5) / len(active_cases) if questions else 0

        question_area.controls.clear()
        for q in questions:
            question_area.controls.append(_build_question_widget(q, f"{case['id']}_{q['id']}", all_answers, readonly))

        # 按钮状态
        prev_btn.visible = current_case_idx[0] > 0
        is_last = current_case_idx[0] >= len(active_cases) - 1
        next_btn.visible = not is_last
        submit_btn.visible = is_last

        if readonly:
            save_draft_btn.visible = False
            submit_btn.visible = False
            next_btn.text = '下一案例'
            next_btn.visible = not is_last

        [c.update() for c in [case_title, progress_bar, question_area, prev_btn, next_btn, submit_btn, save_draft_btn]]

    def go_prev(e):
        if current_case_idx[0] > 0:
            current_case_idx[0] -= 1
            refresh_ui()

    def go_next(e):
        if current_case_idx[0] < len(active_cases) - 1:
            current_case_idx[0] += 1
            refresh_ui()

    def _show_snack(msg: str, success: bool = True):
        snack = ft.SnackBar(ft.Text(msg), bgcolor='#4CAF50' if success else '#FF5252')
        page.overlay.append(snack)
        snack.open = True
        page.update()

    def _close_overlay_dlg(dialog):
        ##page.overlay.remove(dialog)
        dialog.open = False
        page.update()

    def handle_save_draft(e):
        """暂存当前案例"""
        case = active_cases[current_case_idx[0]]
        case_answers = {}
        for key, val in all_answers.items():
            if key.startswith(f"{case['id']}_"):
                qid_str = key.split('_', 1)[1]
                try:
                    qid = int(qid_str)
                except ValueError:
                    qid = qid_str
                case_answers[qid] = val

        result = save_draft(task_id, case['id'], student_id, case_answers)
        _show_snack(result['message'], result['success'])

    def handle_submit(e):
        """一次性提交所有案例"""
        # 1. 收集所有案例的答案，检查未完成项
        all_cases_data = {}  # case_id -> {'answers': dict, 'qids': list}
        all_unanswered = []  # [(case_title, question_text), ...]

        for case in active_cases:
            questions = all_questions_map.get(case['id'], [])
            qids = [q['id'] for q in questions]
            case_answers = {}
            case_unanswered = []
            for q in questions:
                key = f"{case['id']}_{q['id']}"
                ans = all_answers.get(key)
                if ans is None or ans == '' or (isinstance(ans, list) and len(ans) == 0):
                    case_unanswered.append((case['title'], q['question_text'][:30]))
                else:
                    case_answers[q['id']] = ans
            all_cases_data[case['id']] = {'answers': case_answers, 'qids': qids}
            all_unanswered.extend(case_unanswered)

        if all_unanswered:
            # 显示所有未完成题目（按案例分组）
            lines = []
            for case_title, qtext in all_unanswered[:8]:
                lines.append(f'• [{case_title}] {qtext}')
            if len(all_unanswered) > 8:
                lines.append(f'... 及其他 {len(all_unanswered) - 8} 题')
            dlg = ft.AlertDialog(
                title=ft.Text('请完成所有题目'),
                content=ft.Text(f'以下 {len(all_unanswered)} 道题尚未作答：\n\n' + '\n'.join(lines)),
                actions=[ft.TextButton('知道了', on_click=lambda e: _close_overlay_dlg(dlg))],
                modal=True,
            )
            page.overlay.append(dlg)
            dlg.open = True
            page.update()
            return

        # 2. 确认提交对话框（一次性提交所有案例）
        def do_submit_all(e2):
            _close_overlay_dlg(confirm_dlg)

            success_count = 0
            for case in active_cases:
                data = all_cases_data[case['id']]
                result = submit_response(task_id, case['id'], student_id, data['answers'], data['qids'])
                if result['success']:
                    success_count += 1
                    not_submitted_case_ids.discard(case['id'])
                else:
                    _show_snack(f'案例「{case["title"]}」提交失败: {result["message"]}', False)

            if success_count == len(active_cases):
                _show_snack(f'全部 {success_count} 个案例已提交完成！')
                if on_back:
                    on_back()
            elif success_count > 0:
                _show_snack(f'已提交 {success_count}/{len(active_cases)} 个案例，请重试失败的案例')
                # 过滤已提交成功的案例，就地更新列表
                active_cases[:] = [c for c in active_cases if c['id'] in not_submitted_case_ids]
                if not active_cases:
                    _show_snack('所有案例已提交完成！')
                    if on_back:
                        on_back()
                    return
                if current_case_idx[0] >= len(active_cases):
                    current_case_idx[0] = max(0, len(active_cases) - 1)
                refresh_ui()

        confirm_dlg = ft.AlertDialog(
            title=ft.Text('确认提交全部案例'),
            content=ft.Text(f'将一次性提交 {len(active_cases)} 个案例的所有作答，提交后将无法修改。\n\n确定要提交吗？'),
            actions=[
                ft.TextButton(content='取消', on_click=lambda e: _close_overlay_dlg(confirm_dlg)),
                ft.ElevatedButton(content='确认提交全部', on_click=do_submit_all,
                                  style=ft.ButtonStyle(bgcolor='#4CAF50', color='white')),
            ],
            modal=True,
        )
        page.overlay.append(confirm_dlg)
        confirm_dlg.open = True
        page.update()

    # 绑定按钮事件
    prev_btn.on_click = go_prev
    next_btn.on_click = go_next
    submit_btn.on_click = handle_submit
    save_draft_btn.on_click = handle_save_draft

    return [
        ft.Column([
            ft.Row([
                ft.IconButton(icon=ft.Icons.ARROW_BACK, icon_color='#1565C0',
                              on_click=lambda e: on_back() if on_back else None),
                ft.Text(task['name'], size=20, weight=ft.FontWeight.BOLD, color='#1565C0'),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(height=10, color='transparent'),
            progress_bar,
            ft.Divider(height=10, color='transparent'),
            case_title,
            ft.Divider(height=10, color='transparent'),
            ft.Container(
                content=question_area,
                bgcolor='white',
                border_radius=12,
                padding=20,
                shadow=ft.BoxShadow(spread_radius=0.5, blur_radius=8, color='#00000015'),
                expand=True,
            ),
            ft.Divider(height=15, color='transparent'),
            ft.Row([
                save_draft_btn,
                ft.Container(expand=True),
                prev_btn,
                next_btn,
                submit_btn,
            ], spacing=10, alignment=ft.MainAxisAlignment.END),
        ], expand=True, spacing=0),
    ]


def _build_question_widget(question: dict, key_prefix: str, answers: dict, readonly: bool) -> ft.Container:
    """构建单个题目组件"""
    qid = question['id']
    qtype = question['question_type']
    key = f"{key_prefix.split('_')[0]}_{qid}"
    current_val = answers.get(key)

    is_unanswered = not readonly and (
        current_val is None or current_val == '' or
        (isinstance(current_val, list) and len(current_val) == 0)
    )
    border_color = '#FF5252' if is_unanswered else '#E0E0E0'

    def on_answer_change(val):
        answers[key] = val

    if qtype == 'single_choice':
        opts = question.get('options', [])
        if not opts:
            content = ft.Text('(无选项)', size=13, color='#9E9E9E', italic=True)
        else:
            radio = ft.RadioGroup(
                value=current_val,
                on_change=lambda e: on_answer_change(e.control.value),
                content=ft.Column([
                    ft.Radio(value=opt, label=opt, fill_color='#1976D2')
                    for opt in opts
                ], spacing=6),
            )
            if readonly:
                radio.disabled = True
            content = radio

    elif qtype == 'multiple_choice':
        opts = question.get('options', [])
        if not opts:
            content = ft.Text('(无选项)', size=13, color='#9E9E9E', italic=True)
        else:
            selected = current_val if isinstance(current_val, list) else []
            checks = []
            for opt in opts:
                cb = ft.Checkbox(
                    label=opt, value=opt in selected,
                    fill_color='#1976D2',
                    on_change=lambda e, o=opt, s=selected: _toggle_checkbox(o, s, key, answers),
                )
                if readonly:
                    cb.disabled = True
                checks.append(cb)
            content = ft.Column(checks, spacing=4)

    elif qtype == 'open':
        tf = ft.TextField(
            value=current_val or '',
            multiline=True,
            min_lines=3,
            max_lines=6,
            hint_text='请输入您的回答...',
            border_color='#BBDEFB',
            focused_border_color='#1976D2',
            on_change=lambda e: on_answer_change(e.control.value),
        )
        if readonly:
            tf.read_only = True
        content = tf

    else:
        content = ft.Text(f'未知题型: {qtype}', color='#FF5252')

    type_labels = {'single_choice': '单选题', 'multiple_choice': '多选题', 'open': '开放题'}
    type_label = type_labels.get(qtype, qtype)

    # 构建 column 子控件列表
    column_controls = []
    column_controls.append(
        ft.Row([
            ft.Container(
                content=ft.Text(type_label, size=11, color='white'),
                bgcolor='#1976D2', border_radius=10,
                padding=ft.Padding(8, 2, 8, 2),
            ),
            ft.Container(width=8, height=8, border_radius=4, bgcolor='#FF5252' if is_unanswered else 'transparent'),
        ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
    )
    column_controls.append(ft.Divider(height=4, color='transparent'))
    column_controls.append(ft.Text(question['question_text'], size=14, weight=ft.FontWeight.W_500, color='#212121'))

    hint = (question.get('hint') or '').strip()
    if hint:
        hint_lines = [l.strip() for l in hint.split('\n') if l.strip()]
        if hint_lines:
            column_controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Icon(ft.Icons.LIGHTBULB_OUTLINE, size=14, color='#FF8F00'),
                            ft.Text('作答提示', size=12, color='#FF8F00', weight=ft.FontWeight.W_600),
                        ], spacing=4),
                        *[ft.Text(f'{i}. {line}', size=12, color='#FF8F00', italic=True)
                          for i, line in enumerate(hint_lines, 1)],
                    ], spacing=2),
                    bgcolor='#FFF8E1',
                    border_radius=8,
                    padding=ft.Padding(10, 8, 10, 8),
                )
            )

    column_controls.append(ft.Divider(height=8, color='transparent'))
    column_controls.append(content)

    return ft.Container(
        content=ft.Column(column_controls, spacing=0),
        bgcolor='#FAFAFA',
        border_radius=10,
        border=ft.Border.all(width=1, color=border_color),
        padding=16,
    )


def _toggle_checkbox(option: str, selected: list, key: str, answers: dict):
    if option in selected:
        selected.remove(option)
    else:
        selected.append(option)
    answers[key] = selected[:]
