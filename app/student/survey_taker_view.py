"""
问卷作答视图 - 逐题显示版本
每页显示一道题目，支持"上一题"/"下一题"切换、逐题暂存、一次性提交全部
页面控件先加载，数据通过 page.run_task 延迟加载
"""
import json
import threading
import flet as ft
from app.task.task_service import get_task
from app.case.question_service import get_questions_by_case
from app.response.response_service import save_draft, submit_response, get_draft_answers, get_submitted_answers, get_submission_status
from app.student.feedback_service import has_feedback


def build_survey_taker_view(page: ft.Page, task_id: int, on_back=None, readonly: bool = False) -> list:
    """问卷作答视图 - 逐题显示，数据延迟加载"""
    user = page.session.store.get('user')
    student_id = user['id']

    # ================================================================
    # Phase 1: 立即构建 UI 骨架（不做任何 API 调用）
    # ================================================================

    # 进度控件（骨架态）
    progress_text = ft.Text('加载中...', size=15, color='#9E9E9E')
    progress_bar = ft.ProgressBar(value=0, bgcolor='#E0E0E0', color='#1976D2', height=8)

    # 案例/题目位置标签（骨架态）
    case_label = ft.Text('正在加载...', size=15, color='#1976D2',
                         overflow=ft.TextOverflow.VISIBLE)

    # 题目容器 - 先显示加载动画
    question_container = ft.Column([], spacing=0, expand=True,
                                   scroll=ft.ScrollMode.AUTO)
    question_container.controls.append(
        ft.Container(
            content=ft.Column([
                ft.ProgressRing(width=40, height=40, color='#1976D2'),
                ft.Text('正在加载题目数据...', size=14, color='#9E9E9E'),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
            alignment=ft.Alignment(0, 0),
            expand=True,
        )
    )

    # 按钮控件（初始隐藏）
    prev_btn = ft.ElevatedButton(
        content='上一题',
        icon=ft.Icons.ARROW_BACK,
        visible=False,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
    )
    next_btn = ft.ElevatedButton(
        content='下一题',
        icon=ft.Icons.ARROW_FORWARD,
        visible=False,
        style=ft.ButtonStyle(bgcolor='#1976D2', color='white', shape=ft.RoundedRectangleBorder(radius=8)),
    )
    submit_all_btn = ft.ElevatedButton(
        content='提交全部',
        icon=ft.Icons.CHECK,
        visible=False,
        style=ft.ButtonStyle(bgcolor='#4CAF50', color='white', shape=ft.RoundedRectangleBorder(radius=8)),
    )
    save_btn = ft.OutlinedButton(
        content='暂存',
        icon=ft.Icons.SAVE_OUTLINED,
        visible=False,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
    )

    # 任务名标题（骨架态）
    task_title_text = ft.Text('加载中...', size=22, weight=ft.FontWeight.BOLD, color='#1565C0',
                              expand=True, overflow=ft.TextOverflow.ELLIPSIS)

    # 返回按钮
    back_btn = ft.IconButton(
        icon=ft.Icons.ARROW_BACK, icon_color='#1565C0',
        on_click=lambda e: on_back() if on_back else None,
    )

    # SnackBar 辅助
    def _show_snack(msg: str, success: bool = True):
        snack = ft.SnackBar(ft.Text(msg, size=15), bgcolor='#4CAF50' if success else '#FF5252')
        page.overlay.append(snack)
        snack.open = True
        page.update()

    def _navigate_to_feedback(_page):
        """测试用户任务完成后，继续填写反馈任务"""
        _page.go('/student/feedback')

    def _close_overlay_dlg(dialog):
        dialog.open = False
        page.update()

    # ================================================================
    # Phase 2: 数据加载（通过 page.run_task 延迟执行）
    # ================================================================

    async def init_data():
        """异步加载所有数据并更新 UI"""
        try:
            task = get_task(task_id)
            if not task:
                question_container.controls.clear()
                question_container.controls.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Icon(ft.Icons.ERROR_OUTLINE, size=48, color='#FF5252'),
                            ft.Text('任务不存在', size=18, color='#FF5252'),
                            ft.TextButton(content=ft.Text('返回', size=16),
                                          on_click=lambda e: on_back() if on_back else None),
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                        alignment=ft.Alignment(0, 0),
                        expand=True,
                    )
                )
                progress_text.value = '任务不存在'
                case_label.value = ''
                page.update()
                return

            task_title_text.value = task['name']
            task_title_text.update()

            cases = task['cases']
            if not cases:
                question_container.controls.clear()
                question_container.controls.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Icon(ft.Icons.WARNING_AMBER, size=48, color='#FF9800'),
                            ft.Text('该任务没有关联案例', size=18, color='#FF9800'),
                            ft.TextButton(content=ft.Text('返回', size=16),
                                          on_click=lambda e: on_back() if on_back else None),
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                        alignment=ft.Alignment(0, 0),
                        expand=True,
                    )
                )
                progress_text.value = '无关联案例'
                case_label.value = ''
                page.update()
                return

            # ---- 加载所有案例的题目和答案 ----
            all_questions_map = {}
            all_answers = {}
            not_submitted_case_ids = set()

            for case in cases:
                qs = get_questions_by_case(case['id'])
                all_questions_map[case['id']] = qs

                if readonly:
                    saved = get_submitted_answers(task_id, case['id'], student_id)
                else:
                    saved = get_draft_answers(task_id, case['id'], student_id)
                for qid, ans in saved.items():
                    all_answers[f"{case['id']}_{qid}"] = ans

                statuses = get_submission_status(task_id, student_id)
                if statuses.get(case['id']) != 'submitted':
                    not_submitted_case_ids.add(case['id'])

            # 筛选显示的案例
            active_cases = [c for c in cases if c['id'] in not_submitted_case_ids] if not readonly else cases
            if readonly:
                active_cases = cases

            if not active_cases:
                question_container.controls.clear()
                question_container.controls.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Icon(ft.Icons.CHECK_CIRCLE, size=64, color='#4CAF50'),
                            ft.Text('所有案例已提交', size=22, weight=ft.FontWeight.BOLD, color='#4CAF50'),
                            ft.TextButton(content=ft.Text('返回', size=16),
                                          on_click=lambda e: on_back() if on_back else None),
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                        padding=60,
                        alignment=ft.Alignment.CENTER,
                        expand=True,
                    )
                )
                progress_text.value = '全部已提交'
                progress_bar.value = 1.0
                case_label.value = ''
                page.update()
                return

            # ---- 展平所有题目 ----
            flat_questions = []
            for case in active_cases:
                qs = all_questions_map.get(case['id'], [])
                for qi, q in enumerate(qs):
                    flat_questions.append((case, q, qi, len(qs)))

            total_q_count = len(flat_questions)
            current_idx = [0]

            if total_q_count == 0:
                question_container.controls.clear()
                question_container.controls.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Icon(ft.Icons.WARNING_AMBER, size=64, color='#FF9800'),
                            ft.Text('暂无题目', size=22, weight=ft.FontWeight.BOLD, color='#FF9800'),
                            ft.TextButton(content=ft.Text('返回', size=16),
                                          on_click=lambda e: on_back() if on_back else None),
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                        padding=60,
                        alignment=ft.Alignment.CENTER,
                        expand=True,
                    )
                )
                progress_text.value = '暂无题目'
                case_label.value = ''
                page.update()
                return

            # ---- 内部函数：进度统计 ----
            def count_completed():
                return sum(1 for key, val in all_answers.items()
                           if val is not None and val != '' and
                           (not isinstance(val, (list, dict)) or len(val) > 0) and
                           not (isinstance(val, dict) and not val.get('options') and not val.get('open_text')))

            def update_progress():
                completed = count_completed()
                progress_text.value = f'进度: {completed}/{total_q_count} 题已完成'
                progress_bar.value = completed / total_q_count if total_q_count > 0 else 0
                progress_text.update()
                progress_bar.update()

            # ---- 内部函数：获取案例序号 ----
            def _case_order(target_case, case_list):
                for i, c in enumerate(case_list):
                    if c['id'] == target_case['id']:
                        return i + 1
                return 1

            # ---- 刷新按钮可见性 ----
            def _refresh_buttons():
                if readonly:
                    prev_btn.visible = current_idx[0] > 0
                    next_btn.visible = current_idx[0] < total_q_count - 1
                    save_btn.visible = False
                    submit_all_btn.visible = False
                else:
                    is_first = current_idx[0] == 0
                    is_last = current_idx[0] >= total_q_count - 1
                    prev_btn.visible = not is_first
                    next_btn.visible = not is_last
                    save_btn.visible = True
                    submit_all_btn.visible = is_last
                prev_btn.update()
                next_btn.update()
                save_btn.update()
                submit_all_btn.update()

            # ---- 构建当前题目显示 ----
            def build_question_content():
                case, question, qi, qs_len = flat_questions[current_idx[0]]
                num_in_task = current_idx[0] + 1

                case_label.value = f'案例 {_case_order(case, active_cases)}/{len(active_cases)}: {case["title"]}  |  第 {qi + 1}/{qs_len} 题'
                case_label.update()

                question_container.controls.clear()
                w = _build_question_widget(question, f"{case['id']}_{question['id']}", all_answers, readonly)
                question_container.controls.append(w)
                question_container.update()

                _refresh_buttons()
                update_progress()

            # ---- 导航 ----
            def go_prev(e):
                if current_idx[0] > 0:
                    current_idx[0] -= 1
                    build_question_content()

            def go_next(e):
                if current_idx[0] < total_q_count - 1:
                    current_idx[0] += 1
                    build_question_content()

            # ---- 暂存 ----
            def handle_save_draft(e):
                case, question, qi, qs_len = flat_questions[current_idx[0]]
                case_id = case['id']

                case_answers = {}
                for key, val in all_answers.items():
                    if key.startswith(f"{case_id}_"):
                        qid_str = key.split('_', 1)[1]
                        try:
                            qid = int(qid_str)
                        except ValueError:
                            qid = qid_str
                        case_answers[qid] = val

                result = save_draft(task_id, case_id, student_id, case_answers)
                _show_snack(result['message'], result['success'])
                update_progress()

            # ---- 提交全部 ----
            def handle_submit(e):
                all_cases_data = {}
                all_unanswered = []

                for case in active_cases:
                    questions = all_questions_map.get(case['id'], [])
                    qids = [q['id'] for q in questions]
                    case_answers = {}
                    case_unanswered = []
                    for q in questions:
                        key = f"{case['id']}_{q['id']}"
                        ans = all_answers.get(key)
                        if (ans is None or ans == '' or
                                (isinstance(ans, list) and len(ans) == 0) or
                                (isinstance(ans, dict) and not ans.get('options') and not ans.get('open_text'))):
                            case_unanswered.append((case['title'], q['question_text'][:30]))
                        else:
                            case_answers[q['id']] = ans
                    all_cases_data[case['id']] = {'answers': case_answers, 'qids': qids}
                    all_unanswered.extend(case_unanswered)

                if all_unanswered:
                    lines = []
                    for case_title, qtext in all_unanswered[:8]:
                        lines.append(f'\u2022 [{case_title}] {qtext}')
                    if len(all_unanswered) > 8:
                        lines.append(f'... 及其他 {len(all_unanswered) - 8} 题')
                    dlg = ft.AlertDialog(
                        title=ft.Text('\u8BF7\u5B8C\u6210\u6240\u6709\u9898\u76EE', size=16),
                        content=ft.Text(
                            f'\u4EE5\u4E0B {len(all_unanswered)} \u9053\u9898\u5C1A\u672A\u4F5C\u7B54\uFF1A\n\n' + '\n'.join(lines),
                            size=15),
                        actions=[ft.TextButton(content=ft.Text('\u77E5\u9053\u4E86', size=15),
                                                on_click=lambda e: _close_overlay_dlg(dlg))],
                        modal=True,
                    )
                    page.overlay.append(dlg)
                    dlg.open = True
                    page.update()
                    return

                def do_submit_all(e2):
                    _close_overlay_dlg(self_check_dlg)

                    success_count = 0
                    for case in active_cases:
                        data = all_cases_data[case['id']]
                        result = submit_response(task_id, case['id'], student_id, data['answers'], data['qids'])
                        if result['success']:
                            success_count += 1
                            not_submitted_case_ids.discard(case['id'])
                        else:
                            _show_snack(f'\u6848\u4F8B\u300C{case["title"]}\u300D\u63D0\u4EA4\u5931\u8D25: {result["message"]}', False)

                    if success_count == len(active_cases):
                        _show_snack(f'\u5168\u90E8 {success_count} \u4E2A\u6848\u4F8B\u5DF2\u63D0\u4EA4\u5B8C\u6210\uFF01')
                        # 测试用户完成任务后，继续填写反馈任务
                        _user_info = page.session.store.get('user') or {}
                        if (_user_info.get('user_type') == 'test'
                                and not has_feedback(student_id)):
                            _navigate_to_feedback(page)
                        elif on_back:
                            on_back()
                    elif success_count > 0:
                        _show_snack(f'\u5DF2\u63D0\u4EA4 {success_count}/{len(active_cases)} \u4E2A\u6848\u4F8B\uFF0C\u8BF7\u91CD\u8BD5\u5931\u8D25\u7684\u6848\u4F8B')

                # 自检复选框
                check1 = ft.Checkbox(label='\u6700\u91CD\u8981\u7684\u95EE\u9898\u53CA\u7406\u7531', value=False)
                check2 = ft.Checkbox(label='\u76F8\u5173\u4EBA\u5458\u6216\u76F8\u5173\u65B9\u9762\u7684\u8003\u8651', value=False)
                check3 = ft.Checkbox(label='\u4E0B\u4E00\u6B65\u7684\u505A\u6CD5\u548C\u7406\u7531', value=False)
                check4 = ft.Checkbox(label='\u9700\u8981\u8865\u5145\u7684\u4FE1\u606F\u53CA\u5176\u5BF9\u5224\u65AD\u7684\u5F71\u54CD', value=False)

                submit_btn = ft.ElevatedButton(
                    content=ft.Text('\u7EE7\u7EED\u63D0\u4EA4', size=15),
                    on_click=do_submit_all,
                    disabled=True,
                    style=ft.ButtonStyle(bgcolor='#4CAF50', color='white'),
                )

                def on_check_change(e):
                    submit_btn.disabled = not (check1.value and check2.value and check3.value and check4.value)
                    submit_btn.update()

                check1.on_change = on_check_change
                check2.on_change = on_check_change
                check3.on_change = on_check_change
                check4.on_change = on_check_change

                self_check_dlg = ft.AlertDialog(
                    title=ft.Text('\u63D0\u4EA4\u524D\uFF0C\u8BF7\u68C0\u67E5\u60A8\u7684\u56DE\u7B54\u662F\u5426\u5DF2\u5C3D\u53EF\u80FD\u5305\u542B\u4EE5\u4E0B\u5185\u5BB9\uFF1A', size=16),
                    content=ft.Column(
                        [check1, check2, check3, check4],
                        spacing=10,
                    ),
                    actions=[
                        ft.TextButton(content=ft.Text('\u8FD4\u56DE\u8865\u5145', size=15),
                                      on_click=lambda e: _close_overlay_dlg(self_check_dlg)),
                        submit_btn,
                    ],
                    modal=True,
                )
                page.overlay.append(self_check_dlg)
                self_check_dlg.open = True
                page.update()

            # ---- 绑定按钮事件 ----
            prev_btn.on_click = go_prev
            next_btn.on_click = go_next
            submit_all_btn.on_click = handle_submit
            save_btn.on_click = handle_save_draft

            # ---- 初始渲染 ----
            build_question_content()

        except Exception as ex:
            import traceback
            traceback.print_exc()
            question_container.controls.clear()
            question_container.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.ERROR_OUTLINE, size=48, color='#FF5252'),
                        ft.Text('加载失败', size=18, color='#FF5252'),
                        ft.Text(str(ex), size=14, color='#9E9E9E'),
                        ft.TextButton(content=ft.Text('返回', size=16),
                                      on_click=lambda e: on_back() if on_back else None),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                    alignment=ft.Alignment(0, 0),
                    expand=True,
                )
            )
            progress_text.value = '加载失败'
            case_label.value = ''
            page.update()

    # 调度数据加载任务：等待页面控件加载完成后才执行（挂载前不调用任何方法）
    def _schedule_init():
        if question_container.parent is None:
            threading.Timer(0.05, _schedule_init).start()
            return
        page.run_task(init_data)

    _schedule_init()

    # ================================================================
    # Phase 3: 立即返回 UI 骨架
    # ================================================================
    return [
        ft.Column([
            ft.Row([
                back_btn,
                task_title_text,
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(height=10, color='transparent'),
            progress_bar,
            ft.Row([
                progress_text,
            ], alignment=ft.MainAxisAlignment.CENTER),
            ft.Divider(height=8, color='transparent'),
            case_label,
            ft.Divider(height=10, color='transparent'),
            ft.Container(
                content=question_container,
                bgcolor='white',
                border_radius=12,
                padding=20,
                shadow=ft.BoxShadow(spread_radius=0.5, blur_radius=8, color='#00000015'),
                expand=True,
            ),
            ft.Divider(height=15, color='transparent'),
            ft.Row([
                save_btn,
                ft.Container(expand=True),
                prev_btn,
                next_btn,
                submit_all_btn,
            ], spacing=10, alignment=ft.MainAxisAlignment.END),
        ], expand=True, spacing=0),
    ]


def _build_question_widget(question: dict, key: str, answers: dict, readonly: bool) -> ft.Container:
    """构建单个题目组件"""
    qid = question['id']
    qtype = question['question_type']
    current_val = answers.get(key)

    is_unanswered = not readonly and (
        current_val is None or current_val == '' or
        (isinstance(current_val, list) and len(current_val) == 0) or
        (isinstance(current_val, dict) and not current_val.get('options') and not current_val.get('open_text'))
    )
    border_color = '#FF5252' if is_unanswered else '#E0E0E0'

    def on_answer_change(val):
        answers[key] = val

    if qtype == 'single_choice':
        opts = question.get('options', [])
        if not opts:
            content = ft.Text('(无选项)', size=15, color='#9E9E9E', italic=True)
        else:
            # 规范化选项（兼容旧字符串/新对象）
            norm_opts = []
            for o in opts:
                if isinstance(o, dict):
                    norm_opts.append({
                        'label': str(o.get('label', o.get('text', ''))),
                        'requires_open': bool(o.get('requires_open', False)),
                        'open_hint': str(o.get('open_hint', '') or ''),
                    })
                else:
                    norm_opts.append({'label': str(o), 'requires_open': False, 'open_hint': ''})

            def _get_selection():
                val = answers.get(key)
                if isinstance(val, dict):
                    return val.get('option'), val.get('open_text', '')
                return val, ''

            radio_column = ft.Column([], spacing=4)

            def rebuild_single():
                sel_label, sel_open_text = _get_selection()
                radio_column.controls.clear()
                for opt in norm_opts:
                    label = opt['label']
                    is_selected = label == sel_label
                    children = [
                        ft.Container(
                            content=ft.Row([
                                ft.Icon(
                                    ft.Icons.RADIO_BUTTON_CHECKED if is_selected else ft.Icons.RADIO_BUTTON_UNCHECKED,
                                    color='#1976D2' if is_selected else '#757575',
                                    size=20,
                                ),
                                ft.Text(label, size=16, color='#212121',
                                        overflow=ft.TextOverflow.VISIBLE, expand=True,
                                        no_wrap=False),
                            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.START),
                            on_click=None if readonly else (lambda e, o=opt: _on_single_select(o, key, answers, rebuild_single, radio_column)),
                            padding=ft.Padding(8, 6, 8, 6),
                            border_radius=8,
                            bgcolor='#E3F2FD' if is_selected else None,
                            data=label,
                        )
                    ]
                    # 选中且要求补充说明时，显示开放式文本框
                    if is_selected and opt['requires_open']:
                        open_tf = ft.TextField(
                            value=sel_open_text,
                            multiline=True,
                            min_lines=2,
                            max_lines=4,
                            hint_text=opt['open_hint'] or '请输入补充说明...',
                            border_color='#BBDEFB',
                            focused_border_color='#1976D2',
                            text_size=15,
                            on_change=lambda e, l=label: _on_open_text_change(l, e.control.value, key, answers),
                        )
                        if readonly:
                            open_tf.read_only = True
                        children.append(
                            ft.Container(
                                content=open_tf,
                                padding=ft.Padding(28, 4, 8, 8),
                            )
                        )
                    radio_column.controls.append(ft.Column(children, spacing=2))
                # 页面控件加载完成前不调用方法（未挂载时不刷新）
                if radio_column.parent is not None:
                    radio_column.update()

            rebuild_single()
            content = radio_column

    elif qtype == 'multiple_choice':
        opts = question.get('options', [])
        open_enabled = bool(question.get('open_text_enabled', False))
        open_title = question.get('open_text_title', '') or ''
        open_hint = question.get('open_text_hint', '') or ''
        if not opts:
            content = ft.Text('(无选项)', size=15, color='#9E9E9E', italic=True)
        else:
            # 兼容旧 list 答案与新 dict 答案 {'options': [...], 'open_text': '...'}
            if isinstance(current_val, dict):
                selected = current_val.get('options', []) if isinstance(current_val.get('options'), list) else []
                selected_open_text = current_val.get('open_text', '') or ''
            elif isinstance(current_val, list):
                selected = current_val
                selected_open_text = ''
            else:
                selected = []
                selected_open_text = ''
            check_items = []
            for opt in opts:
                label = opt.get('label', '') if isinstance(opt, dict) else str(opt)
                is_checked = label in selected
                check_items.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Checkbox(
                                value=is_checked,
                                fill_color='#1976D2',
                                disabled=readonly,
                                on_change=lambda e, l=label: _on_check_toggle(l, key, answers, open_enabled),
                            ),
                            ft.Text(label, size=16, color='#212121',
                                    overflow=ft.TextOverflow.VISIBLE, expand=True,
                                    no_wrap=False),
                        ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.START),
                        padding=ft.Padding(4, 6, 4, 6),
                        border_radius=8,
                        bgcolor='#E3F2FD' if is_checked else None,
                        on_click=None if readonly else (lambda e, l=label: _on_check_toggle(l, key, answers, open_enabled)),
                    )
                )
            multi_controls = [ft.Column(check_items, spacing=4)]
            # 题目级开放式文本框（一道多选题仅一个）
            if open_enabled:
                open_tf = ft.TextField(
                    value=selected_open_text,
                    multiline=True,
                    min_lines=2,
                    max_lines=4,
                    hint_text=open_hint or '请输入补充说明...',
                    border_color='#BBDEFB',
                    focused_border_color='#1976D2',
                    text_size=15,
                    on_change=lambda e: _on_multi_open_text_change(e.control.value, key, answers),
                )
                if readonly:
                    open_tf.read_only = True
                open_area = ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Icon(ft.Icons.EDIT_NOTE, size=16, color='#1976D2'),
                            ft.Text(open_title or '开放式文本框', size=15,
                                    weight=ft.FontWeight.W_600, color='#1976D2'),
                        ], spacing=4),
                        open_tf,
                    ], spacing=4),
                    bgcolor='#F5F9FF',
                    border_radius=8,
                    border=ft.Border.all(width=1, color='#BBDEFB'),
                    padding=ft.Padding(10, 8, 10, 8),
                )
                multi_controls.append(
                    ft.Container(content=open_area, padding=ft.Padding(0, 10, 0, 0))
                )
            content = ft.Column(multi_controls, spacing=0)

    elif qtype == 'open':
        tf = ft.TextField(
            value=current_val or '',
            multiline=True,
            min_lines=4,
            max_lines=8,
            hint_text='请输入您的回答...',
            border_color='#BBDEFB',
            focused_border_color='#1976D2',
            text_size=16,
            expand=True,
            on_change=lambda e: on_answer_change(e.control.value),
        )
        if readonly:
            tf.read_only = True
        content = tf

    else:
        content = ft.Text(f'未知题型: {qtype}', color='#FF5252', size=15)

    type_labels = {'single_choice': '单选题', 'multiple_choice': '多选题', 'open': '开放题'}
    type_label = type_labels.get(qtype, qtype)

    column_controls = []
    column_controls.append(
        ft.Row([
            ft.Container(
                content=ft.Text(type_label, size=13, color='white'),
                bgcolor='#1976D2', border_radius=10,
                padding=ft.Padding(8, 2, 8, 2),
            ),
            ft.Container(width=8, height=8, border_radius=4,
                         bgcolor='#FF5252' if is_unanswered else 'transparent'),
        ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
    )
    column_controls.append(ft.Divider(height=8, color='transparent'))
    column_controls.append(
        ft.Text(question['question_text'], size=16, weight=ft.FontWeight.W_500, color='#212121',
                overflow=ft.TextOverflow.VISIBLE))

    hint = (question.get('hint') or '').strip()
    if hint:
        hint_lines = [l.strip() for l in hint.split('\n') if l.strip()]
        if hint_lines:
            column_controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Icon(ft.Icons.LIGHTBULB_OUTLINE, size=16, color='#FF8F00'),
                            ft.Text('作答提示', size=15, color='#FF8F00',
                                    weight=ft.FontWeight.W_600),
                        ], spacing=4),
                        *[ft.Text(f'{i}. {line}', size=15, color='#FF8F00', italic=True,
                                  overflow=ft.TextOverflow.VISIBLE)
                          for i, line in enumerate(hint_lines, 1)],
                    ], spacing=2),
                    bgcolor='#FFF8E1',
                    border_radius=8,
                    padding=ft.Padding(10, 8, 10, 8),
                )
            )

    column_controls.append(ft.Divider(height=12, color='transparent'))
    column_controls.append(content)

    return ft.Container(
        content=ft.Column(column_controls, spacing=0),
        bgcolor='#FAFAFA',
        border_radius=10,
        border=ft.Border.all(width=1, color=border_color),
        padding=16,
    )


def _on_single_select(option: dict, key: str, answers: dict, rebuild, radio_column):
    """单选：选择某个选项。若该选项配置了开放式文本框，答案保存为 dict。"""
    label = option.get('label', '')
    if option.get('requires_open'):
        # 保留已填写的补充文本（切换选项时不丢失）
        cur = answers.get(key)
        cur_open = cur.get('open_text', '') if isinstance(cur, dict) else ''
        answers[key] = {'option': label, 'open_text': cur_open}
    else:
        answers[key] = label
    rebuild()


def _on_open_text_change(option_label: str, value: str, key: str, answers: dict):
    """单选：开放式文本框内容变更，保存为 dict 答案"""
    answers[key] = {'option': option_label, 'open_text': value}


def _on_check_toggle(option_label: str, key: str, answers: dict, open_enabled: bool = False):
    """多选：切换某个选项的选中状态

    若题目启用了开放式文本框，答案保存为 dict: {'options': [...], 'open_text': '...'}
    """
    cur = answers.get(key)
    # 兼容 dict 答案
    if isinstance(cur, dict):
        selected = cur.get('options', []) if isinstance(cur.get('options'), list) else []
        if option_label in selected:
            selected.remove(option_label)
        else:
            selected.append(option_label)
        answers[key] = {'options': selected, 'open_text': cur.get('open_text', '')}
        return
    # list / 首次作答
    selected = cur if isinstance(cur, list) else []
    if option_label in selected:
        selected.remove(option_label)
    else:
        selected.append(option_label)
    if open_enabled:
        # 题目启用了开放式文本框，保存 dict 结构
        answers[key] = {'options': selected, 'open_text': ''}
    else:
        answers[key] = selected


def _on_multi_open_text_change(value: str, key: str, answers: dict):
    """多选题开放式文本框内容变更"""
    cur = answers.get(key)
    if isinstance(cur, dict):
        selected = cur.get('options', []) if isinstance(cur.get('options'), list) else []
        answers[key] = {'options': selected, 'open_text': value}
    else:
        # 未选选项时也保留文本
        selected = cur if isinstance(cur, list) else []
        answers[key] = {'options': selected, 'open_text': value}
