"""
背景资料问卷页面

学生在知情同意后、进入仪表盘前必须完成的背景资料问卷。
基于任务和案例体系构建，支持暂存和提交流程。
"""

import json
import threading
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
    构建背景资料问卷页面（两阶段加载）

    Phase 1: 构建所有 UI 控件外壳并返回 View
    Phase 2: View 挂载后，异步加载题目数据和草稿，填充控件
    """
    cases = task['cases']

    # ---- 共用引用容器 ----
    question_fields = {}  # {case_id: [{qid, question_text, hint, answer_text, explanation, ...}, ...]}

    # ---- Phase 1: 构建 UI 外壳 ----
    progress_text = ft.Text('加载中...', size=13, color='#616161')

    # 案例区域占位 Container（加载中）
    case_sections = ft.Column(spacing=16)
    for case in cases:
        case_sections.controls.append(
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(ft.Icons.FOLDER_OPEN, size=18, color='#1976D2'),
                        ft.Text(case['title'], size=15, weight=ft.FontWeight.BOLD,
                                color='#1976D2'),
                    ], spacing=6),
                    ft.Divider(height=8, color='#E3F2FD'),
                    ft.Row([
                        ft.ProgressBar(width=80, color='#1976D2', bgcolor='#E3F2FD'),
                        ft.Text('加载题目...', size=12, color='#9E9E9E'),
                    ], spacing=8),
                ], spacing=0),
                bgcolor='white',
                border_radius=12,
                padding=ft.Padding(16, 16, 16, 16),
                shadow=ft.BoxShadow(spread_radius=1, blur_radius=8, color='#00000010'),
            )
        )

    # ---- 底部按钮 ----
    save_btn = ft.OutlinedButton(
        content='暂存草稿',
        icon=ft.Icons.SAVE_OUTLINED,
        style=ft.ButtonStyle(color='#1976D2', side=ft.BorderSide(color='#1976D2', width=1)),
        on_click=None,  # Phase 2 绑定
        disabled=True,
    )
    submit_btn = ft.ElevatedButton(
        content='提交',
        icon=ft.Icons.CHECK,
        style=ft.ButtonStyle(bgcolor='#1976D2', color='white',
                             shape=ft.RoundedRectangleBorder(radius=8)),
        on_click=None,  # Phase 2 绑定
        disabled=True,
    )

    snack = ft.SnackBar(content=ft.Text(''), duration=3000)

    # ---- 头部 ----
    header = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.ASSIGNMENT, color='white', size=28),
                ft.Text('必要背景资料', size=20, weight=ft.FontWeight.BOLD, color='white',
                        expand=True, overflow=ft.TextOverflow.ELLIPSIS, no_wrap=True),
                ft.Container(
                    content=ft.Row([
                        ft.Text(student_name, size=13, color='#E3F2FD'),
                        ft.OutlinedButton(
                            content='退出登录',
                            on_click=lambda e: on_logout(),
                            icon=ft.Icons.LOGOUT,
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
                size=13, color='#BBDEFB', italic=True,
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

    # ============ Phase 2: 异步加载数据 ============
    def _init_data():
        """后台加载题目、草稿，并重建 UI"""
        # 1. 加载所有案例的题目，创建控件（根据题型创建不同控件）
        for case in cases:
            questions = get_questions_by_case(case['id'])
            case_question_data = []
            for q in questions:
                qid = q['id']
                qtype = q['question_type']
                options = q.get('options', [])
                score_ctrl = ft.Text(value='', size=12, color='#9E9E9E')

                if qtype == 'single_choice':
                    # 单选题：RadioGroup
                    answer_ctrl = ft.RadioGroup(
                        content=ft.Column([
                            ft.Radio(value=opt, label=opt, fill_color='#1976D2')
                            for opt in options
                        ], spacing=4),
                    )
                    explanation_ctrl = None
                    choice_controls = []
                elif qtype == 'multiple_choice':
                    # 多选题：Checkbox 列表
                    answer_ctrl = None
                    explanation_ctrl = None
                    choice_controls = [
                        ft.Checkbox(label=opt, value=False, fill_color='#1976D2')
                        for opt in options
                    ]
                else:
                    # 开放题：TextField
                    answer_ctrl = ft.TextField(
                        multiline=True, min_lines=2, max_lines=4,
                        hint_text='请输入回答...',
                        border_radius=8, text_size=13,
                        border_color='#E0E0E0',
                    )
                    explanation_ctrl = ft.TextField(
                        multiline=True, min_lines=1, max_lines=3,
                        hint_text='简要说明（选填）',
                        border_radius=8, text_size=12,
                        border_color='#E0E0E0',
                    )
                    choice_controls = []

                case_question_data.append({
                    'qid': qid,
                    'question_text': q['question_text'],
                    'question_type': qtype,
                    'hint': (q.get('hint') or '').strip(),
                    'score_ctrl': score_ctrl,
                    'answer_ctrl': answer_ctrl,
                    'explanation': explanation_ctrl,
                    'choice_controls': choice_controls,
                })
            question_fields[case['id']] = case_question_data

        # 2. 定义辅助函数（必须先定义后使用）
        def _get_answer_value(qd):
            """获取题目答案值（字符串）"""
            qtype = qd.get('question_type', 'open')
            if qtype == 'single_choice':
                return (qd['answer_ctrl'].value or '')
            elif qtype == 'multiple_choice':
                selected = [cb.label for cb in qd['choice_controls'] if cb.value]
                return json.dumps(selected, ensure_ascii=False) if selected else ''
            else:
                return (qd['answer_ctrl'].value or '').strip()

        def _get_explanation_value(qd):
            """获取简要说明值"""
            ctrl = qd.get('explanation')
            if ctrl and hasattr(ctrl, 'value'):
                return (ctrl.value or '')
            return ''

        def _is_answered(qd):
            """判断题目是否已作答"""
            qtype = qd.get('question_type', 'open')
            if qtype == 'single_choice':
                return bool(qd['answer_ctrl'].value)
            elif qtype == 'multiple_choice':
                return any(cb.value for cb in qd['choice_controls'])
            else:
                return bool(qd['answer_ctrl'].value and qd['answer_ctrl'].value.strip())

        def _set_answer_value(qd, answer_val):
            """根据题型设置答案值（用于加载草稿）"""
            qtype = qd.get('question_type', 'open')
            if qtype == 'single_choice':
                qd['answer_ctrl'].value = answer_val or ''
            elif qtype == 'multiple_choice':
                if isinstance(answer_val, str):
                    try:
                        answer_val = json.loads(answer_val)
                    except json.JSONDecodeError:
                        answer_val = [answer_val] if answer_val else []
                if isinstance(answer_val, list):
                    for cb in qd['choice_controls']:
                        cb.value = cb.label in answer_val
            else:
                qd['answer_ctrl'].value = answer_val or ''

        def _load_drafts():
            """加载草稿内容到控件"""
            for cid, qds in question_fields.items():
                drafts = get_draft_answers(task['id'], cid, student_id)
                if not drafts:
                    continue
                for qd in qds:
                    qid_str = str(qd['qid'])
                    raw = drafts.get(qid_str) or drafts.get(qd['qid'])
                    if raw:
                        try:
                            data = json.loads(raw)
                            if isinstance(data, dict):
                                _set_answer_value(qd, data.get('answer', ''))
                                if qd.get('explanation') and hasattr(qd['explanation'], 'value'):
                                    qd['explanation'].value = data.get('explanation', '')
                        except (json.JSONDecodeError, TypeError):
                            _set_answer_value(qd, str(raw) if raw else '')

        # 3. 加载草稿
        _load_drafts()

        # 4. 构建案例区域并重建 UI（用题目控件替换占位加载条）
        def _build_case_section(case, case_questions):
            """构建单个案例的问题区域"""
            type_badge_labels = {'single_choice': '单选题', 'multiple_choice': '多选题', 'open': '开放题'}
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
                                        ft.Icon(ft.Icons.LIGHTBULB_OUTLINE, size=13, color='#FF8F00'),
                                        ft.Text('作答提示', size=11, color='#FF8F00', weight=ft.FontWeight.W_600),
                                    ], spacing=4),
                                    *[ft.Text(f'{i}. {line}', size=11, color='#FF8F00', italic=True)
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
                    if qd['explanation']:
                        answer_area.append(qd['explanation'])
                elif qtype == 'single_choice':
                    if qd['answer_ctrl']:
                        answer_area.append(qd['answer_ctrl'])
                elif qtype == 'multiple_choice':
                    if qd['choice_controls']:
                        answer_area.append(
                            ft.Column(qd['choice_controls'], spacing=4)
                        )

                question_rows.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Row([
                                ft.Container(
                                    content=ft.Text(str(q_num), size=12, weight=ft.FontWeight.BOLD,
                                                    color='white', text_align=ft.TextAlign.CENTER),
                                    bgcolor='#1976D2', border_radius=12,
                                    width=24, height=24,
                                    alignment=ft.Alignment(0, 0),
                                ),
                                ft.Container(
                                    content=ft.Text(
                                        type_badge_labels.get(qtype, qtype),
                                        size=10, color='white',
                                    ),
                                    bgcolor='#1976D2', border_radius=8,
                                    padding=ft.Padding(6, 2, 6, 2),
                                ),
                                ft.Text(qd['question_text'], size=13, weight=ft.FontWeight.W_500,
                                        expand=True),
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
            return ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(ft.Icons.FOLDER_OPEN, size=18, color='#1976D2'),
                        ft.Text(f'{case["title"]}', size=15, weight=ft.FontWeight.BOLD,
                                color='#1976D2'),
                    ], spacing=6),
                    ft.Divider(height=8, color='#E3F2FD'),
                    *question_rows,
                ], spacing=0),
                bgcolor='white',
                border_radius=12,
                padding=ft.Padding(16, 16, 16, 16),
                shadow=ft.BoxShadow(spread_radius=1, blur_radius=8, color='#00000010'),
            )

        case_sections.controls.clear()
        for case in cases:
            if case['id'] in question_fields:
                case_sections.controls.append(
                    _build_case_section(case, question_fields[case['id']])
                )

        # 5. 绑定动作函数
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

        # 绑定每个控件的 on_change 来更新进度（根据题型不同）
        for cid, qds in question_fields.items():
            for qd in qds:
                qtype = qd.get('question_type', 'open')
                if qtype in ('single_choice', 'open') and qd['answer_ctrl']:
                    def make_change_handler(qd_ref=qd):
                        def handler(e):
                            _update_progress()
                        return handler
                    qd['answer_ctrl'].on_change = make_change_handler()
                elif qtype == 'multiple_choice':
                    for cb in qd['choice_controls']:
                        def make_change_handler(qd_ref=qd, cb_ref=cb):
                            def handler(e):
                                _update_progress()
                            return handler
                        cb.on_change = make_change_handler()

        def _do_save_draft(e=None):
            """保存草稿"""
            for cid, qds in question_fields.items():
                answers = {}
                for qd in qds:
                    answers[str(qd['qid'])] = json.dumps({
                        'answer': _get_answer_value(qd),
                        'explanation': _get_explanation_value(qd),
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
                        'explanation': _get_explanation_value(qd),
                    }, ensure_ascii=False)
                save_draft(task['id'], cid, student_id, answers)
                submit_response(task['id'], cid, student_id, answers, all_qids)

            snack.content.value = '背景资料已提交，即将进入系统...'
            snack.bgcolor = '#4CAF50'
            snack.open = True
            if snack not in page.overlay:
                page.overlay.append(snack)
            page.update()

            # 跳转仪表盘
            page.session.store.set('background_completed', True)
            page.update()
            on_navigate_dashboard()

        save_btn.on_click = _do_save_draft
        submit_btn.on_click = _do_submit
        save_btn.disabled = False
        submit_btn.disabled = False

        # 初始进度
        _update_progress()

        # 刷新页面
        page.update()

    # 通过 Timer(0) 在 View 返回挂载后立即执行数据加载
    threading.Timer(0, _init_data).start()

    return view
