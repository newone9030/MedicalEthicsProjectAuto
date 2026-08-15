"""
学生反馈视图
9 步反馈流程：引导页 → 说明页 → N 道案例评价页 → 4 个固定类别页 → 确认提交 → 感谢页
"""

import asyncio

import flet as ft
from app.student.feedback_service import (
    get_student_answered_questions,
    get_feedback_tasks_for_question,
    get_feedback_tasks_by_category,
    submit_feedbacks,
    has_feedback,
)

# 固定引导文案
GUIDE_TEXT = (
               "感谢您完成所有情境任务。\n\n"
               "接下来，请根据您的真实体验，对本预测试系统的各个方面进行评价反馈。\n\n"
               "您的意见对研究团队改进和完善系统至关重要。\n\n"
               "反馈不评价您的案例回答是否正确，也不涉及课程成绩或学习评价。"
               )
INSTRUCTION_TEXT = (
               "以下将分为多个页面，分别针对不同方面进行评价。\n\n"
               "每页包含若干单题或开放题，请根据您的真实体验如实作答。\n\n"
               "全部完成后，可在最后一页确认提交。"
)

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
    'course_impact': '请评价课程影响与系统隐私体验——请根据您的真实感受，评价本次预测试对您课程学习的影响，以及使用本电子调查系统的实际操作体验（流程、界面和隐私保护）。',
    'open_feedback': '开放式反馈——如有任何其他意见、建议或您认为需要补充的内容，请在下方自由填写。',
}

CATEGORY_STEPS = [
    ('task_burden', '作答要求与任务负担'),
    ('course_impact', '课程影响、系统与隐私体验'),
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

    # 三个固定类别页数据
    fixed_steps_data = []
    for cat_key, cat_label in CATEGORY_STEPS:
        tasks = get_feedback_tasks_by_category(cat_key)
        fixed_steps_data.append({
            'category': cat_key,
            'label': cat_label,
            'intro': CATEGORY_INTRO.get(cat_key, ''),
            'feedback_tasks': tasks,
        })

    total_steps = 2 + N + 4 + 1 + 1  # 引导+说明+N案例+3类别+确认+感谢
    # step_index:
    #   0=引导, 1=说明, 2~N+1=案例, N+2~N+4=三个类别, N+6=确认, N+7=感谢

    # ---- 内存中暂存作答 ----
    # answers: {feedback_question_id: {'selected_option_id': int, 'comment_text': str}}
    answers = {}

    # ---- UI 元素 ----
    step_title = ft.Text('', size=20, weight=ft.FontWeight.BOLD, color='#212121')
    intro_text = ft.Text('', size=14, color='#616161')
    intro_box = ft.Container(
        content=intro_text,
        bgcolor='#FFF8E1',
        border_radius=10,
        padding=ft.Padding(14, 10, 14, 10),
        border=ft.Border.all(color='#FFE0B2', width=1),
        visible=False,
    )
    content_area = ft.Column(spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)
    nav_row = ft.Row([], spacing=12, alignment=ft.MainAxisAlignment.CENTER)

    main_col = ft.Column([
        step_title,
        ft.Divider(height=8, color='transparent'),
        intro_box,
        ft.Divider(height=16, color='transparent'),
        content_area,
        ft.Container(expand=True),
        ft.Container(height=28, bgcolor='transparent'),  # 与主要内容的固定间距
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

    def _collect_from_container(container, qid, sqid):
        """递归从容器中收集 radio group 和 textfield 的值（按 题目+案例 组合 key）"""
        if hasattr(container, 'controls'):
            for child in container.controls:
                akey = (qid, sqid)
                if isinstance(child, ft.RadioGroup):
                    val = child.value
                    if val:
                        answers[akey] = answers.get(akey, {})
                        answers[akey]['selected_option_id'] = int(val)
                elif isinstance(child, ft.TextField):
                    val = child.value or ''
                    answers[akey] = answers.get(akey, {})
                    answers[akey]['comment_text'] = val.strip() if val else None
                _collect_from_container(child, qid, sqid)

    def collect_all_current_answers():
        """从当前页内容收集中所有题目作答"""
        for ctrl in content_area.controls:
            if hasattr(ctrl, 'data') and ctrl.data and isinstance(ctrl.data, dict):
                qid = ctrl.data.get('question_id')
                if qid is None:
                    continue
                sqid = ctrl.data.get('survey_question_id')
                _collect_from_container(ctrl, qid, sqid)

    def _set_intro(text):
        """设置步骤说明文字（空文本时隐藏说明框）"""
        intro_text.value = text
        intro_box.visible = bool(text)

    # ---- 渲染步骤 ----
    def render_step(step_idx):
        nonlocal current_step
        current_step = step_idx
        content_area.controls.clear()
        nav_row.controls.clear()

        # ===== Step 0: 引导页 =====
        if step_idx == 0:
            step_title.value = '预测试反馈'
            _set_intro('')
            content_area.controls.append(
                ft.Container(
                    content=ft.Column([
                        # 标题栏
                        ft.Container(
                            content=ft.Row([
                                ft.Icon(ft.Icons.INFO_OUTLINE, color='white', size=18),
                                ft.Text('反馈说明', size=15, weight=ft.FontWeight.W_600, color='white'),
                            ], spacing=8),
                            bgcolor='#1976D2',
                            border_radius=8,
                            padding=ft.Padding(12, 8, 12, 8),
                        ),
                        # 正文（引导文案在框内）
                        ft.Container(
                            content=ft.Text(GUIDE_TEXT, size=15, color='#3B3A3A'),
                            padding=ft.Padding(4, 14, 4, 6),
                        ),
                    ], spacing=10),
                    bgcolor='#E3F2FD',
                    border_radius=12,
                    border=ft.Border.all(color='#90CAF9', width=1),
                    padding=14,
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
            _set_intro('')
            content_area.controls.append(
                ft.Container(
                    content=ft.Column([
                        # 标题栏
                        ft.Container(
                            content=ft.Row([
                                ft.Icon(ft.Icons.MENU_BOOK, color='white', size=18),
                                ft.Text('填写说明', size=15, weight=ft.FontWeight.W_600, color='white'),
                            ], spacing=8),
                            bgcolor='#7B1FA2',
                            border_radius=8,
                            padding=ft.Padding(12, 8, 12, 8),
                        ),
                        # 正文（填写说明文案在框内）
                        ft.Container(
                            content=ft.Text(INSTRUCTION_TEXT, size=15, color='#424242'),
                            padding=ft.Padding(4, 14, 4, 6),
                        ),
                    ], spacing=10),
                    bgcolor='#F3E5F5',
                    border_radius=12,
                    border=ft.Border.all(color='#CE93D8', width=1),
                    padding=14,
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
            _set_intro('请根据以下情境场景，对该案例进行评价：')

            # 案例内容卡片：标题栏 + 完整正文（不截断，字体加大）
            content_area.controls.append(
                ft.Container(
                    content=ft.Column([
                        # 案例标题栏
                        ft.Container(
                            content=ft.Row([
                                ft.Icon(ft.Icons.ARTICLE, color='white', size=18),
                                ft.Text(
                                    f'案例 {case_idx + 1}：{aq["case_title"]}',
                                    size=16, weight=ft.FontWeight.W_600, color='white',
                                ),
                            ], spacing=8),
                            bgcolor='#1976D2',
                            border_radius=8,
                            padding=ft.Padding(12, 10, 12, 10),
                        ),
                        # 案例正文（完整展示）
                        ft.Container(
                            content=ft.Text(
                                aq['question_text'], size=16, color='#3B3A3A',
                            ),
                            padding=ft.Padding(4, 14, 4, 6),
                        ),
                    ], spacing=10),
                    bgcolor='#E3F2FD',
                    border_radius=12,
                    border=ft.Border.all(color='#90CAF9', width=1),
                    padding=14,
                )
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
                        ft.Container(
                            content=ft.Text(ftask['description'], size=13, color='#757575'),
                            bgcolor='#FAFAFA',
                            border_radius=8,
                            padding=ft.Padding(12, 8, 12, 8),
                        )
                    )
                for q in ftask['questions']:
                    content_area.controls.append(
                        _render_question(q, answers,
                                         sqid=aq['survey_question_id'])
                    )

            # 导航
            _build_case_nav(step_idx, N)

        # ===== Step N+2 ~ N+1+len(fixed_steps_data): 固定类别页 =====
        elif N + 2 <= step_idx <= N + 1 + len(fixed_steps_data):
            fixed_idx = step_idx - (N + 2)
            fixed_data = fixed_steps_data[fixed_idx]
            step_title.value = fixed_data['label']
            _set_intro(fixed_data['intro'])

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
            prev_step = N + 1 + fixed_idx  # N+1, N+2, N+3
            # 最后一个固定类别页跳转确认页，其余顺延
            next_step = (N + 6 if fixed_idx == len(fixed_steps_data) - 1
                         else N + 3 + fixed_idx)
            nav_row.controls.append(
                ft.OutlinedButton(
                    content='上一页',
                    icon=ft.Icons.ARROW_BACK,
                    on_click=lambda e, s=prev_step: _go_to_step(s),
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                ),
            )
            # 暂存当前页作答（不跳转，返回后仍保留）
            nav_row.controls.append(
                ft.OutlinedButton(
                    content='暂存',
                    icon=ft.Icons.SAVE_OUTLINED,
                    on_click=lambda e: _save_current_answers(),
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
            _set_intro('')

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
                    on_click=lambda e: render_step(N + 4),
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
            _set_intro('')
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

        # 更新 UI（控件已挂载到页面时才更新，避免视图构建期间未挂载报错）
        for _ctrl in (step_title, intro_box, content_area, nav_row):
            if _ctrl.page:
                _ctrl.update()

        # 跳转后滚动到页面最顶端，避免题目漏填
        # （main_col.page 在控件脱离树时访问会抛异常，此处兜底）
        try:
            if main_col.page is not None:
                page.run_task(_scroll_to_top)
        except Exception:
            pass

    def _go_to_step(step_idx):
        """先收集当前页作答，再跳转"""
        collect_all_current_answers()
        render_step(step_idx)

    async def _scroll_to_top():
        """滚动到页面最顶端（外层 + 内层滚动容器同时回顶）。

        scroll_to 是发往客户端的命令（与 update 串行处理）。若新页面内容还没在
        客户端完成渲染与布局就发送滚动命令，滚动会失效（内容换新但滚动位置残留
        在底部）。因此先短暂等待客户端渲染完成，再发送滚动命令；并加超时，
        避免客户端无响应时协程无限挂起。
        """
        await asyncio.sleep(0.15)  # 等待客户端完成新页面的渲染与布局
        for ctrl in (main_col, content_area):
            try:
                await asyncio.wait_for(ctrl.scroll_to(offset=0), timeout=2.0)
            except Exception:
                pass

    def _save_current_answers():
        """暂存当前页作答（不跳转，仅保存到内存，最后统一提交）"""
        collect_all_current_answers()
        show_snack('已暂存当前页作答')

    def _build_case_nav(step_idx, N):
        """案例评价页导航按钮"""
        # 第一案例页也可返回说明页，保证每页可自由返回
        prev_exists = step_idx > 1
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
        # 暂存当前页作答（不跳转，返回后仍保留）
        nav_row.controls.append(
            ft.OutlinedButton(
                content='暂存',
                icon=ft.Icons.SAVE_OUTLINED,
                on_click=lambda e: _save_current_answers(),
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
        for (qid, sqid), ans in list(answers.items())[:5]:
            opt_id = ans.get('selected_option_id')
            com = ans.get('comment_text')
            summary = ''
            if opt_id:
                summary += f'[选项{opt_id}]'
            if com:
                summary += f' 补充: {com[:30]}'
            label = f'题目{qid}'
            if sqid:
                label += f'(案例{sqid})'
            items.append(ft.Text(f'{label}: {summary or "(开放题)"}', size=12, color='#757575'))
        if len(answers) > 5:
            items.append(ft.Text(f'...共 {len(answers)} 题', size=12, color='#9E9E9E'))
        return ft.Column(items, spacing=2)

    def _find_first_missing_required():
        """查找第一个未作答的必答开放题，返回 (step_idx, 题目文本) 或 None"""
        def _check_tasks(tasks, sqid):
            for q in tasks:
                if q.get('question_type') == 'open' and q.get('required'):
                    ans = answers.get((q['id'], sqid), {})
                    if not (ans.get('comment_text') or '').strip():
                        return q['question_text']
            return None

        for cs_idx, cs in enumerate(case_steps_data):
            sqid = cs['answered_q']['survey_question_id']
            for ftask in cs['feedback_tasks']:
                miss = _check_tasks(ftask.get('questions', []), sqid)
                if miss:
                    return 2 + cs_idx, miss
        for fs_idx, fs in enumerate(fixed_steps_data):
            for ftask in fs['feedback_tasks']:
                miss = _check_tasks(ftask.get('questions', []), None)
                if miss:
                    return N + 2 + fs_idx, miss
        return None

    def do_submit(e):
        """提交反馈"""
        collect_all_current_answers()
        # 校验必答开放题是否全部作答
        missing = _find_first_missing_required()
        if missing:
            miss_step, miss_text = missing
            show_snack('还有必答题未填写，请完成后再提交', success=False)
            render_step(miss_step)
            return
        # 每个 (题目, 案例) 组合一条独立作答，survey_question_id 直接取组合 key
        feedbacks = []
        for (qid, sqid), ans in answers.items():
            feedbacks.append({
                'survey_question_id': sqid,
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

    async def init_view():
        """页面控件挂载到 page 后执行初始渲染"""
        render_step(0)

    # 页面挂载后调度初始渲染（挂载前不调用任何控件方法）
    page.run_task(init_view)

    return [main_col]


# ==================== 辅助函数 ====================

def _render_question(q: dict, answers: dict, sqid=None) -> ft.Container:
    """
    根据题目类型渲染反馈题目控件
    q: {'id', 'question_text', 'question_type', 'options': [...]}
    sqid: 关联的案例调查题 id（同一题目关联多个案例时区分作答，案例页必传）
    """
    qid = q['id']
    qtype = q['question_type']
    akey = (qid, sqid)
    prev_answer = answers.get(akey, {})
    prev_option_id = prev_answer.get('selected_option_id')
    prev_comment = prev_answer.get('comment_text', '')

    # 开放题必答时显示星标
    qtitle_row = [
        ft.Text(q['question_text'], size=14, weight=ft.FontWeight.W_500,
                color='#424242', expand=True),
    ]
    if qtype == 'open' and q.get('required'):
        qtitle_row.append(
            ft.Text('*必答', size=12, weight=ft.FontWeight.W_600, color='#FF5252')
        )
    children = [
        ft.Row(qtitle_row, spacing=6,
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
    ]

    DEFAULT_COMMENT_HINT = '请输入您的补充说明...'

    def _sync_comment(e):
        """输入时实时同步到内存暂存（保证返回上一页能回显）"""
        answers.setdefault(akey, {})['comment_text'] = \
            (e.control.value or '').strip() or None

    comment_field = ft.TextField(
        label='补充说明（可选）',
        hint_text=DEFAULT_COMMENT_HINT,
        multiline=True, min_lines=2, max_lines=4,
        border_color='#BBDEFB', focused_border_color='#1976D2',
        data={'question_id': qid, 'field': 'comment'},
        value=prev_comment,
        visible=False,
        on_change=_sync_comment,
    )

    def _comment_hint_for(opt):
        """取选项配置的补充说明提示文字（未配置时用默认值）"""
        hint = (opt or {}).get('comment_hint') or ''
        return hint or DEFAULT_COMMENT_HINT

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
                    comment_field.hint_text = _comment_hint_for(opt)

        radio_group = ft.RadioGroup(
            content=ft.Column(radio_opts, spacing=4),
            value=selected_value,
            data={'question_id': qid, 'field': 'radio'},
        )

        # 选项变更时同步暂存，并检查是否需要显示评论框
        def on_radio_change(e, opts=options_list, cf=comment_field):
            val = e.control.value
            if val:
                opt_id = int(val)
                answers.setdefault(akey, {})['selected_option_id'] = opt_id
                for o in opts:
                    if o['id'] == opt_id and o.get('requires_comment'):
                        cf.visible = True
                        cf.hint_text = _comment_hint_for(o)
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
            on_change=_sync_comment,
        )
        children.append(open_field)

    return ft.Container(
        content=ft.Column(children, spacing=8),
        data={'question_id': qid, 'question_type': qtype,
              'survey_question_id': sqid},
        bgcolor='#FAFAFA',
        border_radius=10,
        border=ft.Border.all(color='#E0E0E0', width=1),
        padding=ft.Padding(16, 12, 16, 12),
    )
