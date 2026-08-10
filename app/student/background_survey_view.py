"""
背景资料问卷页面

学生在知情同意后、进入仪表盘前必须完成的背景资料问卷。
基于任务和案例体系构建，支持暂存和提交流程。

所有数据在构建控件前同步加载完毕，确保控件生成时已具备完整数据，
避免“Control must be added to the page first”错误。
"""

import json

import flet as ft
from typing import Callable

from app.response.response_service import (
    get_draft_answers,
    save_draft,
    submit_response,
)
from app.case.question_service import get_questions_by_case


def build_background_survey_view(
    page: ft.Page,
    on_navigate_dashboard: Callable,
    on_logout: Callable,
    student_id: int,
    student_name: str,
    task: dict,
) -> ft.View:
    """
    构建背景资料问卷页面（同步加载）

    数据在控件创建前加载完毕，所有控件创建时已包含草稿数据，
    页面返回后无需任何异步初始化。
    """
    cases = task['cases']

    # ---- 共用引用容器 ----
    question_fields = {}  # {case_id: [{qid, question_text, hint, answer_text, explanation, ...}, ...]}

    # ================================================================
    # 第一步：同步加载所有数据（在任何控件创建之前）
    # ================================================================
    for case in cases:
        questions = get_questions_by_case(case['id'])
        drafts = get_draft_answers(task['id'], case['id'], student_id)
        case_question_data = []
        for q in questions:
            qid = q['id']
            qtype = q['question_type']
            options = q.get('options', [])
            score_ctrl = ft.Text(value='', size=14, color='#9E9E9E')

            # 解析草稿答案
            draft_info = {}
            qid_str = str(qid)
            raw = drafts.get(qid_str) or drafts.get(qid)
            if raw:
                try:
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        draft_info = {
                            'answer': data.get('answer', ''),
                            'explanation': data.get('explanation', ''),
                        }
                except (json.JSONDecodeError, TypeError):
                    draft_info = {'answer': str(raw) if raw else '', 'explanation': ''}

            if qtype == 'single_choice':
                radio_items = []
                for opt in options:
                    radio = ft.Radio(value=opt, label=opt, fill_color='#1976D2')
                    radio_items.append(radio)

                draft_answer = draft_info.get('answer', '')
                rg = ft.RadioGroup(
                    value=draft_answer or '',
                    content=ft.Column(radio_items, spacing=4),
                )

                answer_ctrl = rg
                answer_items_list = radio_items
                explanation_ctrl = None
                choice_controls = []
            elif qtype == 'multiple_choice':
                draft_answer = draft_info.get('answer', '')
                if isinstance(draft_answer, str):
                    try:
                        draft_answer = json.loads(draft_answer)
                    except json.JSONDecodeError:
                        draft_answer = [draft_answer] if draft_answer else []
                if not isinstance(draft_answer, list):
                    draft_answer = []

                checkboxes = {}
                check_items = []
                for opt in options:
                    cb = ft.Checkbox(value=opt in draft_answer, fill_color='#1976D2')
                    checkboxes[opt] = cb
                    bg_container = ft.Container(
                        content=ft.Row([
                            cb,
                            ft.Text(opt, size=16, color='#212121',
                                    overflow=ft.TextOverflow.VISIBLE, expand=True,
                                    no_wrap=False),
                        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.START,
                           expand=True),
                        padding=ft.Padding(8, 6, 8, 6),
                        border_radius=8,
                        bgcolor='#E3F2FD' if opt in draft_answer else None,
                    )
                    check_items.append(bg_container)

                answer_ctrl = None
                answer_items_list = check_items
                checkboxes_map = checkboxes
                explanation_ctrl = None
                choice_controls = checkboxes_map
            else:
                draft_answer = draft_info.get('answer', '')
                answer_ctrl = ft.TextField(
                    value=draft_answer or '',
                    multiline=True, min_lines=2, max_lines=4,
                    hint_text='请输入年龄...',
                    border_radius=8, text_size=15,
                    border_color='#E0E0E0',
                )
                choice_controls = []

            entry = {
                'qid': qid,
                'question_text': q['question_text'],
                'question_type': qtype,
                'hint': (q.get('hint') or '').strip(),
                'score_ctrl': score_ctrl,
                'answer_ctrl': answer_ctrl,
                'choice_controls': choice_controls,
                'answer_items_list': answer_items_list if qtype in ('single_choice', 'multiple_choice') else [],
            }
            if qtype == 'multiple_choice':
                entry['checkboxes_map'] = checkboxes_map
            case_question_data.append(entry)
        question_fields[case['id']] = case_question_data

    # ================================================================
    # 第二步：辅助函数
    # ================================================================
    def _on_radio_click(rg_ref, value):
        """单选点击（已废弃，on_change 处理即可）"""
        pass

    def _on_check_click(cb):
        """多选点击"""
        cb.value = not cb.value
        cb.update()
        _update_progress()

    def _get_answer_value(qd):
        """获取题目答案值（字符串）"""
        qtype = qd.get('question_type', 'open')
        if qtype == 'single_choice':
            return (qd['answer_ctrl'].value or '')
        elif qtype == 'multiple_choice':
            cbs = qd.get('choice_controls', {})
            selected = [label for label, cb in cbs.items() if cb.value]
            return json.dumps(selected, ensure_ascii=False) if selected else ''
        else:
            return (qd['answer_ctrl'].value or '').strip()

    def _is_answered(qd):
        """判断题目是否已作答"""
        qtype = qd.get('question_type', 'open')
        if qtype == 'single_choice':
            return bool(qd['answer_ctrl'].value)
        elif qtype == 'multiple_choice':
            cbs = qd.get('choice_controls', {})
            return any(cb.value for cb in cbs.values())
        else:
            return bool(qd['answer_ctrl'].value and qd['answer_ctrl'].value.strip())

    def _update_progress():
        """更新进度统计"""
        total = 0
        answered = 0
        for cid, qds in question_fields.items():
            for qd in qds:
                total += 1
                if _is_answered(qd):
                    answered += 1
        progress_text.value = f'进度：{answered}/{total} 题已作答'
        progress_text.update()

    # ================================================================
    # 第三步：构建进度条
    # ================================================================
    progress_text = ft.Text('加载中...', size=15, color='#616161')

    # ================================================================
    # 第四步：构建案例题目区域
    # ================================================================
    case_sections = ft.Column(spacing=16)
    type_badge_labels = {'single_choice': '单选题', 'multiple_choice': '多选题', 'open': '开放题'}

    for case in cases:
        case_questions = question_fields.get(case['id'], [])
        question_rows = []
        for idx, qd in enumerate(case_questions):
            q_num = idx + 1
            qtype = qd.get('question_type', 'open')

            hint_controls = []
            hint_text = qd.get('hint', '')
            if hint_text:
                hint_lines = [l.strip() for l in hint_text.split('\n') if l.strip()]
                if hint_lines:
                    hint_controls.append(
                        ft.Container(
                            content=ft.Column([
                                ft.Row([
                                    ft.Icon(ft.Icons.LIGHTBULB_OUTLINE, size=15, color='#FF8F00'),
                                    ft.Text('作答提示', size=13, color='#FF8F00', weight=ft.FontWeight.W_600),
                                ], spacing=4),
                                *[ft.Text(f'{i}. {line}', size=13, color='#FF8F00', italic=True,
                                           overflow=ft.TextOverflow.VISIBLE)
                                  for i, line in enumerate(hint_lines, 1)],
                            ], spacing=1),
                            bgcolor='#FFF8E1',
                            border_radius=6,
                            padding=ft.Padding(8, 6, 8, 6),
                        )
                    )

            # 根据题型构建作答区域
            answer_area = []
            if qtype == 'open':
                if qd['answer_ctrl']:
                    answer_area.append(qd['answer_ctrl'])
            elif qtype == 'single_choice':
                # 单选直接放 RadioGroup
                if qd['answer_ctrl']:
                    answer_area.append(qd['answer_ctrl'])
            elif qtype == 'multiple_choice':
                # 多选放 Checkbox 列表
                items_list = qd.get('answer_items_list', [])
                if items_list:
                    answer_area.append(
                        ft.Column(items_list, spacing=4)
                    )

            question_rows.append(
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Container(
                                content=ft.Text(str(q_num), size=14, weight=ft.FontWeight.BOLD,
                                                color='white', text_align=ft.TextAlign.CENTER),
                                bgcolor='#1976D2', border_radius=12,
                                width=24, height=24,
                                alignment=ft.Alignment(0, 0),
                            ),
                            ft.Container(
                                content=ft.Text(
                                    type_badge_labels.get(qtype, qtype),
                                    size=12, color='white',
                                ),
                                bgcolor='#1976D2', border_radius=8,
                                padding=ft.Padding(6, 2, 6, 2),
                            ),
                            ft.Text(qd['question_text'], size=15, weight=ft.FontWeight.W_500,
                                    expand=True, overflow=ft.TextOverflow.VISIBLE),
                            qd['score_ctrl'],
                        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        *hint_controls,
                        *answer_area,
                    ], spacing=8),
                    bgcolor='#FAFAFA', border_radius=10,
                    padding=ft.Padding(14, 12, 14, 12),
                    margin=ft.Margin(bottom=8, left=0, right=0, top=0),
                )
            )
        case_sections.controls.append(
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(ft.Icons.FOLDER_OPEN, size=18, color='#1976D2'),
                        ft.Text(f'{case["title"]}', size=15, weight=ft.FontWeight.BOLD,
                                color='#1976D2', overflow=ft.TextOverflow.VISIBLE),
                    ], spacing=6),
                    ft.Divider(height=8, color='#E3F2FD'),
                    *question_rows,
                ], spacing=0),
                bgcolor='white',
                border_radius=12,
                padding=ft.Padding(16, 16, 16, 16),
                shadow=ft.BoxShadow(spread_radius=1, blur_radius=8, color='#00000010'),
            )
        )

    # ================================================================
    # 第五步：绑定 on_change 事件（更新进度）
    # ================================================================
    for cid, qds in question_fields.items():
        for qd in qds:
            qtype = qd.get('question_type', 'open')
            if qtype == 'open' and qd['answer_ctrl'] and hasattr(qd['answer_ctrl'], 'on_change'):
                def make_change_handler():
                    def handler(e):
                        _update_progress()
                    return handler
                qd['answer_ctrl'].on_change = make_change_handler()
            elif qtype == 'single_choice' and qd['answer_ctrl']:
                def make_radio_change_handler():
                    def handler(e):
                        _update_progress()
                    return handler
                qd['answer_ctrl'].on_change = make_radio_change_handler()
            elif qtype == 'multiple_choice':
                cbs = qd.get('choice_controls', {})
                for opt, cb in cbs.items():
                    def make_check_change_handler():
                        def handler(e):
                            _update_progress()
                        return handler
                    cb.on_change = make_check_change_handler()

    # ================================================================
    # 第六步：构建底部按钮
    # ================================================================
    snack = ft.SnackBar(content=ft.Text(''), duration=3000)

    def _do_save_draft(e=None):
        """保存草稿"""
        for cid, qds in question_fields.items():
            answers = {}
            for qd in qds:
                answers[str(qd['qid'])] = json.dumps({
                    'answer': _get_answer_value(qd),
                }, ensure_ascii=False)
            save_draft(task['id'], cid, student_id, answers)

        snack.content.value = '草稿已保存'
        snack.bgcolor = None
        snack.open = True
        if snack not in page.overlay:
            page.overlay.append(snack)
        page.update()

    def _do_submit(e):
        """提交：验证所有题目都已作答，年龄段验证"""
        # 1. 验证所有题目都已作答
        unanswered = []
        for cid, qds in question_fields.items():
            for qd in qds:
                if not _is_answered(qd):
                    case_title = next((c['title'] for c in cases if c['id'] == cid), f'案例{cid}')
                    unanswered.append(f'「{case_title}」中的「{qd["question_text"][:20]}...」')

        if unanswered:
            snack.content.value = f'还有 {len(unanswered)} 道题目未作答，请完成后提交'
            snack.bgcolor = None
            snack.open = True
            if snack not in page.overlay:
                page.overlay.append(snack)
            page.update()
            return

        # 2. 年龄题目验证：年龄必须是18-23岁之间的单个数字
        for cid, qds in question_fields.items():
            for qd in qds:
                if '年龄' in qd.get('question_text', ''):
                    age_answer = _get_answer_value(qd)
                    if not age_answer.isdigit() or not (18 <= int(age_answer) <= 23):
                        snack.content.value = '年龄必须是一个数字，且范围在 18-23 岁之间，请修改后提交'
                        snack.bgcolor = None
                        snack.open = True
                        if snack not in page.overlay:
                            page.overlay.append(snack)
                        page.update()
                        return

        # 提交所有案例
        for cid, qds in question_fields.items():
            all_qids = [str(qd['qid']) for qd in qds]
            answers = {}
            for qd in qds:
                answers[str(qd['qid'])] = json.dumps({
                    'answer': _get_answer_value(qd),
                }, ensure_ascii=False)
            save_draft(task['id'], cid, student_id, answers)
            submit_response(task['id'], cid, student_id, answers, all_qids)

        snack.content.value = '背景资料已提交'
        snack.bgcolor = '#4CAF50'
        snack.open = True
        if snack not in page.overlay:
            page.overlay.append(snack)

        # 跳转到任务列表页面
        page.session.store.set('background_completed', True)
        page.go('/student/dashboard')

    save_btn = ft.OutlinedButton(
        content='暂存草稿',
        icon=ft.Icons.SAVE_OUTLINED,
        style=ft.ButtonStyle(color='#1976D2', side=ft.BorderSide(color='#1976D2', width=1)),
        on_click=_do_save_draft,
    )
    submit_btn = ft.ElevatedButton(
        content='提交',
        icon=ft.Icons.CHECK,
        style=ft.ButtonStyle(bgcolor='#1976D2', color='white',
                             shape=ft.RoundedRectangleBorder(radius=8)),
        on_click=_do_submit,
    )

    bottom_bar = ft.Container(
        content=ft.Row([
            save_btn,
            ft.Container(expand=True),
            submit_btn,
        ], spacing=12),
        bgcolor='white',
        padding=ft.Padding(20, 12, 20, 12),
        shadow=ft.BoxShadow(spread_radius=1, blur_radius=10, color='#00000015'),
        border=ft.Border(top=ft.BorderSide(color='#F0F0F0', width=1)),
    )

    # ================================================================
    # 第七步：初始化进度（仅设值不 update，控件尚未在页面中）并构建头部
    # ================================================================
    _total = 0
    _answered = 0
    for __cd, __qds in question_fields.items():
        for __qd in __qds:
            _total += 1
            if _is_answered(__qd):
                _answered += 1
    progress_text.value = f'进度：{_answered}/{_total} 题已作答'

    header = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.ASSIGNMENT, color='white', size=28),
                ft.Text('必要背景资料', size=22, weight=ft.FontWeight.BOLD, color='white',
                        expand=True, overflow=ft.TextOverflow.ELLIPSIS, no_wrap=True),
                ft.Container(
                    content=ft.Row([
                        ft.Text(student_name, size=15, color='#E3F2FD'),
                        ft.OutlinedButton(
                            content='退出登录',
                            icon=ft.Icons.LOGOUT,
                            on_click=lambda e: on_logout(),
                            style=ft.ButtonStyle(
                                color='white',
                                side=ft.BorderSide(color='#FFFFFF80', width=1),
                                shape=ft.RoundedRectangleBorder(radius=8),
                                padding=ft.Padding(8, 4, 8, 4),
                            ),
                        ),
                    ], spacing=8, alignment=ft.MainAxisAlignment.END),
                ),
            ]),
            ft.Divider(height=12, color='transparent'),
            ft.Text(
                '以下资料仅用于帮助研究团队理解不同学习和经历背景下的研究回答。'
                '请根据实际情况填写；各项均可不回答，简要说明栏为选填内容。'
                '请勿填写患者或其他人员的姓名、学号、联系方式等可识别信息。',
                size=15, color='#BBDEFB', italic=True,
                overflow=ft.TextOverflow.VISIBLE,
            ),
        ], spacing=0),
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=['#1565C0', '#1976D2']
        ),
        padding=ft.Padding(24, 40, 24, 24),
    )

    # ---- 主内容区 ----
    content_column = ft.Column(
        spacing=16,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    view_body = ft.Column([
        progress_text,
        ft.Divider(height=4, color='transparent'),
        case_sections,
    ], spacing=0)

    content_column.controls.append(
        ft.Container(
            content=view_body,
            padding=ft.Padding(20, 16, 20, 16),
        )
    )

    # ================================================================
    # 第八步：组装 View 并返回
    # ================================================================
    view = ft.View(
        route='/student/background',
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Container(
                content=ft.Column([
                    header,
                    ft.Container(content=content_column, expand=True),
                    bottom_bar,
                ], spacing=0),
                bgcolor='#F5F7FA',
                expand=True,
            ),
        ],
        padding=0,
    )

    return view
