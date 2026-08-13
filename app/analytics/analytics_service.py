"""
数据分析服务：频次统计、多选题交叉分析
"""

import json
from app.db import get_connection
from app.case.question_service import normalize_options


def get_task_statistics(task_id: int) -> dict:
    """获取任务整体统计"""
    with get_connection() as conn:
        cursor = conn.cursor()

        # 总案例数
        cursor.execute("SELECT COUNT(*) FROM task_cases WHERE task_id = :tid", {'tid': task_id})
        total_cases = cursor.fetchone()[0]

        # 参与学生数
        cursor.execute("""
            SELECT COUNT(DISTINCT student_id) FROM responses
            WHERE task_id = :tid AND status = 'submitted'
        """, {'tid': task_id})
        total_students = cursor.fetchone()[0]

        # 总提交数
        cursor.execute("""
            SELECT COUNT(*) FROM responses
            WHERE task_id = :tid AND status = 'submitted'
        """, {'tid': task_id})
        total_submissions = cursor.fetchone()[0]

        # 每个案例的提交统计
        cursor.execute("""
            SELECT tc.case_id, c.title,
                   COUNT(CASE WHEN r.status = 'submitted' THEN 1 END) as submitted_count
            FROM task_cases tc
            JOIN cases c ON tc.case_id = c.id
            LEFT JOIN responses r ON tc.task_id = r.task_id AND tc.case_id = r.case_id
            WHERE tc.task_id = :tid
            GROUP BY tc.case_id, c.title, tc.sort_order
            ORDER BY tc.sort_order
        """, {'tid': task_id})

        per_case = []
        for row in cursor.fetchall():
            per_case.append({
                'case_id': row[0],
                'title': row[1],
                'submitted': row[2] or 0,
            })

        return {
            'total_cases': total_cases,
            'total_students': total_students,
            'total_submissions': total_submissions,
            'per_case': per_case,
        }


def get_question_analysis(task_id: int) -> list:
    """获取每个题目的统计数据"""
    with get_connection() as conn:
        cursor = conn.cursor()

        # 获取任务的所有题目
        cursor.execute("""
            SELECT q.id, q.case_id, q.question_text, q.question_type, q.options,
                   c.title as case_title
            FROM case_questions q
            JOIN task_cases tc ON q.case_id = tc.case_id
            JOIN cases c ON q.case_id = c.id
            WHERE tc.task_id = :tid
            ORDER BY tc.sort_order, q.sort_order
        """, {'tid': task_id})

        results = []
        for q_row in cursor.fetchall():
            q_id = q_row[0]
            q_type = q_row[3]
            options_str = q_row[4]
            raw_options = json.loads(options_str) if options_str else []
            options = normalize_options(raw_options)
            option_labels = [o['label'] for o in options]

            analysis = {
                'question_id': q_id,
                'case_title': q_row[5],
                'question_text': q_row[2],
                'question_type': q_type,
                'options': options,
            }

            # 获取所有提交的答案
            cursor.execute("""
                SELECT rd.answer FROM response_details rd
                JOIN responses r ON rd.response_id = r.id
                WHERE rd.question_id = :qid AND r.task_id = :tid AND r.status = 'submitted'
            """, {'qid': q_id, 'tid': task_id})
            answers = cursor.fetchall()

            total_responses = len(answers)

            if q_type in ('single_choice', 'multiple_choice'):
                # 频次统计
                freq = {}
                for label in option_labels:
                    freq[label] = 0

                for ans_row in answers:
                    ans = ans_row[0]
                    if q_type == 'single_choice':
                        # 兼容旧字符串答案 / 新 dict 答案
                        if isinstance(ans, str):
                            try:
                                parsed = json.loads(ans)
                            except (json.JSONDecodeError, TypeError):
                                parsed = ans
                            if isinstance(parsed, dict):
                                ans = parsed.get('option')
                            else:
                                ans = parsed
                        elif isinstance(ans, dict):
                            ans = ans.get('option')
                        if ans in freq:
                            freq[ans] += 1
                    else:  # multiple_choice
                        # 兼容旧 list 答案 / 新 dict 答案 {'options': [...], 'open_text': '...'}
                        if isinstance(ans, str):
                            try:
                                selected = json.loads(ans) if ans else []
                            except (json.JSONDecodeError, TypeError):
                                selected = []
                        elif isinstance(ans, dict):
                            selected = ans.get('options', []) if isinstance(ans.get('options'), list) else []
                        elif isinstance(ans, list):
                            selected = ans
                        else:
                            selected = []
                        if isinstance(selected, dict):
                            selected = selected.get('options', []) if isinstance(selected.get('options'), list) else []
                        if not isinstance(selected, list):
                            selected = []
                        for s in selected:
                            if s in freq:
                                freq[s] += 1

                analysis['frequency'] = freq
                analysis['total_responses'] = total_responses

            elif q_type == 'open':
                # 开放题 - 收集所有文本回答
                text_answers = [a[0] for a in answers if a[0]]
                analysis['total_responses'] = total_responses
                analysis['text_answers'] = text_answers[:20]  # 最多展示20条
                analysis['has_more'] = len(text_answers) > 20

            results.append(analysis)

        return results


def get_student_list() -> list:
    """获取所有学生列表"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, username, real_name, class_name
            FROM users WHERE role = 'student' AND status = 'active'
            ORDER BY class_name, username
        """)
        return [{'id': r[0], 'username': r[1], 'real_name': r[2], 'class_name': r[3]} for r in cursor.fetchall()]


def get_student_count() -> int:
    """获取学生总数"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'student' AND status = 'active'")
        return cursor.fetchone()[0]
