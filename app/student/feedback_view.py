"""
学生反馈视图
9 步反馈流程：引导页 → 说明页 → N 道案例评价页 → 4 个固定类别页 → 确认提交 → 感谢页
"""

import flet as ft
from app.student.feedback_service import (
    get_student_answered_questions,
    get_feedback_tasks_for_question,
    get_feedback_tasks_by_category,
    submit_feedbacks,
    has_feedback,
)

# 固定引导文案
GUIDE_TEXT = "感谢您完成所有情境任务。接下来，请根据您的真实体验，对本预测试系统的各个方面进行评价反馈。您的意见对研究团队改进和完善系统至关重要。"
INSTRUCTION_TEXT = "以下将分为多个页面，分别针对不同方面进行评价。每页包含若干选择题或开放题，请根据您的真实体验如实作答。全部完成后，可在最后一页确认提交。"

CONFIRM_TEXT = (
    "请确认以上内容反映了您的真实使用体验。\n\n"
    "本页仅用于预测试反馈，不评价您的情境回答，也不进入正式研究分析。\n\n"
    "提交后，本次反馈将保存，您不能自行修改。\n\n"
    "是否确认提交？"
)

THANK_YOU_TEXT = (
    "感谢您完成本次预测试并提供反馈。\n\n"
    "您的意见将用于研究团队进一步检查和完善情境案例、电子系统及研究实施流程。\n\n"
    "预测试资料将按照研究要求单独管理，不会纳入正式研究分析。\n\n"
    "本次预测试已全部完成。"
)

CATEGORY_INTRO = {
    'task_burden': '请评价作答要求和任务负担——请根据您完成所有情境任务的实际体验，评价作答要求的清晰度、任务数量和完成时间是否合理。',
    'course_impact': '请评价课程影响——请根据您的真实感受，评价本次预测试对您课程学习的影响。',
    'system_privacy': '请评价系统与隐私体验——请根据您使用本电子调查系统的实际体验，评价系统操作流程、界面设计和隐私保护。',
    'open_feedback': '开放式反馈——如有任何其他意见、建议或您认为需要补充的内容，请在下方自由填写。',
}

CATEGORY_STEPS = [
    ('task_burden', '作答要求与任务负担'),
    ('course_impact', '课程影响'),
    ('system_privacy', '系统与隐私体验'),
    ('open_feedback', '开放式反馈'),
]


def build_feedback_view(page: ft.Page, student_id: int, task_id: int,
                         on_complete) -> list:
    """
    构建反馈视图
    参数：
      page         - Flet Page 对象
      student_id   - 学生用户 ID
      task_id      - 任务 ID（用于查找已作答题目）
      on_complete  - 反馈完成回调（退出系统）
    """

    # ---- 加载数据 ----
    answered_qs = get_student_answered_questions(student_id, task_id)
    N = len(answered_qs)

    # 案例题评价页数据：每题对应的 case 类反馈任务
    case_steps_data = []
    for aq in answered_qs:
        tasks = get_feedback_tasks_for_question(aq['survey_question_id'])
        case_steps_data.append({
            'answered_q': aq,
            'feedback_tasks': tasks,
        })

    # 四个固定类别页数据
    fixed_steps_data = []
    for cat_key, cat_label in CATEGORY_STEPS:
        tasks = get_feedback_tasks_by_category(cat_key)
        fixed_steps_data.append({
            'category': cat_key,
            'label': cat_label,
            'intro': CATEGORY_INTRO.get(cat_key, ''),
            'feedback_tasks': tasks,
        })

    total_steps = 2 + N + 4 + 1 + 1  # 引导+说明+N案例+4类别+确认+感谢
    # step_index:
    #   0=引导, 1=说明, 2~N+1=案例, N+2~N+5=四个类别, N+6=确认, N+7=感谢

    # ---- 内存中暂存作答 ----
    # answers: {feedback_question_id: {'selected_option_id': int, 'comment_text': str}}
    answers = {}

    # ---- UI 元素 ----
    step_title = ft.Text('', size=20, weight=ft.FontWeight.BOLD, color='#212121')
    intro_text = ft.Text('', size=14, color='#616161')
    content_area = ft.Column(spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)
    nav_row = ft.Row([], spacing=12, alignment=ft.MainAxisAlignment.CENTER)

    main_col = ft.Column([
        step_title,
        ft.Divider(height=8, color='transparent'),
        intro_text,
        ft.Divider(height=16, color='transparent'),
        content_area,
        ft.Container(expand=True),
        nav_row,
    ], spacing=0, expand=True, scroll=ft.ScrollMode.AUTO)

    current_step = 0

    def show_snack(msg: str, success: bool = True):
        snack = ft.SnackBar(
            ft.Text(msg),
            bgcolor='#4CAF50' if success else '#FF5252',
        )
        page.overlay.append(snack)
        snack.open = True
        page.update()

    # ---- 获取当前步骤的作答数据 ----
    def collect_current_answers():
        """从 content_area 控件中收集当前页的作答"""
        for ctrl in content_area.controls:
            if hasattr(ctrl, 'data') and ctrl.data and isinstance(ctrl.data, dict):
                # 这是题目卡片，ctrl.data 包含 question_id 等信息
                qid = ctrl.data.get('question_id')
                if qid is None:
                    continue
                qtype = ctrl.data.get('question_type')
                selected_option_id = None
                comment_text = None

                # 查找该卡片内部的 RadioGroup 和 TextField
                _collect_from_container(ctrl, qid, qtype)

    def _collect_from_container(container, qid, qtype):
        """递归从容器中收集 radio group 和 textfield 的值"""
        if hasattr(container, 'controls'):
            for child in container.controls:
                if isinstance(child, ft.RadioGroup) and hasattr(child, 'data'):
                    val = child.value
                    if val:
                        answers[qid] = answers.get(qid, {})
                        answers[qid]['selected_option_id'] = int(val)
                        # 检查是否有 requires_comment
                        if hasattr(child, 'data') and isinstance(child.data, dict):
                            answers[qid]['_requires_comment_option_id'] = child.data.get('_requires_comment_option_id')
                elif isinstance(child, ft.TextField) and hasattr(child, 'data'):
                    val = child.value or ''
                    answers[qid] = answers.get(qid, {})
                    answers[qid]['comment_text'] = val.strip() if val else None
                elif isinstance(child, ft.Container) and child.data:
                    pass  # handled by outer collect
                _collect_from_container(child, qid, qtype)

    def collect_all_current_answers():
        """从当前页内容收集中所有题目作答"""
        for ctrl in content_area.controls:
            if hasattr(ctrl, 'data') and ctrl.data and isinstance(ctrl.data, dict):
                qid = ctrl.data.get('question_id')
                if qid is None:
                    continue
                _collect_from_container(ctrl, qid, ctrl.data.get('question_type'))

    # ---- 渲染步骤 ----
    def render_step(step_idx):
        nonlocal current_step
        current_step = step_idx
        content_area.controls.clear()
        nav_row.controls.clear()

        # ===== Step 0: 引导页 =====
        if step_idx == 0:
            step_title.value = '预测试反馈'
            intro_text.value = ''
            content_area.controls.append(
                ft.Container(
                    content=ft.Text(GUIDE_TEXT, size=15, color='#424242'),
                    bgcolor='#E3F2FD',
                    border_radius=12,
                    padding=24,
                )
            )
            nav_row.controls.append(
                ft.ElevatedButton(
                    content='下一步',
                    icon=ft.Icons.ARROW_FORWARD,
                    on_click=lambda e: render_step(1),
                    style=ft.ButtonStyle(
                        bgcolor='#1976D2', color='white',
                        shape=ft.RoundedRectangleBorder(radius=8),
                    ),
                )
            )

        # ===== Step 1: 说明页 =====
        elif step_idx == 1:
            step_title.value = '填写说明'
            intro_text.value = ''
            content_area.controls.append(
                ft.Container(
                    content=ft.Text(INSTRUCTION_TEXT, size=15, color='#424242'),
                    bgcolor='#F3E5F5',
                    border_radius=12,
                    padding=24,
                )
            )
            nav_row.controls.append(
                ft.OutlinedButton(
                    content='上一页',
                    icon=ft.Icons.ARROW_BACK,
                    on_click=lambda e: render_step(0),
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                ),
            )
            nav_row.controls.append(
                ft.ElevatedButton(
                    content='开始填写',
                    icon=ft.Icons.EDIT,
                    on_click=lambda e: render_step(2),
                    style=ft.ButtonStyle(
                        bgcolor='#1976D2', color='white',
                        shape=ft.RoundedRectangleBorder(radius=8),
                    ),
                )
            )

        # ===== Step 2 ~ N+1: 案例评价页 =====
        elif 2 <= step_idx <= 1 + N:
            case_idx = step_idx - 2
            case_data = case_steps_data[case_idx]
            aq = case_data['answered_q']
            step_title.value = f'案例评价 ({step_idx - 1}/{N})'
            intro_text.value = (
                f'请根据以下情境场景进行评价：\n'
                f'「{aq["case_title"]}」 - {aq["question_text"][:80]}'
            )

            for ftask in case_data['feedback_tasks']:
                content_area.controls.append(
                    ft.Container(
                        content=ft.Text(
                            ftask['title'],
                            size=15, weight=ft.FontWeight.W_600, color='#1976D2',
                        ),
                        bgcolor='#E3F2FD',
                        border_radius=8,
                        padding=ft.Padding(12, 8, 12, 8),
                    )
                )
                if ftask['description']:
                    content_area.controls.append(
                        ft.Text(ftask['description'], size=13, color='#757575')
                    )
                for q in ftask['questions']:
                    content_area.controls.append(
                        _render_question(q, answers)
                    )

            # 导航
            _build_case_nav(step_idx, N)

        # ===== Step N+2 ~ N+5: 四个固定类别页 =====
        elif N + 2 <= step_idx <= N + 5:
            fixed_idx = step_idx - (N + 2)
            fixed_data = fixed_steps_data[fixed_idx]
            step_title.value = fixed_data['label']
            intro_text.value = fixed_data['intro']

            if not fixed_data['feedback_tasks']:
                content_area.controls.append(
                    ft.Container(
                        content=ft.Text('暂无此分类的反馈任务。', size=14, color='#9E9E9E'),
                        alignment=ft.Alignment.CENTER,
                        padding=30,
                    )
                )
            else:
                for ftask in fixed_data['feedback_tasks']:
                    content_area.controls.append(
                        ft.Container(
                            content=ft.Text(
                                ftask['title'],
                                size=15, weight=ft.FontWeight.W_600, color='#1976D2',
                            ),
                            bgcolor='#E3F2FD',
                            border_radius=8,
                            padding=ft.Padding(12, 8, 12, 8),
                        )
                    )
                    if ftask['description']:
                        content_area.controls.append(
                            ft.Text(ftask['description'], size=13, color='#757575')
                        )
                    for q in ftask['questions']:
                        content_area.controls.append(
                            _render_question(q, answers)
                        )

            # 导航
            prev_step = N + 1 + fixed_idx  # N+1, N+2, N+3, N+4
            next_step = N + 3 + fixed_idx   # N+3, N+4, N+5, N+6
            nav_row.controls.append(
                ft.OutlinedButton(
                    content='上一页',
                    icon=ft.Icons.ARROW_BACK,
                    on_click=lambda e, s=prev_step: _go_to_step(s),
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                ),
            )
            nav_row.controls.append(
                ft.ElevatedButton(
                    content='下一页',
                    icon=ft.Icons.ARROW_FORWARD,
                    on_click=lambda e, s=next_step: _go_to_step(s),
                    style=ft.ButtonStyle(
                        bgcolor='#1976D2', color='white',
                        shape=ft.RoundedRectangleBorder(radius=8),
                    ),
                )
            )

        # ===== Step N+6: 确认提交页 =====
        elif step_idx == N + 6:
            collect_all_current_answers()
            step_title.value = '确认提交'
            intro_text.value = ''

            answered_count = len(answers)
            total_questions = _count_all_questions()

            content_area.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Text(CONFIRM_TEXT, size=15, color='#424242'),
                        ft.Divider(height=12, color='transparent'),
                        ft.Row([
                            ft.Icon(ft.Icons.CHECK_CIRCLE, color='#4CAF50', size=20),
                            ft.Text(
                                f'已完成 {answered_count}/{total_questions} 道题目',
                                size=14, weight=ft.FontWeight.W_500, color='#4CAF50',
                            ),
                        ], spacing=8),
                        _build_answer_summary(),
                    ]),
                    border_radius=12,
                    bgcolor='#FFF8E1',
                    padding=24,
                )
            )

            nav_row.controls.append(
                ft.OutlinedButton(
                    content='返回修改',
                    icon=ft.Icons.ARROW_BACK,
                    on_click=lambda e: render_step(N + 5),
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                ),
            )
            nav_row.controls.append(
                ft.ElevatedButton(
                    content='确认提交',
                    icon=ft.Icons.CHECK,
                    on_click=do_submit,
                    style=ft.ButtonStyle(
                        bgcolor='#4CAF50', color='white',
                        shape=ft.RoundedRectangleBorder(radius=8),
                    ),
                ),
            )

        # ===== Step N+7: 感谢页 =====
        elif step_idx == N + 7:
            step_title.value = '预测试完成'
            intro_text.value = ''
            content_area.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.CHECK_CIRCLE, color='#4CAF50', size=64),
                        ft.Text(THANK_YOU_TEXT, size=16, color='#424242',
                               text_align=ft.TextAlign.CENTER),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=16),
                    bgcolor='#E8F5E9',
                    border_radius=16,
                    padding=32,
                    alignment=ft.Alignment.CENTER,
                )
            )
            nav_row.controls.append(
                ft.ElevatedButton(
                    content='退出系统',
                    icon=ft.Icons.EXIT_TO_APP,
                    on_click=lambda e: on_complete(),
                    style=ft.ButtonStyle(
                        bgcolor='#FF5252', color='white',
                        shape=ft.RoundedRectangleBorder(radius=8),
                    ),
                )
            )

        # 更新 UI
        step_title.update()
        intro_text.update()
        content_area.update()
        nav_row.update()

    def _go_to_step(step_idx):
        """先收集当前页作答，再跳转"""
        collect_all_current_answers()
        render_step(step_idx)

    def _build_case_nav(step_idx, N):
        """案例评价页导航按钮"""
        prev_exists = step_idx > 2
        is_last_case = step_idx == N + 1

        if prev_exists:
            nav_row.controls.append(
                ft.OutlinedButton(
                    content='上一页',
                    icon=ft.Icons.ARROW_BACK,
                    on_click=lambda e, s=step_idx - 1: _go_to_step(s),
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                ),
            )
        if is_last_case:
            # 最后一题案例评价，跳到下一个分类
            nav_row.controls.append(
                ft.ElevatedButton(
                    content='提交并继续' if N == 0 else '下一页',
                    icon=ft.Icons.ARROW_FORWARD,
                    on_click=lambda e: _go_to_step(N + 2),
                    style=ft.ButtonStyle(
                        bgcolor='#1976D2', color='white',
                        shape=ft.RoundedRectangleBorder(radius=8),
                    ),
                )
            )
        else:
            nav_row.controls.append(
                ft.ElevatedButton(
                    content='下一页',
                    icon=ft.Icons.ARROW_FORWARD,
                    on_click=lambda e, s=step_idx + 1: _go_to_step(s),
                    style=ft.ButtonStyle(
                        bgcolor='#1976D2', color='white',
                        shape=ft.RoundedRectangleBorder(radius=8),
                    ),
                )
            )

    def _count_all_questions():
        """统计所有反馈题目总数"""
        count = 0
        for cs in case_steps_data:
            for ft in cs['feedback_tasks']:
                count += len(ft.get('questions', []))
        for fs in fixed_steps_data:
            for ft in fs['feedback_tasks']:
                count += len(ft.get('questions', []))
        return count

    def _build_answer_summary():
        """构建已作答汇总（简要展示）"""
        items = []
        for qid, ans in list(answers.items())[:5]:
            opt_id = ans.get('selected_option_id')
            com = ans.get('comment_text')
            summary = ''
            if opt_id:
                summary += f'[选项{opt_id}]'
            if com:
                summary += f' 补充: {com[:30]}'
            items.append(ft.Text(f'题目{qid}: {summary or "(开放题)"}', size=12, color='#757575'))
        if len(answers) > 5:
            items.append(ft.Text(f'...共 {len(answers)} 题', size=12, color='#9E9E9E'))
        return ft.Column(items, spacing=2)

    def do_submit(e):
        """提交反馈"""
        collect_all_current_answers()
        feedbacks = []
        survey_question_id_map = {}
        for cs in case_steps_data:
            sqid = cs['answered_q']['survey_question_id']
            for ft in cs['feedback_tasks']:
                for q in ft.get('questions', []):
                    survey_question_id_map[q['id']] = sqid

        for qid, ans in answers.items():
            survey_question_id = survey_question_id_map.get(qid)
            feedbacks.append({
                'survey_question_id': survey_question_id,
                'feedback_question_id': qid,
                'selected_option_id': ans.get('selected_option_id'),
                'comment_text': ans.get('comment_text'),
            })

        if not feedbacks:
            show_snack('未找到任何反馈作答', success=False)
            return

        result = submit_feedbacks(student_id, feedbacks)
        if result['success']:
            show_snack('反馈提交成功！')
            render_step(N + 7)  # 进入感谢页
        else:
            show_snack(result.get('message', '提交失败'), success=False)

    # ---- 初始渲染 ----
    render_step(0)

    return [main_col]


# ==================== 辅助函数 ====================

def _render_question(q: dict, answers: dict) -> ft.Container:
    """
    根据题目类型渲染反馈题目控件
    q: {'id', 'question_text', 'question_type', 'options': [...]}
    """
    qid = q['id']
    qtype = q['question_type']
    prev_answer = answers.get(qid, {})
    prev_option_id = prev_answer.get('selected_option_id')
    prev_comment = prev_answer.get('comment_text', '')

    children = [
        ft.Text(
            q['question_text'],
            size=14, weight=ft.FontWeight.W_500, color='#424242',
        ),
    ]

    comment_field = ft.TextField(
        label='补充说明（可选）',
        hint_text='请输入您的补充说明...',
        multiline=True, min_lines=2, max_lines=4,
        border_color='#BBDEFB', focused_border_color='#1976D2',
        data={'question_id': qid, 'field': 'comment'},
        value=prev_comment,
        visible=False,
    )

    if qtype == 'radio':
        options_list = q.get('options', [])
        selected_value = None
        radio_opts = []

        for opt in options_list:
            opt_id = opt['id']
            radio_opts.append(
                ft.Radio(
                    value=str(opt_id),
                    label=opt['label'],
                )
            )
            if prev_option_id is not None and opt_id == prev_option_id:
                selected_value = str(opt_id)
                if opt.get('requires_comment'):
                    comment_field.visible = True

        radio_group = ft.RadioGroup(
            content=ft.Column(radio_opts, spacing=4),
            value=selected_value,
            data={'question_id': qid, 'field': 'radio'},
        )

        # 选项变更时检查是否需要显示评论框
        def on_radio_change(e, opts=options_list, cf=comment_field):
            val = e.control.value
            if val:
                opt_id = int(val)
                for o in opts:
                    if o['id'] == opt_id and o.get('requires_comment'):
                        cf.visible = True
                        if cf.page:
                            cf.update()
                        return
            cf.visible = False
            if cf.page:
                cf.update()

        radio_group.on_change = on_radio_change

        children.append(radio_group)
        children.append(comment_field)

    elif qtype == 'open':
        open_field = ft.TextField(
            label='请输入您的回答',
            multiline=True, min_lines=3, max_lines=6,
            border_color='#BBDEFB', focused_border_color='#1976D2',
            data={'question_id': qid, 'field': 'open'},
            value=prev_comment or '',
        )
        children.append(open_field)

    return ft.Container(
        content=ft.Column(children, spacing=8),
        data={'question_id': qid, 'question_type': qtype},
        bgcolor='#FAFAFA',
        border_radius=10,
        border=ft.border.all(color='#E0E0E0', width=1),
        padding=ft.Padding(16, 12, 16, 12),
    )
