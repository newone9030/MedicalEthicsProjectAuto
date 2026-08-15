"""
学生反馈服务
"""

from app.db import get_connection


def get_student_answered_questions(student_id: int, task_id: int) -> list:
    """
    获取学生在指定任务中已提交的作答题目（含案例信息）
    返回 [{survey_question_id, question_text, question_type, case_id, case_title}, ...]
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT cq.id, cq.question_text, cq.question_type, cq.case_id, c.title
            FROM responses r
            JOIN response_details rd ON rd.response_id = r.id
            JOIN case_questions cq ON rd.question_id = cq.id
            JOIN cases c ON cq.case_id = c.id
            WHERE r.student_id = :sid AND r.task_id = :tid AND r.status = 'submitted'
            ORDER BY cq.case_id, cq.sort_order
        """, {'sid': student_id, 'tid': task_id})
        rows = cursor.fetchall()
        return [
            {
                'survey_question_id': row[0],
                'question_text': row[1],
                'question_type': row[2],
                'case_id': row[3],
                'case_title': row[4],
            }
            for row in rows
        ]


def get_feedback_tasks_for_question(survey_question_id: int) -> list:
    """
    获取关联到指定调查题的 case 类反馈任务（含题目和选项）
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        # 先找映射
        cursor.execute("""
            SELECT ft.id, ft.title, ft.description
            FROM feedback_task_mappings ftm
            JOIN feedback_tasks ft ON ftm.task_id = ft.id
            WHERE ftm.survey_question_id = :sqid AND ft.page_category = 'case'
        """, {'sqid': survey_question_id})
        tasks = []
        for t_row in cursor.fetchall():
            task = {
                'id': t_row[0],
                'title': t_row[1],
                'description': t_row[2] or '',
                'questions': [],
            }
            # 获取该任务下的题目
            cursor.execute("""
                SELECT id, question_text, question_type, sort_order, required
                FROM feedback_questions
                WHERE task_id = :tid
                ORDER BY sort_order, id
            """, {'tid': t_row[0]})
            for q_row in cursor.fetchall():
                q = {
                    'id': q_row[0],
                    'question_text': q_row[1],
                    'question_type': q_row[2],
                    'sort_order': q_row[3],
                    'required': bool(q_row[4]),
                    'options': [],
                }
                if q['question_type'] == 'radio':
                    cursor.execute("""
                        SELECT id, label, value, sort_order, requires_comment, comment_hint
                        FROM feedback_question_options
                        WHERE question_id = :qid
                        ORDER BY sort_order, id
                    """, {'qid': q['id']})
                    q['options'] = [
                        {
                            'id': o[0],
                            'label': o[1],
                            'value': o[2],
                            'sort_order': o[3],
                            'requires_comment': bool(o[4]),
                            'comment_hint': o[5] or '',
                        }
                        for o in cursor.fetchall()
                    ]
                task['questions'].append(q)
            tasks.append(task)
        return tasks


def get_feedback_tasks_by_category(page_category: str) -> list:
    """
    按 page_category 获取所有反馈任务（含题目和选项）
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, description
            FROM feedback_tasks
            WHERE page_category = :cat
            ORDER BY created_at DESC
        """, {'cat': page_category})
        tasks = []
        for t_row in cursor.fetchall():
            task = {
                'id': t_row[0],
                'title': t_row[1],
                'description': t_row[2] or '',
                'questions': [],
            }
            cursor.execute("""
                SELECT id, question_text, question_type, sort_order, required
                FROM feedback_questions
                WHERE task_id = :tid
                ORDER BY sort_order, id
            """, {'tid': t_row[0]})
            for q_row in cursor.fetchall():
                q = {
                    'id': q_row[0],
                    'question_text': q_row[1],
                    'question_type': q_row[2],
                    'sort_order': q_row[3],
                    'required': bool(q_row[4]),
                    'options': [],
                }
                if q['question_type'] == 'radio':
                    cursor.execute("""
                        SELECT id, label, value, sort_order, requires_comment, comment_hint
                        FROM feedback_question_options
                        WHERE question_id = :qid
                        ORDER BY sort_order, id
                    """, {'qid': q['id']})
                    q['options'] = [
                        {
                            'id': o[0],
                            'label': o[1],
                            'value': o[2],
                            'sort_order': o[3],
                            'requires_comment': bool(o[4]),
                            'comment_hint': o[5] or '',
                        }
                        for o in cursor.fetchall()
                    ]
                task['questions'].append(q)
            tasks.append(task)
        return tasks


def submit_feedbacks(student_id: int, feedbacks: list) -> dict:
    """
    批量写入反馈作答
    feedbacks: [{'survey_question_id': int, 'feedback_question_id': int,
                 'selected_option_id': int, 'comment_text': str}, ...]
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        # 先删除学生已有的所有反馈记录
        cursor.execute("DELETE FROM feedback_responses WHERE student_id = :sid",
                       {'sid': student_id})

        for fb in feedbacks:
            cursor.execute("""
                INSERT INTO feedback_responses
                    (student_id, survey_question_id, feedback_question_id, selected_option_id, comment_text)
                VALUES (:sid, :sqid, :fqid, :oid, :com)
            """, {
                'sid': student_id,
                'sqid': fb.get('survey_question_id'),
                'fqid': fb['feedback_question_id'],
                'oid': fb.get('selected_option_id'),
                'com': fb.get('comment_text'),
            })
        conn.commit()
        return {'success': True, 'message': '反馈已提交'}


def get_feedback_submitters() -> list:
    """
    获取所有提交过反馈的学生（作答者）列表
    返回 [{'student_id', 'username', 'real_name', 'class_name',
           'answer_count', 'first_submitted_at', 'last_submitted_at'}, ...]
    按最近提交时间倒序排列
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.username, u.real_name, u.class_name,
                   COUNT(fr.id),
                   MIN(fr.created_at),
                   MAX(fr.created_at)
            FROM feedback_responses fr
            JOIN users u ON fr.student_id = u.id
            GROUP BY u.id, u.username, u.real_name, u.class_name
            ORDER BY MAX(fr.created_at) DESC
        """)
        rows = cursor.fetchall()
        return [
            {
                'student_id': r[0],
                'username': r[1],
                'real_name': r[2],
                'class_name': r[3],
                'answer_count': r[4],
                'first_submitted_at': r[5],
                'last_submitted_at': r[6],
            }
            for r in rows
        ]


def has_feedback(student_id: int) -> bool:
    """检查学生是否已提交反馈"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM feedback_responses WHERE student_id = :sid",
            {'sid': student_id}
        )
        return cursor.fetchone()[0] > 0


def delete_student_feedback(student_id: int) -> bool:
    """删除学生已提交的全部反馈记录（删除后可重新填写）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM feedback_responses WHERE student_id = :sid",
            {'sid': student_id}
        )
        conn.commit()
        return cursor.rowcount > 0


def get_student_feedback(student_id: int) -> list:
    """
    获取学生已提交的反馈内容（按案例/类别分组连续排列）
    返回 [{'page_category', 'group_title', 'question_text', 'answer_text'}]
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT fr.survey_question_id, fr.selected_option_id, fr.comment_text,
                   fq.question_text, fq.question_type,
                   ft.title, ft.page_category
            FROM feedback_responses fr
            JOIN feedback_questions fq ON fr.feedback_question_id = fq.id
            JOIN feedback_tasks ft ON fq.task_id = ft.id
            WHERE fr.student_id = :sid
            ORDER BY fq.task_id, fq.sort_order, fq.id
        """, {'sid': student_id})
        rows = cursor.fetchall()
        if not rows:
            return []

        # 缓存选项 label 与案例标题，避免循环内反复查询
        opt_labels = {}
        case_titles = {}

        items = []
        for sqid, opt_id, comment_text, q_text, q_type, task_title, category in rows:
            # 分组标题：案例反馈按案例标题，其他按任务标题
            if category == 'case':
                if sqid and sqid not in case_titles:
                    cursor.execute("""
                        SELECT c.title FROM case_questions cq
                        JOIN cases c ON cq.case_id = c.id
                        WHERE cq.id = :sqid
                    """, {'sqid': sqid})
                    row = cursor.fetchone()
                    case_titles[sqid] = row[0] if row else None
                group_title = case_titles.get(sqid) or task_title or '案例反馈'
            else:
                group_title = task_title or category

            # 答案文本
            answer_text = ''
            if q_type == 'radio':
                if opt_id:
                    if opt_id not in opt_labels:
                        cursor.execute(
                            "SELECT label FROM feedback_question_options WHERE id = :oid",
                            {'oid': opt_id})
                        row = cursor.fetchone()
                        opt_labels[opt_id] = row[0] if row else ''
                    answer_text = opt_labels[opt_id]
                if comment_text:
                    answer_text = f'{answer_text}\n补充说明：{comment_text}'.strip()
            else:
                answer_text = comment_text or ''

            items.append({
                'page_category': category,
                'group_title': group_title,
                'question_text': q_text,
                'answer_text': answer_text,
            })

        # 按类别顺序 + 分组标题排序，保证同组连续
        category_order = {'case': 0, 'task_burden': 1, 'course_impact': 2, 'open_feedback': 3}
        items.sort(key=lambda x: (category_order.get(x['page_category'], 9), x['group_title']))
        return items
