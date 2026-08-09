"""
作答记录服务：提交校验、时间窗口校验、防重复、暂存、批量写入
"""

import json
from datetime import datetime
from app.db import get_connection


def save_draft(task_id: int, case_id: int, student_id: int, answers: dict) -> dict:
    """
    暂存草稿
    answers: {question_id: answer_value}
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        # 检查是否已有记录
        cursor.execute("""
            SELECT id, status FROM responses
            WHERE task_id = :tid AND case_id = :cid AND student_id = :sid
        """, {'tid': task_id, 'cid': case_id, 'sid': student_id})

        row = cursor.fetchone()
        if row and row[1] == 'submitted':
            return {'success': False, 'message': '该案例已提交，无法暂存'}

        if row:
            # 更新已有草稿
            response_id = row[0]
            cursor.execute("""
                UPDATE responses SET status = 'draft', updated_at = CURRENT_TIMESTAMP
                WHERE id = :rid
            """, {'rid': response_id})
            # 删除旧明细
            cursor.execute("DELETE FROM response_details WHERE response_id = :rid", {'rid': response_id})
        else:
            # 新建草稿
            cursor.execute("""
                INSERT INTO responses (task_id, case_id, student_id, status)
                VALUES (:tid, :cid, :sid, 'draft')
            """, {'tid': task_id, 'cid': case_id, 'sid': student_id})
            cursor.execute("SELECT last_insert_rowid()")
            response_id = cursor.fetchone()[0]

        # 写入答案明细
        for question_id, answer in answers.items():
            answer_val = json.dumps(answer, ensure_ascii=False) if isinstance(answer, list) else str(answer) if answer is not None else ''
            cursor.execute("""
                INSERT INTO response_details (response_id, question_id, answer)
                VALUES (:rid, :qid, :ans)
            """, {'rid': response_id, 'qid': question_id, 'ans': answer_val})

        conn.commit()
        return {'success': True, 'message': '已保存草稿'}


def submit_response(task_id: int, case_id: int, student_id: int, answers: dict,
                    all_question_ids: list) -> dict:
    """
    提交作答
    answers: {question_id: answer_value}
    all_question_ids: 该案例所有题目ID列表（用于完整性校验）
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        # 1. 检查是否已提交
        cursor.execute("""
            SELECT id, status FROM responses
            WHERE task_id = :tid AND case_id = :cid AND student_id = :sid
        """, {'tid': task_id, 'cid': case_id, 'sid': student_id})
        row = cursor.fetchone()
        if row and row[1] == 'submitted':
            return {'success': False, 'message': '您已提交过该案例'}

        # 2. 校验时间窗口
        cursor.execute("""
            SELECT start_time, end_time, status FROM tasks WHERE id = :tid
        """, {'tid': task_id})
        task_row = cursor.fetchone()
        if not task_row:
            return {'success': False, 'message': '任务不存在'}

        now = datetime.now()
        start_time = task_row[0] if isinstance(task_row[0], datetime) else datetime.fromisoformat(task_row[0])
        end_time = task_row[1] if isinstance(task_row[1], datetime) else datetime.fromisoformat(task_row[1])
        if task_row[2] != 'active' or now < start_time or now > end_time:
            return {'success': False, 'message': '当前不在任务有效期内，无法提交'}

        # 3. 完整性校验 - 所有题目必须作答
        unanswered = []
        for qid in all_question_ids:
            ans = answers.get(str(qid)) or answers.get(qid)
            if ans is None or ans == '' or ans == []:
                unanswered.append(qid)

        if unanswered:
            return {
                'success': False,
                'message': f'还有 {len(unanswered)} 道题未作答，请完成所有题目后再提交',
                'unanswered': unanswered
            }

        # 4. 写入或更新
        if row:
            response_id = row[0]
            cursor.execute("""
                UPDATE responses SET status = 'submitted', submitted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = :rid
            """, {'rid': response_id})
            cursor.execute("DELETE FROM response_details WHERE response_id = :rid", {'rid': response_id})
        else:
            cursor.execute("""
                INSERT INTO responses (task_id, case_id, student_id, status, submitted_at)
                VALUES (:tid, :cid, :sid, 'submitted', CURRENT_TIMESTAMP)
            """, {'tid': task_id, 'cid': case_id, 'sid': student_id})
            cursor.execute("SELECT last_insert_rowid()")
            response_id = cursor.fetchone()[0]

        # 写入答案明细
        for question_id, answer in answers.items():
            answer_val = json.dumps(answer, ensure_ascii=False) if isinstance(answer, list) else str(answer) if answer is not None else ''
            cursor.execute("""
                INSERT INTO response_details (response_id, question_id, answer)
                VALUES (:rid, :qid, :ans)
            """, {'rid': response_id, 'qid': question_id, 'ans': answer_val})

        conn.commit()
        return {'success': True, 'message': '提交成功'}


def _load_response_answers(cursor, response_id: int) -> dict:
    """从 response_details 加载答案字典"""
    cursor.execute("""
        SELECT question_id, answer FROM response_details WHERE response_id = :rid
    """, {'rid': response_id})
    answers = {}
    for detail in cursor.fetchall():
        qid = detail[0]
        ans = detail[1]
        try:
            answers[qid] = json.loads(ans)
        except (json.JSONDecodeError, TypeError):
            answers[qid] = ans
    return answers


def get_draft_answers(task_id: int, case_id: int, student_id: int) -> dict:
    """获取暂存答案（用于回填）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT r.id FROM responses r
            WHERE r.task_id = :tid AND r.case_id = :cid AND r.student_id = :sid AND r.status = 'draft'
        """, {'tid': task_id, 'cid': case_id, 'sid': student_id})

        row = cursor.fetchone()
        if not row:
            return {}

        return _load_response_answers(cursor, row[0])


def get_submitted_answers(task_id: int, case_id: int, student_id: int) -> dict:
    """获取已提交答案（用于只读查看）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT r.id FROM responses r
            WHERE r.task_id = :tid AND r.case_id = :cid AND r.student_id = :sid AND r.status = 'submitted'
        """, {'tid': task_id, 'cid': case_id, 'sid': student_id})

        row = cursor.fetchone()
        if not row:
            return {}

        return _load_response_answers(cursor, row[0])


def get_submission_status(task_id: int, student_id: int) -> dict:
    """获取学生某任务所有案例的提交状态"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT tc.case_id, COALESCE(r.status, 'not_started') as status
            FROM task_cases tc
            LEFT JOIN responses r ON tc.task_id = r.task_id
                AND tc.case_id = r.case_id AND r.student_id = :sid
            WHERE tc.task_id = :tid
            ORDER BY tc.sort_order
        """, {'tid': task_id, 'sid': student_id})

        return {row[0]: row[1] for row in cursor.fetchall()}


def get_response_count() -> int:
    """获取总提交数"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM responses WHERE status = 'submitted'")
        return cursor.fetchone()[0]


def delete_student_responses(task_id: int, student_id: int) -> dict:
    """删除学生对某个任务的全部作答，允许重新作答。仅在任务状态为 active 时允许。"""
    from app.task.task_service import auto_update_task_statuses
    auto_update_task_statuses()

    with get_connection() as conn:
        cursor = conn.cursor()

        # 检查任务状态
        cursor.execute("SELECT status FROM tasks WHERE id = :tid", {'tid': task_id})
        row = cursor.fetchone()
        if not row:
            return {'success': False, 'message': '任务不存在'}
        if row[0] != 'active':
            return {'success': False, 'message': '任务已关闭，无法删除作答'}

        return _do_delete_responses(cursor, task_id, student_id, conn)


def admin_delete_student_responses(task_id: int, student_id: int) -> dict:
    """管理员删除某个学生对某个任务的全部作答（不受任务状态限制）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM tasks WHERE id = :tid", {'tid': task_id})
        if not cursor.fetchone():
            return {'success': False, 'message': '任务不存在'}
        return _do_delete_responses(cursor, task_id, student_id, conn)


def admin_delete_all_responses(task_id: int) -> dict:
    """管理员删除某个任务的所有学生作答"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM tasks WHERE id = :tid", {'tid': task_id})
        if not cursor.fetchone():
            return {'success': False, 'message': '任务不存在'}

        # 先删明细
        cursor.execute("""
            DELETE FROM response_details
            WHERE response_id IN (
                SELECT id FROM responses WHERE task_id = :tid
            )
        """, {'tid': task_id})

        # 再删主记录
        cursor.execute("""
            DELETE FROM responses WHERE task_id = :tid
        """, {'tid': task_id})

        deleted = cursor.rowcount
        conn.commit()
        return {'success': True, 'message': f'已删除 {deleted} 条作答记录'}


def _do_delete_responses(cursor, task_id: int, student_id: int, conn) -> dict:
    """内部：删除指定学生的作答"""
    cursor.execute("""
        DELETE FROM response_details
        WHERE response_id IN (
            SELECT id FROM responses
            WHERE task_id = :tid AND student_id = :sid
        )
    """, {'tid': task_id, 'sid': student_id})

    cursor.execute("""
        DELETE FROM responses
        WHERE task_id = :tid AND student_id = :sid
    """, {'tid': task_id, 'sid': student_id})

    conn.commit()
    return {'success': True, 'message': '作答已删除'}


def get_task_response_summary(task_id: int) -> list:
    """获取任务下所有学生的作答概况"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.username, u.real_name,
                   COUNT(DISTINCT r.case_id) as submitted_count,
                   (SELECT COUNT(*) FROM task_cases WHERE task_id = :tid) as total_cases
            FROM users u
            INNER JOIN responses r ON u.id = r.student_id AND r.status = 'submitted'
            WHERE r.task_id = :tid
            GROUP BY u.id, u.username, u.real_name
            ORDER BY u.username
        """, {'tid': task_id})

        return [
            {
                'student_id': row[0],
                'username': row[1],
                'real_name': row[2] or row[1],
                'submitted_count': row[3],
                'total_cases': row[4],
            }
            for row in cursor.fetchall()
        ]
