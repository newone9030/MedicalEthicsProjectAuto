"""
任务服务：任务 CRUD、案例关联、时间窗口校验、状态流转
"""

from datetime import datetime
from app.db import get_connection


def create_task(name: str, description: str, start_time: datetime, end_time: datetime,
                case_ids: list, created_by: int, task_type: str = 'survey') -> dict:
    """创建任务"""
    if not name:
        return {'success': False, 'message': '任务名称不能为空'}
    if not case_ids:
        return {'success': False, 'message': '请至少选择一个案例'}
    if start_time >= end_time:
        return {'success': False, 'message': '开始时间必须早于结束时间'}

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO tasks (name, description, start_time, end_time, status, task_type, created_by)
            VALUES (:name, :desc, :stime, :etime, 'draft', :ttype, :cby)
        """, {
            'name': name, 'desc': description,
            'stime': start_time, 'etime': end_time, 'ttype': task_type, 'cby': created_by
        })

        task_id = cursor.lastrowid

        # 关联案例
        for i, case_id in enumerate(case_ids):
            cursor.execute("""
                INSERT INTO task_cases (task_id, case_id, sort_order)
                VALUES (:tid, :cid, :sorder)
            """, {'tid': task_id, 'cid': case_id, 'sorder': i})

        conn.commit()
        return {'success': True, 'message': '任务创建成功', 'task_id': task_id}


def update_task(task_id: int, name: str, description: str, start_time: datetime,
                end_time: datetime, case_ids: list) -> dict:
    """更新任务（仅草稿状态可编辑）"""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT status FROM tasks WHERE id = :tid", {'tid': task_id})
        row = cursor.fetchone()
        if not row:
            return {'success': False, 'message': '任务不存在'}
        if row[0] != 'draft':
            return {'success': False, 'message': '仅草稿状态的任务可编辑'}

        cursor.execute("""
            UPDATE tasks SET name = :name, description = :desc,
            start_time = :stime, end_time = :etime
            WHERE id = :tid
        """, {
            'name': name, 'desc': description,
            'stime': start_time, 'etime': end_time, 'tid': task_id
        })

        # 重建案例关联
        cursor.execute("DELETE FROM task_cases WHERE task_id = :tid", {'tid': task_id})
        for i, case_id in enumerate(case_ids):
            cursor.execute("""
                INSERT INTO task_cases (task_id, case_id, sort_order)
                VALUES (:tid, :cid, :sorder)
            """, {'tid': task_id, 'cid': case_id, 'sorder': i})

        conn.commit()
        return {'success': True, 'message': '任务更新成功'}


def delete_task(task_id: int) -> dict:
    """删除任务（需先清空作答记录）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM tasks WHERE id = :tid", {'tid': task_id})
        row = cursor.fetchone()
        if not row:
            return {'success': False, 'message': '任务不存在'}
        if row[0] not in ('draft', 'closed'):
            return {'success': False, 'message': '仅草稿或已关闭的任务可删除'}

        # 检查是否存在作答记录
        cursor.execute("SELECT COUNT(*) FROM responses WHERE task_id = :tid", {'tid': task_id})
        if cursor.fetchone()[0] > 0:
            return {'success': False, 'message': '该任务存在学生作答记录，请先在学生端删除作答后再删除任务'}

        # 删任务-案例关联
        cursor.execute("DELETE FROM task_cases WHERE task_id = :tid", {'tid': task_id})
        # 删任务
        cursor.execute("DELETE FROM tasks WHERE id = :tid", {'tid': task_id})
        conn.commit()
        return {'success': True, 'message': '任务已删除'}


def publish_task(task_id: int) -> dict:
    """发布任务（draft → published/active）"""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT status, start_time, end_time FROM tasks WHERE id = :tid",
            {'tid': task_id}
        )
        row = cursor.fetchone()
        if not row:
            return {'success': False, 'message': '任务不存在'}
        if row[0] != 'draft':
            return {'success': False, 'message': '仅草稿状态可发布'}

        cursor.execute(
            "UPDATE tasks SET status = 'active' WHERE id = :tid",
            {'tid': task_id}
        )
        conn.commit()
        return {'success': True, 'message': '任务已发布'}


def close_task(task_id: int) -> dict:
    """关闭任务（published/active → closed）"""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT status FROM tasks WHERE id = :tid", {'tid': task_id})
        row = cursor.fetchone()
        if not row:
            return {'success': False, 'message': '任务不存在'}
        if row[0] not in ('active',):
            return {'success': False, 'message': '仅已发布或进行中的任务可关闭'}

        cursor.execute(
            "UPDATE tasks SET status = 'closed' WHERE id = :tid",
            {'tid': task_id}
        )
        conn.commit()
        return {'success': True, 'message': '任务已关闭'}


def auto_update_task_statuses():
    """自动更新任务状态（定时调用）"""
    now = datetime.now()
    with get_connection() as conn:
        cursor = conn.cursor()
        # 到期的进行中任务 → closed
        cursor.execute("""
            UPDATE tasks SET status = 'closed'
            WHERE status = 'active' AND end_time < :now
        """, {'now': now})
        # 到开始时间的已发布任务 → active
        cursor.execute("""
            UPDATE tasks SET status = 'active'
            WHERE status = 'published' AND start_time <= :now AND end_time >= :now2
        """, {'now': now, 'now2': now})
        conn.commit()


def get_task(task_id: int) -> dict:
    """获取单个任务（含关联案例和状态）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, description, start_time, end_time, status, COALESCE(task_type, 'survey'), created_by, created_at
            FROM tasks WHERE id = :tid
        """, {'tid': task_id})
        row = cursor.fetchone()
        if not row:
            return None

        task = {
            'id': row[0], 'name': row[1], 'description': row[2],
            'start_time': row[3], 'end_time': row[4], 'status': row[5],
            'task_type': row[6], 'created_by': row[7], 'created_at': row[8],
            'cases': []
        }

        # 获取关联案例
        cursor.execute("""
            SELECT c.id, c.title, c.theme, tc.sort_order
            FROM task_cases tc
            JOIN cases c ON tc.case_id = c.id
            WHERE tc.task_id = :tid
            ORDER BY tc.sort_order
        """, {'tid': task_id})

        for cr in cursor.fetchall():
            task['cases'].append({
                'id': cr[0], 'title': cr[1], 'theme': cr[2], 'sort_order': cr[3]
            })

        return task


def get_task_status_display(task: dict) -> str:
    """获取带自动更新的任务展示状态"""
    now = datetime.now()
    status = task['status']
    if status == 'draft':
        return 'draft'
    if status == 'closed' or task['end_time'] < now:
        return 'closed'
    if task['start_time'] <= now <= task['end_time']:
        return 'active'
    return 'published'


def list_tasks(status_filter: str = '', search: str = '', task_type: str = '') -> list:
    """获取任务列表"""
    auto_update_task_statuses()

    with get_connection() as conn:
        cursor = conn.cursor()

        sql = """
            SELECT t.id, t.name, t.description, t.start_time, t.end_time, t.status, t.created_at,
                   COALESCE(t.task_type, 'survey') as task_type,
                   (SELECT COUNT(*) FROM task_cases WHERE task_id = t.id) as case_count
            FROM tasks t WHERE 1=1
        """
        params = {}

        if status_filter:
            sql += " AND t.status = :status"
            params['status'] = status_filter

        if task_type:
            sql += " AND COALESCE(t.task_type, 'survey') = :ttype"
            params['ttype'] = task_type

        if search:
            sql += " AND (t.name LIKE :search OR t.description LIKE :search2)"
            params['search'] = f'%{search}%'
            params['search2'] = f'%{search}%'

        sql += " ORDER BY t.created_at DESC"

        cursor.execute(sql, params)
        tasks = []
        for row in cursor.fetchall():
            tasks.append({
                'id': row[0], 'name': row[1], 'description': row[2],
                'start_time': row[3], 'end_time': row[4], 'status': row[5],
                'created_at': row[6], 'task_type': row[7], 'case_count': row[8]
            })
        return tasks


def get_active_task_for_student(student_id: int) -> dict:
    """
    获取学生当前进行中任务（全局唯一）
    返回最先开始的那个进行中任务
    """
    auto_update_task_statuses()
    now = datetime.now()

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT t.id, t.name, t.description, t.start_time, t.end_time, t.status,
                   (SELECT COUNT(*) FROM task_cases WHERE task_id = t.id) as case_count
            FROM tasks t
            WHERE t.status = 'active'
              AND t.end_time >= :now
              AND COALESCE(t.task_type, 'survey') != 'background'
            ORDER BY t.start_time ASC
        """, {'now': now})

        row = cursor.fetchone()
        if not row:
            return None

        task = {
            'id': row[0], 'name': row[1], 'description': row[2],
            'start_time': row[3], 'end_time': row[4], 'status': row[5],
            'case_count': row[6], 'cases': []
        }

        # 获取关联案例及作答进度
        cursor.execute("""
            SELECT c.id, c.title, c.theme, tc.sort_order,
                   COALESCE((SELECT r.status FROM responses r
                        WHERE r.task_id = :tid AND r.case_id = c.id AND r.student_id = :sid),
                       'not_started') as response_status
            FROM task_cases tc
            JOIN cases c ON tc.case_id = c.id
            WHERE tc.task_id = :tid
            ORDER BY tc.sort_order
        """, {'tid': task['id'], 'sid': student_id})

        for cr in cursor.fetchall():
            task['cases'].append({
                'id': cr[0], 'title': cr[1], 'theme': cr[2],
                'sort_order': cr[3], 'response_status': cr[4]
            })

        return task


def get_task_count() -> int:
    """获取任务总数"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tasks")
        return cursor.fetchone()[0]


def get_active_task_count() -> int:
    """获取进行中任务数"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'active'")
        return cursor.fetchone()[0]


def get_background_task() -> dict:
    """获取背景资料问卷任务（全局唯一）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id FROM tasks
            WHERE COALESCE(task_type, 'survey') = 'background'
            ORDER BY id DESC LIMIT 1
        """)
        row = cursor.fetchone()
        if not row:
            return None
        return get_task(row[0])


def set_task_background(task_id: int, is_background: bool = True) -> dict:
    """将任务标记/取消为背景资料问卷"""
    with get_connection() as conn:
        cursor = conn.cursor()

        # 检查任务是否存在
        cursor.execute("SELECT id, name FROM tasks WHERE id = :tid", {'tid': task_id})
        trow = cursor.fetchone()
        if not trow:
            return {'success': False, 'message': '任务不存在'}

        if is_background:
            # 先取消所有现有的背景资料标记
            cursor.execute("UPDATE tasks SET task_type = 'survey' WHERE COALESCE(task_type, 'survey') = 'background'")
            cursor.execute("UPDATE tasks SET task_type = 'background' WHERE id = :tid", {'tid': task_id})
            conn.commit()
            return {'success': True, 'message': f'已将「{trow[1]}」设为背景资料问卷'}
        else:
            cursor.execute("UPDATE tasks SET task_type = 'survey' WHERE id = :tid", {'tid': task_id})
            conn.commit()
            return {'success': True, 'message': f'已取消「{trow[1]}」的背景资料标记'}
