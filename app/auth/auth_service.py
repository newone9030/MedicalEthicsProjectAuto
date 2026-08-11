"""
认证服务：密码哈希(PBKDF2-HMAC-SHA256)、注册、登录
"""

import hashlib
import secrets
import string
from app.db import get_connection
from app.config import PBKDF2_ITERATIONS, SALT_LENGTH


def hash_password(password: str, salt: str = None) -> tuple:
    """
    使用 PBKDF2-HMAC-SHA256 对密码进行哈希
    返回 (password_hash, salt)
    """
    if salt is None:
        salt = secrets.token_hex(SALT_LENGTH)

    password_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        PBKDF2_ITERATIONS
    ).hex()

    return password_hash, salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    """
    验证密码是否匹配
    """
    computed_hash, _ = hash_password(password, salt)
    return computed_hash == password_hash


def generate_random_password(length: int = 6) -> str:
    """
    生成随机默认密码（数字+小写字母）
    """
    chars = string.digits + string.ascii_lowercase
    return ''.join(secrets.choice(chars) for _ in range(length))


def register_user(username: str, password: str, role: str = 'student',
                  real_name: str = None, class_name: str = None,
                  student_id: str = None, user_type: str = 'formal',
                  must_change_password: int = 0) -> dict:
    """
    注册新用户
    返回 {'success': True/False, 'message': str, 'user_id': int}
    """
    # 校验用户名长度
    if len(username) < 2 or len(username) > 50:
        return {'success': False, 'message': '用户名长度需在2-50个字符之间'}

    # 校验密码长度
    if len(password) < 6:
        return {'success': False, 'message': '密码长度至少6位'}

    # 校验角色
    if role not in ('admin', 'student'):
        return {'success': False, 'message': '无效的用户角色'}

    with get_connection() as conn:
        cursor = conn.cursor()

        # 检查用户名是否已存在
        cursor.execute("SELECT id FROM users WHERE username = :uname", {'uname': username})
        if cursor.fetchone():
            return {'success': False, 'message': f'用户名 "{username}" 已被注册'}

        # 检查学号是否已被使用
        if student_id:
            cursor.execute("SELECT id FROM users WHERE student_id = :sid", {'sid': student_id})
            if cursor.fetchone():
                return {'success': False, 'message': f'学号 "{student_id}" 已被使用'}

        # 密码哈希
        password_hash, salt = hash_password(password)

        # 插入用户
        cursor.execute("""
            INSERT INTO users (username, password_hash, salt, role, real_name, class_name, student_id, user_type, status, must_change_password)
            VALUES (:uname, :phash, :salt, :role, :rname, :cname, :sid, :utype, 'active', :mcp)
        """, {
            'uname': username,
            'phash': password_hash,
            'salt': salt,
            'role': role,
            'rname': real_name,
            'cname': class_name,
            'sid': student_id,
            'utype': user_type,
            'mcp': must_change_password
        })
        conn.commit()

        # 获取新用户ID
        cursor.execute("SELECT id FROM users WHERE username = :uname", {'uname': username})
        user_id = cursor.fetchone()[0]

        return {'success': True, 'message': '注册成功', 'user_id': user_id}


def get_student_list() -> list:
    """
    获取所有学生账号列表（供管理员使用）
    返回 [{'id': int, 'username': str, 'real_name': str, 'class_name': str,
           'student_id': str, 'status': str, 'must_change_password': bool, 'created_at': str}, ...]
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, username, real_name, class_name, student_id, status,
                   must_change_password, created_at, user_type
            FROM users WHERE role = 'student'
            ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()
        result = []
        for row in rows:
            result.append({
                'id': row[0],
                'username': row[1],
                'real_name': row[2] or '',
                'class_name': row[3] or '',
                'student_id': row[4] or '',
                'status': row[5],
                'must_change_password': bool(row[6]),
                'created_at': str(row[7]) if row[7] else '',
                'user_type': row[8] or 'formal',
            })
        return result


def toggle_student_status(student_id_val: int) -> dict:
    """
    切换学生账号启用/禁用状态
    返回 {'success': True/False, 'message': str}
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, status FROM users WHERE id = :uid AND role = 'student'",
            {'uid': student_id_val}
        )
        row = cursor.fetchone()
        if not row:
            return {'success': False, 'message': '学生账号不存在'}

        new_status = 'disabled' if row[1] == 'active' else 'active'
        cursor.execute(
            "UPDATE users SET status = :st WHERE id = :uid",
            {'st': new_status, 'uid': student_id_val}
        )
        conn.commit()
        status_text = '禁用' if new_status == 'disabled' else '启用'
        return {'success': True, 'message': f'账号已{status_text}'}


def reset_student_password(student_id_val: int, new_password: str = None) -> dict:
    """
    重置学生账号密码
    返回 {'success': True/False, 'message': str, 'new_password': str}
    """
    if new_password is None:
        new_password = generate_random_password(6)
    elif len(new_password) < 6:
        return {'success': False, 'message': '密码长度至少6位'}

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM users WHERE id = :uid AND role = 'student'",
            {'uid': student_id_val}
        )
        if not cursor.fetchone():
            return {'success': False, 'message': '学生账号不存在'}

        password_hash, salt = hash_password(new_password)
        cursor.execute("""
            UPDATE users SET password_hash = :phash, salt = :salt, must_change_password = 1
            WHERE id = :uid
        """, {'phash': password_hash, 'salt': salt, 'uid': student_id_val})
        conn.commit()

        return {
            'success': True,
            'message': '密码已重置',
            'new_password': new_password
        }


def delete_student(student_id_val: int) -> dict:
    """
    删除学生账号（仅限 student 角色）
    返回 {'success': True/False, 'message': str}
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM users WHERE id = :uid AND role = 'student'",
            {'uid': student_id_val}
        )
        if not cursor.fetchone():
            return {'success': False, 'message': '学生账号不存在'}

        # 先删除关联的作答记录
        cursor.execute(
            "DELETE FROM response_details WHERE response_id IN "
            "(SELECT id FROM responses WHERE student_id = :uid)",
            {'uid': student_id_val}
        )
        cursor.execute(
            "DELETE FROM responses WHERE student_id = :uid",
            {'uid': student_id_val}
        )
        # 删除用户
        cursor.execute(
            "DELETE FROM users WHERE id = :uid",
            {'uid': student_id_val}
        )
        conn.commit()
        return {'success': True, 'message': '账号已删除'}


def login(username: str, password: str) -> dict:
    """
    用户登录
    返回 {'success': True/False, 'message': str, 'user': dict}
    """
    if not username or not password:
        return {'success': False, 'message': '请输入用户名和密码'}

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, username, password_hash, salt, role, real_name, class_name, status, must_change_password, user_type
            FROM users WHERE username = :uname
        """, {'uname': username})

        row = cursor.fetchone()
        if not row:
            return {'success': False, 'message': '用户名或密码错误'}

        user_id, uname, pw_hash, salt, role, rname, cname, status, mcp, utype = row

        # 检查账号状态
        if status == 'disabled':
            return {'success': False, 'message': '账号已被禁用，请联系管理员'}

        # 验证密码
        if not verify_password(password, pw_hash, salt):
            return {'success': False, 'message': '用户名或密码错误'}

        return {
            'success': True,
            'message': '登录成功',
            'user': {
                'id': user_id,
                'username': uname,
                'role': role,
                'real_name': rname,
                'class_name': cname,
                'user_type': utype or 'formal',
                'must_change_password': bool(mcp)
            }
        }


def change_password(user_id: int, old_password: str, new_password: str) -> dict:
    """
    修改密码
    """
    if len(new_password) < 6:
        return {'success': False, 'message': '新密码长度至少6位'}

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT password_hash, salt FROM users WHERE id = :uid",
            {'uid': user_id}
        )
        row = cursor.fetchone()
        if not row:
            return {'success': False, 'message': '用户不存在'}

        pw_hash, salt = row

        # 验证旧密码
        if not verify_password(old_password, pw_hash, salt):
            return {'success': False, 'message': '原密码不正确'}

        # 更新密码
        new_hash, new_salt = hash_password(new_password)
        cursor.execute("""
            UPDATE users SET password_hash = :phash, salt = :salt, must_change_password = 0
            WHERE id = :uid
        """, {'phash': new_hash, 'salt': new_salt, 'uid': user_id})
        conn.commit()

        return {'success': True, 'message': '密码修改成功'}
