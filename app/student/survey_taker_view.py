"""
问卷作答视图 - 逐题显示版本
每页显示一道题目，支持"上一题"/"下一题"切换、逐题暂存、一次性提交全部
页面控件先加载，数据通过 page.run_task 延迟加载
"""
import json
import re
import threading
import flet as ft
from app.task.task_service import get_task, get_background_task, is_task_unlocked_for_student
from app.case.question_service import get_questions_by_case
from app.response.response_service import (save_draft, submit_response, get_draft_answers,
                                           get_submitted_answers, get_submission_status,
                                           is_background_completed)


# 开放性文本案例最少回答汉字数（ycs / test 账号豁免）
MIN_OPEN_TEXT_CHARS = 50
_EXEMPT_MIN_CHARS_USERNAMES = {'ycs', 'test'}


def _count_chinese_chars(value) -> int:
    """统计答案中的汉字数量（兼容字符串 / 列表 / 字典结构）"""
    text = ''
    if isinstance(value, str):
        text = value
    elif isinstance(value, dict):
        text = value.get('open_text') or ''
    elif isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict) and item.get('open_text'):
                parts.append(str(item['open_text']))
            elif isinstance(item, str):
                parts.append(item)
        text = ''.join(parts)
    if not isinstance(text, str):
        text = str(text)
    return len(re.findall(r'[\u4e00-\u9fff]', text))


def is_mobile_width(page: ft.Page) -> bool:
    """判断当前视口是否为手机窄屏（用于收窄内边距）"""
    return bool(page) and bool(page.width) and page.width < 600


def build_survey_taker_view(page: ft.Page, task_id: int, on_back=None, readonly: bool = False) -> list:
    """问卷作答视图 - 逐题显示，数据延迟加载"""
    user = page.session.store.get('user')
    student_id = user['id']

    # 记录构建时的视图代际：页面切换后旧视图的延迟加载调度应立即停止
    _view_gen = page.session.store.get('_view_generation') or 0

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

    # 构建阶段同步预加载时：控件尚未挂载，直接调用 update() 会抛
    # "Control must be added to the page first"。以下辅助函数在未挂载时
    # 跳过更新，填充好的内容随 route_change 末尾的 page.update() 一次性渲染。
    _sync_build = [False]

    def _safe_update(ctrl):
        try:
            if ctrl.parent is not None:
                ctrl.update()
        except Exception:
            pass

    def _page_update():
        if not _sync_build[0]:
            try:
                page.update()
            except Exception:
                pass

    # SnackBar 辅助
    def _show_snack(msg: str, success: bool = True):
        # 清理旧的 SnackBar，避免 overlay 控件无限累积导致页面越来越卡
        for s in [s for s in page.overlay if isinstance(s, ft.SnackBar)]:
            page.overlay.remove(s)
        snack = ft.SnackBar(ft.Text(msg, size=15), bgcolor='#4CAF50' if success else '#FF5252')
        page.overlay.append(snack)
        snack.open = True
        page.update()

    def _close_overlay_dlg(dialog):
        # Flet 0.86.5 官方关闭方式：只 open=False + update。
        # 不能发 remove 命令——show_dialog 已包装 on_dismiss，客户端确认关闭后
        # 会自动把对话框移出对话框栈，手动 remove 反而导致模态框不消失。
        # 注意：直接用闭包 page，dialog.page 在控件脱离树时可能抛异常。
        dialog.open = False
        page.update()

    def _cleanup_stale_overlay(keep=None):
        """清理对话框栈中已关闭的旧对话框（open=False），避免无限累积导致卡顿"""
        dialogs = getattr(page, '_dialogs', None)
        if dialogs is None:
            return
        for c in [c for c in dialogs.controls
                  if isinstance(c, ft.AlertDialog) and c is not keep and not c.open]:
            try:
                page._remove_dialog(c)
            except Exception:
                pass

    def _open_overlay_dlg(dlg):
        """打开对话框（Flet 0.86.5 官方 API）：先清理旧对话框（防累积），
        再 page.show_dialog 挂载（自动包装 on_dismiss，关闭后自动出栈）。"""
        _cleanup_stale_overlay(keep=dlg)
        dialogs = getattr(page, '_dialogs', None)
        if dialogs is not None and dlg in dialogs.controls:
            if dlg.open:
                return  # 已在显示中，忽略重复触发
            try:
                page._remove_dialog(dlg)
            except Exception:
                pass
        try:
            page.show_dialog(dlg)
        except RuntimeError:
            pass

    # ================================================================
    # Phase 2: 数据加载（通过 page.run_task 延迟执行）
    # ================================================================

    def refresh_task():
        """加载所有数据并更新 UI（同步函数，无 await）"""
        try:
            # 若页面已切换（代际变化），旧视图任务直接放弃，避免操作已移除控件
            if (page.session.store.get('_view_generation') or 0) != _view_gen:
                print('[survey] refresh_task 执行时视图已切换，放弃加载')
                return
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
                _page_update()
                return

            # ---- 背景资料未完成时禁止作答（只读查看不受限） ----
            if not readonly:
                bg_task = get_background_task()
                if bg_task and not is_background_completed(bg_task['id'], student_id):
                    question_container.controls.clear()
                    question_container.controls.append(
                        ft.Container(
                            content=ft.Column([
                                ft.Icon(ft.Icons.LOCK_OUTLINE, size=48, color='#FF9800'),
                                ft.Text('请先完成背景资料调查', size=18, color='#FF9800'),
                                ft.Text('返回任务列表填写背景资料后再进入作答', size=14, color='#757575'),
                                ft.TextButton(content=ft.Text('返回', size=16),
                                              on_click=lambda e: on_back() if on_back else None),
                            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                            alignment=ft.Alignment(0, 0),
                            expand=True,
                        )
                    )
                    progress_text.value = '背景资料未完成'
                    case_label.value = ''
                    _page_update()
                    return

            # ---- 顺序作答限制：前置任务未全部提交时禁止作答（只读查看不受限） ----
            if not readonly and not is_task_unlocked_for_student(task_id, student_id):
                question_container.controls.clear()
                question_container.controls.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Icon(ft.Icons.LOCK_OUTLINE, size=48, color='#FF9800'),
                            ft.Text('请先完成前面的任务', size=18, color='#FF9800'),
                            ft.Text('按任务顺序作答，完成前置任务后再进入本任务', size=14, color='#757575'),
                            ft.TextButton(content=ft.Text('返回', size=16),
                                          on_click=lambda e: on_back() if on_back else None),
                        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                        alignment=ft.Alignment(0, 0),
                        expand=True,
                    )
                )
                progress_text.value = '任务未解锁'
                case_label.value = ''
                _page_update()
                return

            task_title_text.value = task['name']
            _safe_update(task_title_text)

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
                _page_update()
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
                _page_update()
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
                _page_update()
                return

            # ---- 内部函数：进度统计 ----
            def count_completed():
                return sum(1 for key, val in all_answers.items()
                           if val is not None and val != '' and
                           (not isinstance(val, (list, dict)) or len(val) > 0) and
                           not (isinstance(val, dict) and not val.get('options') and not val.get('open_text') and not val.get('option')))

            def update_progress():
                completed = count_completed()
                progress_text.value = f'进度: {completed}/{total_q_count} 题已完成'
                progress_bar.value = completed / total_q_count if total_q_count > 0 else 0
                _safe_update(progress_text)
                _safe_update(progress_bar)

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
                _safe_update(prev_btn)
                _safe_update(next_btn)
                _safe_update(save_btn)
                _safe_update(submit_all_btn)

            # ---- 构建当前题目显示 ----
            def build_question_content():
                case, question, qi, qs_len = flat_questions[current_idx[0]]
                num_in_task = current_idx[0] + 1

                case_label.value = f'案例 {_case_order(case, active_cases)}/{len(active_cases)}: {case["title"]}  |  第 {qi + 1}/{qs_len} 题'
                _safe_update(case_label)

                question_container.controls.clear()
                w = _build_question_widget(question, f"{case['id']}_{question['id']}", all_answers, readonly, page)
                question_container.controls.append(w)
                _safe_update(question_container)

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
                        is_required = bool(q.get('is_required', True))
                        if (is_required and (ans is None or ans == '' or
                                (isinstance(ans, list) and len(ans) == 0) or
                                (isinstance(ans, dict) and not ans.get('options') and not ans.get('open_text') and not ans.get('option')))):
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
                        title=ft.Text('\u8BF7\u5B8C\u6210\u6240\u6709\u5FC5\u7B54\u9898', size=16),
                        content=ft.Text(
                            f'\u4EE5\u4E0B {len(all_unanswered)} \u9053\u5FC5\u7B54\u9898\u5C1A\u672A\u4F5C\u7B54\uFF1A\n\n' + '\n'.join(lines),
                            size=15),
                        actions=[ft.TextButton(content=ft.Text('\u77E5\u9053\u4E86', size=15),
                                                on_click=lambda e: _close_overlay_dlg(dlg))],
                        modal=True,
                    )
                    _open_overlay_dlg(dlg)
                    return

                # ---- 开放性文本案例逐题最少汉字预校验（ycs / test 账号豁免） ----
                username = (page.session.store.get('user') or {}).get('username', '')
                if username not in _EXEMPT_MIN_CHARS_USERNAMES:
                    short_questions = []
                    for case in active_cases:
                        questions = all_questions_map.get(case['id'], [])
                        if questions and all(q.get('question_type') == 'open' for q in questions):
                            for q in questions:
                                if not q.get('is_required', True):
                                    continue  # 非必答题可跳过，不参与字数校验
                                chars = _count_chinese_chars(all_answers.get(f"{case['id']}_{q['id']}"))
                                if chars < MIN_OPEN_TEXT_CHARS:
                                    short_questions.append((case['title'], q.get('question_text', '')[:30], chars))
                    if short_questions:
                        lines = [f'• [{title}] {qtext}（当前 {n} 个汉字）' for title, qtext, n in short_questions[:5]]
                        if len(short_questions) > 5:
                            lines.append(f'... 及其他 {len(short_questions) - 5} 道题')
                        dlg = ft.AlertDialog(
                            title=ft.Text(f'开放性文本题目回答不能少于 {MIN_OPEN_TEXT_CHARS} 个汉字', size=16),
                            content=ft.Text('以下题目尚未达到最少字数：\n\n' + '\n'.join(lines), size=15),
                            actions=[ft.TextButton(content=ft.Text('知道了', size=15),
                                                    on_click=lambda e: _close_overlay_dlg(dlg))],
                            modal=True,
                        )
                        _open_overlay_dlg(dlg)
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
                        # 作答完成一个任务后直接返回任务列表（测试用户也通过
                        # dashboard 上的反馈入口在全部任务完成后填写反馈）
                        if on_back:
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
                _open_overlay_dlg(self_check_dlg)

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
            _page_update()

    # 调度数据加载任务：等待页面控件加载完成后才执行（挂载前不调用任何方法）
    def _schedule_init(retry: int = 0):
        # 页面已切换（代际变化），旧视图调度立即停止，避免操作已移除控件
        if (page.session.store.get('_view_generation') or 0) != _view_gen:
            print('[survey] 视图已切换，放弃加载调度')
            return
        if question_container.parent is None:
            # 限制最大重试次数，防止视图构建失败时无限递归创建线程导致卡死
            if retry >= 100:
                print('[survey] question_container 长时间未挂载，放弃调度')
                return
            threading.Timer(0.05, _schedule_init, args=[retry + 1]).start()
            return
        # 通过 page.run_task 在 Flet 事件循环中执行加载
        async def _async_init():
            if (page.session.store.get('_view_generation') or 0) != _view_gen:
                print('[survey] 加载执行时视图已切换，放弃')
                return
            try:
                refresh_task()
            except Exception:
                import traceback
                traceback.print_exc()

        page.run_task(_async_init)

    _schedule_init()

    # 首次加载同步填充内容：构建阶段控件树尚未挂载，refresh_task 内部的
    # 更新调用会被 _safe_update/_page_update 安全跳过，填充好的内容随
    # route_change 末尾的 page.update() 一次性渲染。即使异步调度
    # （Timer + parent 检测 + run_task）任一环节异常，页面也不会永远
    # 停留在"正在加载题目数据..."。异步调度仍保留用于后续刷新。
    _sync_build[0] = True
    try:
        refresh_task()
    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        _sync_build[0] = False

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
                padding=16 if is_mobile_width(page) else 20,
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


def _build_question_widget(question: dict, key: str, answers: dict, readonly: bool,
                           page: ft.Page = None) -> ft.Container:
    """构建单个题目组件"""
    qid = question['id']
    qtype = question['question_type']
    is_required = bool(question.get('is_required', True))
    current_val = answers.get(key)

    unanswered_raw = (
        current_val is None or current_val == '' or
        (isinstance(current_val, list) and len(current_val) == 0) or
        (isinstance(current_val, dict) and not current_val.get('options') and not current_val.get('open_text') and not current_val.get('option'))
    )
    # 仅必答题未作答时标红提醒
    is_unanswered = not readonly and is_required and unanswered_raw
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
                                ft.Text(label, size=20, color='#212121',
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
            # 归一化选项（携带 index 与互斥配置），供互斥校验使用
            norm_opts = []
            for i, opt in enumerate(opts):
                if isinstance(opt, dict):
                    excl_idx = []
                    for x in (opt.get('exclusive_with') or []):
                        if isinstance(x, bool):
                            continue
                        if isinstance(x, int) and x >= 0:
                            excl_idx.append(x)
                        elif isinstance(x, str) and x.isdigit():
                            excl_idx.append(int(x))
                    norm_opts.append({'label': opt.get('label', ''), 'index': i, 'exclusive_with': excl_idx})
                else:
                    norm_opts.append({'label': str(opt), 'index': i, 'exclusive_with': []})
            check_items = []
            for opt in norm_opts:
                label = opt['label']
                is_checked = label in selected
                check_items.append(
                    ft.Container(
                        # 只用 Checkbox 单一事件绑定（on_change），
                        # 避免 on_click + on_change 双重触发导致答案被抵消/状态错乱
                        content=ft.Checkbox(
                            value=is_checked,
                            label=label,
                            label_style=ft.TextStyle(size=20, color='#212121'),
                            fill_color='#1976D2',
                            disabled=readonly,
                            on_change=(lambda e, o=opt: _on_check_toggle(o['label'], key, answers, open_enabled,
                                                                         norm_opts, page, e.control))
                            if not readonly else None,
                        ),
                        padding=ft.Padding(4, 6, 4, 6),
                        border_radius=8,
                        bgcolor='#E3F2FD' if is_checked else None,
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
    # 部分标题（分组标题）：本题开启一个新部分时，在题目上方显示标题栏
    section_title = (question.get('section_title') or '').strip()
    if section_title:
        column_controls.append(
            ft.Container(
                content=ft.Row([
                    ft.Container(width=4, height=20, bgcolor='#1976D2', border_radius=2),
                    ft.Text(section_title, size=18, weight=ft.FontWeight.BOLD, color='#1565C0',
                            overflow=ft.TextOverflow.VISIBLE),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor='#E3F2FD',
                border_radius=8,
                padding=ft.Padding(12, 8, 12, 8),
            )
        )
        column_controls.append(ft.Divider(height=6, color='transparent'))
    header_row_controls = [
        ft.Container(
            content=ft.Text(type_label, size=13, color='white'),
            bgcolor='#1976D2', border_radius=10,
            padding=ft.Padding(8, 2, 8, 2),
        ),
        ft.Container(width=8, height=8, border_radius=4,
                     bgcolor='#FF5252' if is_unanswered else 'transparent'),
    ]
    if is_required:
        header_row_controls.append(
            ft.Container(
                content=ft.Text('必答', size=12, color='#FF5252'),
                border=ft.Border.all(width=1, color='#FF5252'),
                border_radius=6,
                padding=ft.Padding(6, 1, 6, 1),
            )
        )
    column_controls.append(
        ft.Row(header_row_controls, spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER),
    )
    column_controls.append(ft.Divider(height=8, color='transparent'))
    column_controls.append(
        ft.Text(question['question_text'], size=20, weight=ft.FontWeight.W_500, color='#212121',
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
                            ft.Text('作答提示', size=19, color='#1565C0',
                                    weight=ft.FontWeight.W_600),
                        ], spacing=4),
                        *[ft.Text(f'{i}. {line}', size=20, color='#1565C0',
                                  overflow=ft.TextOverflow.VISIBLE)
                          for i, line in enumerate(hint_lines, 1)],
                    ], spacing=2),
                    bgcolor='#E3F2FD',
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
        padding=12 if is_mobile_width(page) else 16,
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


def _on_check_toggle(option_label: str, key: str, answers: dict, open_enabled: bool = False,
                     norm_opts: list = None, page: ft.Page = None, control: ft.Checkbox = None):
    """多选：切换某个选项的选中状态

    若题目启用了开放式文本框，答案保存为 dict: {'options': [...], 'open_text': '...'}
    若选项配置了互斥关系（exclusive_with），与已选中的互斥选项冲突时阻止勾选并提示。
    """
    cur = answers.get(key)
    # 兼容 dict 答案
    if isinstance(cur, dict):
        selected = cur.get('options', []) if isinstance(cur.get('options'), list) else []
        open_text = cur.get('open_text', '')
    else:
        selected = cur if isinstance(cur, list) else []
        open_text = ''

    if option_label in selected:
        selected.remove(option_label)
    else:
        # 互斥校验：勾选前检查与已选中的选项是否冲突
        if _check_exclusive_conflict(option_label, selected, norm_opts):
            if control is not None:
                try:
                    control.value = False
                    control.update()
                except Exception:
                    pass
            _show_snack_page(page, f'选项「{option_label}」与「{_find_conflict_label(option_label, selected, norm_opts)}」不能同时选择', success=False)
            return
        selected.append(option_label)

    if open_enabled:
        # 题目启用了开放式文本框，保存 dict 结构
        answers[key] = {'options': selected, 'open_text': open_text}
    else:
        answers[key] = selected


def _check_exclusive_conflict(label: str, selected: list, norm_opts: list) -> bool:
    """判断 label 是否与已选中选项存在互斥冲突"""
    return _find_conflict_label(label, selected, norm_opts) is not None


def _find_conflict_label(label: str, selected: list, norm_opts: list):
    """返回与 label 互斥冲突的已选中选项 label；无冲突返回 None"""
    if not norm_opts or not selected:
        return None
    idx_map = {o['label']: o['index'] for o in norm_opts}
    excl_map = {o['label']: set(o.get('exclusive_with') or []) for o in norm_opts}
    my_idx = idx_map.get(label)
    if my_idx is None:
        return None
    for sel in selected:
        sel_idx = idx_map.get(sel)
        if sel_idx is None:
            continue
        if my_idx in excl_map.get(sel, set()) or sel_idx in excl_map.get(label, set()):
            return sel
    return None


def _show_snack_page(page: ft.Page, msg: str, success: bool = True):
    """页面级 SnackBar 提示（用于互斥冲突等）"""
    if page is None:
        return
    try:
        # 清理旧的 SnackBar，避免 overlay 控件无限累积导致页面越来越卡
        for s in [s for s in page.overlay if isinstance(s, ft.SnackBar)]:
            page.overlay.remove(s)
        snack = ft.SnackBar(
            ft.Text(msg, size=14),
            bgcolor='#4CAF50' if success else '#FF5252',
            duration=2500,
        )
        page.overlay.append(snack)
        snack.open = True
        page.update()
    except Exception:
        pass


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
