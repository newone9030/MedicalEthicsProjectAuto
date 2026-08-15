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

        # 新任务默认排到末尾
        cursor.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM tasks")
        sort_order = cursor.fetchone()[0]

        cursor.execute("""
            INSERT INTO tasks (name, description, start_time, end_time, status, task_type, created_by, sort_order)
            VALUES (:name, :desc, :stime, :etime, 'draft', :ttype, :cby, :sorder)
        """, {
            'name': name, 'desc': description,
            'stime': start_time, 'etime': end_time, 'ttype': task_type, 'cby': created_by,
            'sorder': sort_order
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
                   (SELECT COUNT(*) FROM task_cases WHERE task_id = t.id) as case_count,
                   t.sort_order
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

        sql += " ORDER BY t.sort_order ASC, t.id ASC"

        cursor.execute(sql, params)
        tasks = []
        for row in cursor.fetchall():
            tasks.append({
                'id': row[0], 'name': row[1], 'description': row[2],
                'start_time': row[3], 'end_time': row[4], 'status': row[5],
                'created_at': row[6], 'task_type': row[7], 'case_count': row[8]
            })
        return tasks


def get_active_tasks_for_student(student_id: int) -> list:
    """
    获取学生当前所有进行中任务（按管理员设置的顺序返回）
    返回 status='active' 且未到截止时间的全部任务，排除背景资料问卷
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
            ORDER BY t.sort_order ASC, t.id ASC
        """, {'now': now})

        rows = cursor.fetchall()
        if not rows:
            return []

        tasks = []
        for row in rows:
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

            tasks.append(task)

        return tasks


def get_active_task_for_student(student_id: int) -> dict:
    """
    获取学生当前进行中任务（兼容旧调用）
    返回最先开始的进行中任务；无进行中任务时返回 None
    """
    tasks = get_active_tasks_for_student(student_id)
    return tasks[0] if tasks else None


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


def _get_sorted_task_ids(cursor) -> list:
    """按管理员设置的顺序返回全部任务 (id, sort_order) 列表"""
    cursor.execute("""
        SELECT id, sort_order FROM tasks
        ORDER BY sort_order ASC, id ASC
    """)
    return cursor.fetchall()


def move_task_up(task_id: int) -> dict:
    """将任务在管理员顺序中上移一位（与前一任务交换排序值）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        ordered = _get_sorted_task_ids(cursor)
        ids = [r[0] for r in ordered]
        if task_id not in ids:
            return {'success': False, 'message': '任务不存在'}
        idx = ids.index(task_id)
        if idx == 0:
            return {'success': False, 'message': '已是第一个任务，无法上移'}
        prev_id, prev_order = ordered[idx - 1]
        cur_order = ordered[idx][1]
        cursor.execute("UPDATE tasks SET sort_order = :so WHERE id = :tid",
                       {'so': prev_order, 'tid': task_id})
        cursor.execute("UPDATE tasks SET sort_order = :so WHERE id = :tid",
                       {'so': cur_order, 'tid': prev_id})
        conn.commit()
        return {'success': True, 'message': '任务顺序已上移'}


def move_task_down(task_id: int) -> dict:
    """将任务在管理员顺序中下移一位（与后一任务交换排序值）"""
    with get_connection() as conn:
        cursor = conn.cursor()
        ordered = _get_sorted_task_ids(cursor)
        ids = [r[0] for r in ordered]
        if task_id not in ids:
            return {'success': False, 'message': '任务不存在'}
        idx = ids.index(task_id)
        if idx == len(ids) - 1:
            return {'success': False, 'message': '已是最后一个任务，无法下移'}
        next_id, next_order = ordered[idx + 1]
        cur_order = ordered[idx][1]
        cursor.execute("UPDATE tasks SET sort_order = :so WHERE id = :tid",
                       {'so': next_order, 'tid': task_id})
        cursor.execute("UPDATE tasks SET sort_order = :so WHERE id = :tid",
                       {'so': cur_order, 'tid': next_id})
        conn.commit()
        return {'success': True, 'message': '任务顺序已下移'}


def reopen_task(task_id: int) -> dict:
    """将已关闭的任务回退到草稿状态（closed → draft），便于重新编辑和发布"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM tasks WHERE id = :tid", {'tid': task_id})
        row = cursor.fetchone()
        if not row:
            return {'success': False, 'message': '任务不存在'}
        if row[0] != 'closed':
            return {'success': False, 'message': '仅已关闭的任务可回退到草稿'}
        cursor.execute("UPDATE tasks SET status = 'draft' WHERE id = :tid", {'tid': task_id})
        conn.commit()
        return {'success': True, 'message': '任务已回退到草稿状态，可重新编辑并发布'}


def is_task_unlocked_for_student(task_id: int, student_id: int) -> bool:
    """
    顺序作答限制：判断学生当前是否可作答指定任务。
    按管理员设置的顺序遍历进行中任务，若到达目标任务之前存在尚未全部提交的任务，则返回 False。
    仅 ycs 账号豁免顺序限制，其余用户（含测试用户）均须按顺序作答。
    """
    # 仅 ycs 账号豁免顺序限制（便于完整测试）；任务仅暂存未提交时，后续任务一律锁定
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE id = :sid", {'sid': student_id})
        row = cursor.fetchone()
        if row and row[0] == 'ycs':
            return True

    tasks = get_active_tasks_for_student(student_id)
    for task in tasks:
        if task['id'] == task_id:
            return True
        all_submitted = all(
            c.get('response_status') == 'submitted' for c in task['cases']
        )
        if not all_submitted:
            return False
    return False
