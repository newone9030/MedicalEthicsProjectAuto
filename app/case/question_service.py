"""
题目服务：案例题目 CRUD 和排序
"""

import json
from app.db import get_connection


def normalize_options(raw_options) -> list:
    """
    规范化选项列表，兼容两种存储格式：
    - 旧数据：字符串数组 ['A', 'B']
    - 新数据：对象数组 [{'label': 'A', 'requires_open': False, 'open_hint': ''}]
    统一返回对象数组。
    """
    if not isinstance(raw_options, list):
        return []
    normalized = []
    for opt in raw_options:
        if isinstance(opt, dict):
            normalized.append({
                'label': str(opt.get('label', opt.get('text', ''))),
                'requires_open': bool(opt.get('requires_open', False)),
                'open_hint': str(opt.get('open_hint', '') or ''),
                'exclusive_with': _clean_exclusive(opt.get('exclusive_with')),
            })
        else:
            normalized.append({
                'label': str(opt),
                'requires_open': False,
                'open_hint': '',
                'exclusive_with': [],
            })
    return normalized


def _clean_exclusive(val) -> list:
    """
    规范化互斥选项索引列表：只保留非负整数、去重、升序。
    互斥关系以选项索引（index）记录，索引从 0 开始。
    """
    if not isinstance(val, list):
        return []
    out = []
    for v in val:
        if isinstance(v, bool):
            continue
        try:
            iv = int(v)
        except (TypeError, ValueError):
            continue
        if iv >= 0 and iv not in out:
            out.append(iv)
    return sorted(out)


def add_question(case_id: int, question_text: str, question_type: str,
                 options: list = None, sort_order: int = None, hint: str = None,
                 open_text_enabled: bool = False,
                 open_text_title: str = None, open_text_hint: str = None,
                 section_title: str = None, is_required: bool = True) -> dict:
    """添加题目到案例

    open_text_enabled / open_text_title / open_text_hint:
        多选题题目级开放式文本框配置（一道多选题仅一个开放式文本框）。
    section_title:
        分组标题（可选）。填写后本题开启一个新部分，标题跟随其后题目直到下一个标题。
    is_required:
        是否必答。默认 True（必答）。
    """
    if question_type not in ('single_choice', 'multiple_choice', 'open'):
        return {'success': False, 'message': '无效的题目类型'}

    # 多选题至少要有2个选项
    if question_type == 'multiple_choice' and (not options or len(options) < 2):
        return {'success': False, 'message': '多选题至少需要2个选项'}

    # 单选题至少要有1个选项
    if question_type == 'single_choice' and (not options or len(options) < 1):
        return {'success': False, 'message': '单选题至少需要1个选项'}

    with get_connection() as conn:
        cursor = conn.cursor()

        # 自动计算排序号
        if sort_order is None:
            cursor.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM case_questions WHERE case_id = :cid",
                {'cid': case_id}
            )
            sort_order = cursor.fetchone()[0]

        options_json = json.dumps(normalize_options(options), ensure_ascii=False) if options else None

        cursor.execute("""
            INSERT INTO case_questions (case_id, question_text, question_type, options, sort_order, hint,
                                        open_text_enabled, open_text_title, open_text_hint, section_title,
                                        is_required)
            VALUES (:cid, :qtext, :qtype, :opts, :sorder, :hint,
                    :open_enabled, :open_title, :open_hint, :section_title, :is_required)
        """, {
            'cid': case_id,
            'qtext': question_text,
            'qtype': question_type,
            'opts': options_json,
            'sorder': sort_order,
            'hint': hint,
            'open_enabled': 1 if open_text_enabled else 0,
            'open_title': (open_text_title or '').strip() if open_text_enabled else None,
            'open_hint': (open_text_hint or '').strip() if open_text_enabled else None,
            'section_title': (section_title or '').strip() or None,
            'is_required': 1 if is_required else 0,
        })
        conn.commit()
        qid = cursor.lastrowid

        return {'success': True, 'message': '题目已添加', 'question_id': qid}


def update_question(question_id: int, question_text: str, question_type: str,
                    options: list = None, hint: str = None,
                    open_text_enabled: bool = None,
                    open_text_title: str = None, open_text_hint: str = None,
                    section_title: str = None, is_required: bool = None) -> dict:
    """更新题目

    open_text_enabled / open_text_title / open_text_hint:
        多选题题目级开放式文本框配置（一道多选题仅一个开放式文本框）。
        open_text_enabled 为 None 时不修改开放式文本框配置。
    section_title:
        分组标题（可选）。None 时不修改；传 '' 表示清除分组标题。
    is_required:
        是否必答。None 时不修改。
    """
    if question_type == 'multiple_choice' and (not options or len(options) < 2):
        return {'success': False, 'message': '多选题至少需要2个选项'}

    if question_type == 'single_choice' and (not options or len(options) < 1):
        return {'success': False, 'message': '单选题至少需要1个选项'}

    with get_connection() as conn:
        cursor = conn.cursor()

        options_json = json.dumps(normalize_options(options), ensure_ascii=False) if options else None

        # 动态拼装 UPDATE 子句：None 参数表示不修改对应字段
        set_parts = ['question_text = :qtext', 'question_type = :qtype',
                     'options = :opts', 'hint = :hint']
        params = {
            'qtext': question_text,
            'qtype': question_type,
            'opts': options_json,
            'hint': hint,
            'qid': question_id,
        }
        if open_text_enabled is not None:
            set_parts += ['open_text_enabled = :open_enabled',
                          'open_text_title = :open_title',
                          'open_text_hint = :open_hint']
            params['open_enabled'] = 1 if open_text_enabled else 0
            params['open_title'] = (open_text_title or '').strip() if open_text_enabled else None
            params['open_hint'] = (open_text_hint or '').strip() if open_text_enabled else None
        if section_title is not None:
            set_parts.append('section_title = :section_title')
            params['section_title'] = (section_title or '').strip() or None
        if is_required is not None:
            set_parts.append('is_required = :is_required')
            params['is_required'] = 1 if is_required else 0
        cursor.execute(
            f"UPDATE case_questions SET {', '.join(set_parts)} WHERE id = :qid",
            params
        )
        conn.commit()

        return {'success': True, 'message': '题目已更新'}


def delete_question(question_id: int) -> dict:
    """删除题目"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM case_questions WHERE id = :qid", {'qid': question_id})
        conn.commit()
        return {'success': True, 'message': '题目已删除'}


def get_questions_by_case(case_id: int) -> list:
    """获取案例的所有题目（按 sort_order 排序）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, case_id, question_text, question_type, options, sort_order, hint,
                   open_text_enabled, open_text_title, open_text_hint, section_title, is_required
            FROM case_questions
            WHERE case_id = :cid
            ORDER BY sort_order
        """, {'cid': case_id})

        rows = cursor.fetchall()
        questions = []
        for row in rows:
            opts = row[4]
            if opts:
                try:
                    raw_options = json.loads(opts)
                except (json.JSONDecodeError, TypeError):
                    raw_options = []
            else:
                raw_options = []
            options = normalize_options(raw_options)

            questions.append({
                'id': row[0],
                'case_id': row[1],
                'question_text': row[2],
                'question_type': row[3],
                'options': options,
                'sort_order': row[5],
                'hint': row[6] or '',
                'open_text_enabled': bool(row[7]),
                'open_text_title': row[8] or '',
                'open_text_hint': row[9] or '',
                'section_title': row[10] or '',
                'is_required': bool(row[11]) if len(row) > 11 else True,
            })
        return questions


def reorder_questions(case_id: int, question_ids: list) -> dict:
    """重新排序题目（按 question_ids 顺序更新 sort_order）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        for i, qid in enumerate(question_ids):
            cursor.execute(
                "UPDATE case_questions SET sort_order = :sorder WHERE id = :qid AND case_id = :cid",
                {'sorder': i, 'qid': qid, 'cid': case_id}
            )
        conn.commit()
    return {'success': True, 'message': '排序已更新'}
