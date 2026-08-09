"""
案例服务：案例 CRUD 操作
"""

from app.db import get_connection


def create_case(title: str, body: str, theme: str, created_by: int) -> dict:
    """创建案例"""
    if not title:
        return {'success': False, 'message': '案例标题不能为空'}

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO cases (title, body, theme, created_by)
            VALUES (:title, :body, :theme, :created_by)
        """, {'title': title, 'body': body, 'theme': theme, 'created_by': created_by})
        conn.commit()
        case_id = cursor.lastrowid

        return {'success': True, 'message': '案例保存成功！', 'case_id': case_id}


def update_case(case_id: int, title: str, body: str, theme: str) -> dict:
    """更新案例"""
    if not title:
        return {'success': False, 'message': '案例标题不能为空'}

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE cases SET title = :title, body = :body, theme = :theme, updated_at = CURRENT_TIMESTAMP
            WHERE id = :cid
        """, {'title': title, 'body': body, 'theme': theme, 'cid': case_id})

        if cursor.rowcount == 0:
            return {'success': False, 'message': '案例不存在'}

        conn.commit()
        return {'success': True, 'message': '案例更新成功！'}


def delete_case(case_id: int) -> dict:
    """删除案例"""
    with get_connection() as conn:
        cursor = conn.cursor()
        # 检查是否被任务引用
        cursor.execute("SELECT COUNT(*) FROM task_cases WHERE case_id = :cid", {'cid': case_id})
        task_count = cursor.fetchone()[0]
        if task_count > 0:
            return {'success': False, 'message': f'该案例被 {task_count} 个任务引用，无法删除。请先解除关联'}

        # 检查是否有作答记录
        cursor.execute("SELECT COUNT(*) FROM responses WHERE case_id = :cid", {'cid': case_id})
        resp_count = cursor.fetchone()[0]
        if resp_count > 0:
            return {'success': False, 'message': f'该案例有 {resp_count} 条学生作答记录，无法删除。请先清除作答记录'}

        # 先删除关联题目（手动处理 ON DELETE CASCADE）
        cursor.execute("DELETE FROM case_questions WHERE case_id = :cid", {'cid': case_id})
        # 删除案例本身
        cursor.execute("DELETE FROM cases WHERE id = :cid", {'cid': case_id})
        conn.commit()

        return {'success': True, 'message': '案例已删除'}


def get_case(case_id: int) -> dict:
    """获取单个案例（含题目列表）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, body, theme, created_by, created_at, updated_at
            FROM cases WHERE id = :cid
        """, {'cid': case_id})
        row = cursor.fetchone()
        if not row:
            return None

        case = {
            'id': row[0],
            'title': row[1],
            'body': row[2],
            'theme': row[3],
            'created_by': row[4],
            'created_at': row[5],
            'updated_at': row[6],
            'questions': []
        }

        # 获取关联题目
        from app.case.question_service import get_questions_by_case
        case['questions'] = get_questions_by_case(case_id)

        return case


def list_cases(search: str = '', theme: str = '') -> list:
    """获取案例列表，支持搜索和按主题筛选"""
    with get_connection() as conn:
        cursor = conn.cursor()

        sql = "SELECT id, title, theme, created_at, updated_at FROM cases WHERE 1=1"
        params = {}

        if search:
            sql += " AND (title LIKE :search OR body LIKE :search2)"
            params['search'] = f'%{search}%'
            params['search2'] = f'%{search}%'

        if theme:
            sql += " AND theme = :theme"
            params['theme'] = theme

        sql += " ORDER BY updated_at DESC"

        cursor.execute(sql, params)
        rows = cursor.fetchall()

        return [
            {
                'id': row[0],
                'title': row[1],
                'theme': row[2],
                'created_at': row[3],
                'updated_at': row[4],
            }
            for row in rows
        ]


def get_case_count() -> int:
    """获取案例总数"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM cases")
        return cursor.fetchone()[0]
