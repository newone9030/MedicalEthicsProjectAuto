"""
题目服务：案例题目 CRUD 和排序
"""

import json
from app.db import get_connection


def add_question(case_id: int, question_text: str, question_type: str,
                 options: list = None, sort_order: int = None, hint: str = None) -> dict:
    """添加题目到案例"""
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

        options_json = json.dumps(options, ensure_ascii=False) if options else None

        cursor.execute("""
            INSERT INTO case_questions (case_id, question_text, question_type, options, sort_order, hint)
            VALUES (:cid, :qtext, :qtype, :opts, :sorder, :hint)
        """, {
            'cid': case_id,
            'qtext': question_text,
            'qtype': question_type,
            'opts': options_json,
            'sorder': sort_order,
            'hint': hint
        })
        conn.commit()
        qid = cursor.lastrowid

        return {'success': True, 'message': '题目已添加', 'question_id': qid}


def update_question(question_id: int, question_text: str, question_type: str,
                    options: list = None, hint: str = None) -> dict:
    """更新题目"""
    if question_type == 'multiple_choice' and (not options or len(options) < 2):
        return {'success': False, 'message': '多选题至少需要2个选项'}

    if question_type == 'single_choice' and (not options or len(options) < 1):
        return {'success': False, 'message': '单选题至少需要1个选项'}

    with get_connection() as conn:
        cursor = conn.cursor()

        options_json = json.dumps(options, ensure_ascii=False) if options else None

        cursor.execute("""
            UPDATE case_questions
            SET question_text = :qtext, question_type = :qtype, options = :opts, hint = :hint
            WHERE id = :qid
        """, {
            'qtext': question_text,
            'qtype': question_type,
            'opts': options_json,
            'hint': hint,
            'qid': question_id
        })
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
            SELECT id, case_id, question_text, question_type, options, sort_order, hint
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
                    options = json.loads(opts)
                except (json.JSONDecodeError, TypeError):
                    options = []
            else:
                options = []

            questions.append({
                'id': row[0],
                'case_id': row[1],
                'question_text': row[2],
                'question_type': row[3],
                'options': options,
                'sort_order': row[5],
                'hint': row[6] or '',
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
