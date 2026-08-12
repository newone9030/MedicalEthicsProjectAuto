"""
反馈任务管理服务：反馈任务 CRUD（含 page_category）、题目 CRUD、
选项 CRUD、映射 CRUD、获取所有调查题
"""

from app.db import get_connection


# ==================== 反馈任务 CRUD ====================

def create_feedback_task(title: str, description: str = None,
                         page_category: str = 'case') -> dict:
    """创建反馈任务，返回 {'success': True/False, 'task_id': int, 'message': str}"""
    valid_categories = ('case', 'task_burden', 'course_impact', 'open_feedback')
    if page_category not in valid_categories:
        return {'success': False, 'message': f'无效的页面分类: {page_category}'}

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO feedback_tasks (title, description, page_category)
            VALUES (:title, :desc, :cat)
        """, {'title': title, 'desc': description, 'cat': page_category})
        conn.commit()
        task_id = cursor.lastrowid
        return {'success': True, 'message': '反馈任务创建成功', 'task_id': task_id}


def update_feedback_task(task_id: int, title: str = None,
                         description: str = None, page_category: str = None) -> dict:
    """更新反馈任务"""
    with get_connection() as conn:
        cursor = conn.cursor()
        # 检查任务存在
        cursor.execute("SELECT id FROM feedback_tasks WHERE id = :tid", {'tid': task_id})
        if not cursor.fetchone():
            return {'success': False, 'message': '反馈任务不存在'}

        set_parts = []
        params = {'tid': task_id}
        if title is not None:
            set_parts.append("title = :title")
            params['title'] = title
        if description is not None:
            set_parts.append("description = :desc")
            params['desc'] = description
        if page_category is not None:
            valid_categories = ('case', 'task_burden', 'course_impact', 'open_feedback')
            if page_category not in valid_categories:
                return {'success': False, 'message': f'无效的页面分类: {page_category}'}
            set_parts.append("page_category = :cat")
            params['cat'] = page_category

        if set_parts:
            cursor.execute(f"UPDATE feedback_tasks SET {', '.join(set_parts)} WHERE id = :tid", params)
            conn.commit()

        return {'success': True, 'message': '反馈任务已更新'}


def delete_feedback_task(task_id: int) -> dict:
    """删除反馈任务（级联删除关联题目、选项、映射、作答）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM feedback_tasks WHERE id = :tid", {'tid': task_id})
        if not cursor.fetchone():
            return {'success': False, 'message': '反馈任务不存在'}

        # 先删除关联的作答记录
        cursor.execute("""
            DELETE FROM feedback_responses WHERE feedback_question_id IN
            (SELECT id FROM feedback_questions WHERE task_id = :tid)
        """, {'tid': task_id})
        # 删除关联的选项记录
        cursor.execute("""
            DELETE FROM feedback_question_options WHERE question_id IN
            (SELECT id FROM feedback_questions WHERE task_id = :tid)
        """, {'tid': task_id})
        # 删除关联的题目
        cursor.execute("DELETE FROM feedback_questions WHERE task_id = :tid", {'tid': task_id})
        # 删除关联的映射
        cursor.execute("DELETE FROM feedback_task_mappings WHERE task_id = :tid", {'tid': task_id})
        # 删除任务
        cursor.execute("DELETE FROM feedback_tasks WHERE id = :tid", {'tid': task_id})
        conn.commit()
        return {'success': True, 'message': '反馈任务已删除'}


def get_feedback_task_list(page_category: str = None) -> list:
    """获取反馈任务列表，可按 page_category 筛选"""
    with get_connection() as conn:
        cursor = conn.cursor()
        if page_category:
            cursor.execute("""
                SELECT ft.id, ft.title, ft.description, ft.page_category, ft.created_at,
                       (SELECT COUNT(*) FROM feedback_questions WHERE task_id = ft.id) AS question_count
                FROM feedback_tasks ft
                WHERE ft.page_category = :cat
                ORDER BY ft.created_at DESC
            """, {'cat': page_category})
        else:
            cursor.execute("""
                SELECT ft.id, ft.title, ft.description, ft.page_category, ft.created_at,
                       (SELECT COUNT(*) FROM feedback_questions WHERE task_id = ft.id) AS question_count
                FROM feedback_tasks ft
                ORDER BY ft.page_category, ft.created_at DESC
            """)
        rows = cursor.fetchall()
        return [
            {
                'id': row[0],
                'title': row[1],
                'description': row[2] or '',
                'page_category': row[3],
                'created_at': str(row[4]) if row[4] else '',
                'question_count': row[5],
            }
            for row in rows
        ]


def get_feedback_task_detail(task_id: int) -> dict:
    """获取反馈任务详情（含题目和选项）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, description, page_category, created_at
            FROM feedback_tasks WHERE id = :tid
        """, {'tid': task_id})
        task_row = cursor.fetchone()
        if not task_row:
            return {'success': False, 'message': '反馈任务不存在'}

        # 获取题目
        cursor.execute("""
            SELECT id, question_text, question_type, sort_order, required
            FROM feedback_questions WHERE task_id = :tid
            ORDER BY sort_order, id
        """, {'tid': task_id})
        questions = []
        for q in cursor.fetchall():
            q_dict = {
                'id': q[0],
                'question_text': q[1],
                'question_type': q[2],
                'sort_order': q[3],
                'required': bool(q[4]),
                'options': [],
            }
            # 仅单选题目获取选项
            if q[2] == 'radio':
                cursor.execute("""
                    SELECT id, label, value, sort_order, requires_comment, comment_hint
                    FROM feedback_question_options WHERE question_id = :qid
                    ORDER BY sort_order, id
                """, {'qid': q[0]})
                q_dict['options'] = [
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
            questions.append(q_dict)

        # 获取关联映射（仅 case 类有意义）
        cursor.execute("""
            SELECT id, survey_question_id FROM feedback_task_mappings WHERE task_id = :tid
        """, {'tid': task_id})
        mappings = [{'id': m[0], 'survey_question_id': m[1]} for m in cursor.fetchall()]

        return {
            'success': True,
            'task': {
                'id': task_row[0],
                'title': task_row[1],
                'description': task_row[2] or '',
                'page_category': task_row[3],
                'created_at': str(task_row[4]) if task_row[4] else '',
                'questions': questions,
                'mappings': mappings,
            }
        }


# ==================== 反馈题目 CRUD ====================

def add_feedback_question(task_id: int, question_text: str,
                          question_type: str = 'radio',
                          required: int = 0) -> dict:
    """添加反馈题目（required 仅对开放题生效）"""
    if question_type not in ('radio', 'open'):
        return {'success': False, 'message': '题目类型无效，仅支持 radio 或 open'}

    with get_connection() as conn:
        cursor = conn.cursor()
        # 检查任务存在
        cursor.execute("SELECT id FROM feedback_tasks WHERE id = :tid", {'tid': task_id})
        if not cursor.fetchone():
            return {'success': False, 'message': '反馈任务不存在'}

        # 获取下一个 sort_order
        cursor.execute("""
            SELECT COALESCE(MAX(sort_order), -1) FROM feedback_questions WHERE task_id = :tid
        """, {'tid': task_id})
        max_order = cursor.fetchone()[0]
        next_order = max_order + 1

        cursor.execute("""
            INSERT INTO feedback_questions (task_id, question_text, question_type, sort_order, required)
            VALUES (:tid, :qtext, :qtype, :sorder, :req)
        """, {'tid': task_id, 'qtext': question_text, 'qtype': question_type,
              'sorder': next_order, 'req': 1 if required else 0})
        conn.commit()
        return {'success': True, 'message': '题目添加成功', 'question_id': cursor.lastrowid}


def update_feedback_question(question_id: int, question_text: str = None,
                             question_type: str = None,
                             required: int = None) -> dict:
    """更新反馈题目（required 仅对开放题生效）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM feedback_questions WHERE id = :qid", {'qid': question_id})
        if not cursor.fetchone():
            return {'success': False, 'message': '题目不存在'}

        set_parts = []
        params = {'qid': question_id}
        if question_text is not None:
            set_parts.append("question_text = :qtext")
            params['qtext'] = question_text
        if question_type is not None:
            if question_type not in ('radio', 'open'):
                return {'success': False, 'message': '题目类型无效，仅支持 radio 或 open'}
            set_parts.append("question_type = :qtype")
            params['qtype'] = question_type
        if required is not None:
            set_parts.append("required = :req")
            params['req'] = 1 if required else 0

        if set_parts:
            cursor.execute(f"UPDATE feedback_questions SET {', '.join(set_parts)} WHERE id = :qid", params)
            conn.commit()

        return {'success': True, 'message': '题目已更新'}


def delete_feedback_question(question_id: int) -> dict:
    """删除反馈题目（级联删除选项和作答）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM feedback_questions WHERE id = :qid", {'qid': question_id})
        if not cursor.fetchone():
            return {'success': False, 'message': '题目不存在'}

        # 删除关联作答和选项
        cursor.execute("DELETE FROM feedback_responses WHERE feedback_question_id = :qid", {'qid': question_id})
        cursor.execute("DELETE FROM feedback_question_options WHERE question_id = :qid", {'qid': question_id})
        cursor.execute("DELETE FROM feedback_questions WHERE id = :qid", {'qid': question_id})
        conn.commit()
        return {'success': True, 'message': '题目已删除'}


# ==================== 选项 CRUD ====================

def add_feedback_option(question_id: int, label: str, value: int,
                        sort_order: int = None, requires_comment: int = 0,
                        comment_hint: str = None) -> dict:
    """添加单选题选项"""
    with get_connection() as conn:
        cursor = conn.cursor()
        # 检查题目存在且为单选类型
        cursor.execute("SELECT id, question_type FROM feedback_questions WHERE id = :qid", {'qid': question_id})
        q_row = cursor.fetchone()
        if not q_row:
            return {'success': False, 'message': '题目不存在'}
        if q_row[1] != 'radio':
            return {'success': False, 'message': '仅单选题可添加选项'}

        if sort_order is None:
            cursor.execute("""
                SELECT COALESCE(MAX(sort_order), -1) FROM feedback_question_options
                WHERE question_id = :qid
            """, {'qid': question_id})
            sort_order = cursor.fetchone()[0] + 1

        cursor.execute("""
            INSERT INTO feedback_question_options (question_id, label, value, sort_order, requires_comment, comment_hint)
            VALUES (:qid, :label, :val, :sorder, :rcom, :chint)
        """, {'qid': question_id, 'label': label, 'val': value,
              'sorder': sort_order, 'rcom': requires_comment,
              'chint': comment_hint or None})
        conn.commit()
        return {'success': True, 'message': '选项添加成功', 'option_id': cursor.lastrowid}


def update_feedback_option(option_id: int, label: str = None,
                           value: int = None, requires_comment: int = None,
                           comment_hint: str = None) -> dict:
    """更新选项（comment_hint 传空字符串可清空提示文字）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM feedback_question_options WHERE id = :oid", {'oid': option_id})
        if not cursor.fetchone():
            return {'success': False, 'message': '选项不存在'}

        set_parts = []
        params = {'oid': option_id}
        if label is not None:
            set_parts.append("label = :label")
            params['label'] = label
        if value is not None:
            set_parts.append("value = :val")
            params['val'] = value
        if requires_comment is not None:
            set_parts.append("requires_comment = :rcom")
            params['rcom'] = requires_comment
        if comment_hint is not None:
            set_parts.append("comment_hint = :chint")
            params['chint'] = comment_hint or None

        if set_parts:
            cursor.execute(f"UPDATE feedback_question_options SET {', '.join(set_parts)} WHERE id = :oid", params)
            conn.commit()

        return {'success': True, 'message': '选项已更新'}


def delete_feedback_option(option_id: int) -> dict:
    """删除选项"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM feedback_question_options WHERE id = :oid", {'oid': option_id})
        if not cursor.fetchone():
            return {'success': False, 'message': '选项不存在'}

        cursor.execute("DELETE FROM feedback_question_options WHERE id = :oid", {'oid': option_id})
        conn.commit()
        return {'success': True, 'message': '选项已删除'}


# ==================== 映射 CRUD ====================

def get_feedback_task_mappings(task_id: int) -> list:
    """获取反馈任务的关联调查题映射"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ftm.id, ftm.survey_question_id, cq.question_text, c.title AS case_title
            FROM feedback_task_mappings ftm
            JOIN case_questions cq ON ftm.survey_question_id = cq.id
            JOIN cases c ON cq.case_id = c.id
            WHERE ftm.task_id = :tid
            ORDER BY cq.id
        """, {'tid': task_id})
        rows = cursor.fetchall()
        return [
            {
                'id': row[0],
                'survey_question_id': row[1],
                'question_text': row[2],
                'case_title': row[3],
            }
            for row in rows
        ]


def add_feedback_task_mapping(task_id: int, survey_question_id: int) -> dict:
    """添加反馈任务→调查题关联（仅 case 类任务）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        # 检查映射是否已存在
        cursor.execute("""
            SELECT id FROM feedback_task_mappings
            WHERE task_id = :tid AND survey_question_id = :sqid
        """, {'tid': task_id, 'sqid': survey_question_id})
        if cursor.fetchone():
            return {'success': False, 'message': '该关联已存在'}

        cursor.execute("""
            INSERT INTO feedback_task_mappings (task_id, survey_question_id)
            VALUES (:tid, :sqid)
        """, {'tid': task_id, 'sqid': survey_question_id})
        conn.commit()
        return {'success': True, 'message': '关联已添加', 'mapping_id': cursor.lastrowid}


def remove_feedback_task_mapping(task_id: int, survey_question_id: int) -> dict:
    """移除反馈任务→调查题关联"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM feedback_task_mappings
            WHERE task_id = :tid AND survey_question_id = :sqid
        """, {'tid': task_id, 'sqid': survey_question_id})
        conn.commit()
        return {'success': True, 'message': '关联已移除'}


# ==================== 辅助查询 ====================

def get_all_survey_questions() -> list:
    """获取所有调查题（case_questions），含所属案例标题"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT cq.id, cq.question_text, cq.question_type, cq.sort_order,
                   c.id AS case_id, c.title AS case_title
            FROM case_questions cq
            JOIN cases c ON cq.case_id = c.id
            ORDER BY c.id, cq.sort_order
        """)
        rows = cursor.fetchall()
        return [
            {
                'id': row[0],
                'question_text': row[1],
                'question_type': row[2],
                'sort_order': row[3],
                'case_id': row[4],
                'case_title': row[5],
            }
            for row in rows
        ]
