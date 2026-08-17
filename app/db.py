"""
数据库管理器（双模式：SQLite / Oracle）
- 默认使用 SQLite，无需额外配置即可运行
- 当 database.ini 中 engine=oracle 且 Oracle 可用时切换至 Oracle 模式
"""

import sqlite3
import threading
import os
import json
from contextlib import contextmanager
from app.config import load_database_config, BASE_DIR

# 全局状态
_engine = None           # 'sqlite' 或 'oracle'
_sqlite_conn = None      # SQLite 单连接
_oracle_pool = None      # Oracle 连接池
_lock = threading.Lock()
_sqlite_lock = threading.RLock()   # SQLite 单连接并发访问锁（可重入，支持嵌套 get_connection）
_initialized = False

# SQLite 数据库文件路径
##SQLITE_DB_PATH = os.path.join(BASE_DIR, 'survey.db')
mount_path = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "./data")
SQLITE_DB_PATH = os.path.join(mount_path, "survey.db")


def _init_sqlite():
    """初始化 SQLite 数据库（WAL 模式、建表、迁移）"""
    global _sqlite_conn
    _sqlite_conn = sqlite3.connect(SQLITE_DB_PATH, check_same_thread=False)
    _sqlite_conn.execute("PRAGMA journal_mode=WAL")
    _sqlite_conn.execute("PRAGMA busy_timeout=5000")
    _sqlite_conn.execute("PRAGMA foreign_keys=ON")
    _sqlite_conn.row_factory = sqlite3.Row
    _create_sqlite_tables(_sqlite_conn)
    _migrate_sqlite(_sqlite_conn)
    print(f"[DB] SQLite 数据库已连接 ({SQLITE_DB_PATH})")


def _migrate_sqlite(conn):
    """SQLite 数据库迁移：为已有数据库添加缺失字段"""
    cursor = conn.cursor()
    # 检查 student_id 字段是否存在
    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'student_id' not in columns:
        try:
            conn.execute("ALTER TABLE users ADD COLUMN student_id VARCHAR2(50)")
            conn.commit()
            print("[DB] 已添加 users.student_id 字段")
        except Exception as e:
            print(f"[DB] 迁移 users.student_id 失败: {e}")
    # 检查 user_type 字段是否存在
    if 'user_type' not in columns:
        try:
            conn.execute("ALTER TABLE users ADD COLUMN user_type VARCHAR2(10) DEFAULT 'formal'")
            conn.commit()
            print("[DB] 已添加 users.user_type 字段")
        except Exception as e:
            print(f"[DB] 迁移 users.user_type 失败: {e}")


def _create_sqlite_tables(conn):
    """创建 SQLite 表结构"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR2(50) UNIQUE NOT NULL,
            password_hash VARCHAR2(128) NOT NULL,
            salt VARCHAR2(64) NOT NULL,
            role VARCHAR2(10) NOT NULL CHECK(role IN ('admin', 'student')),
            real_name VARCHAR2(50),
            class_name VARCHAR2(100),
            student_id VARCHAR2(50),
            user_type VARCHAR2(10) DEFAULT 'formal',
            status VARCHAR2(10) DEFAULT 'active',
            must_change_password INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title VARCHAR2(200) NOT NULL,
            body TEXT,
            theme VARCHAR2(50),
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS case_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            question_text VARCHAR2(500) NOT NULL,
            question_type VARCHAR2(20) NOT NULL CHECK(question_type IN ('single_choice', 'multiple_choice', 'open')),
            options TEXT,
            hint VARCHAR2(500),
            sort_order INTEGER DEFAULT 0,
            open_text_enabled INTEGER DEFAULT 0,
            open_text_title VARCHAR2(200),
            open_text_hint VARCHAR2(500),
            section_title VARCHAR2(200),
            is_required INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR2(200) NOT NULL,
            description TEXT,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            status VARCHAR2(20) DEFAULT 'draft' CHECK(status IN ('draft', 'published', 'active', 'closed')),
            task_type VARCHAR2(20) DEFAULT 'survey' CHECK(task_type IN ('survey', 'background')),
            sort_order INTEGER DEFAULT 0,
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS task_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            case_id INTEGER NOT NULL REFERENCES cases(id),
            sort_order INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id),
            case_id INTEGER NOT NULL REFERENCES cases(id),
            student_id INTEGER NOT NULL REFERENCES users(id),
            status VARCHAR2(10) DEFAULT 'draft' CHECK(status IN ('draft', 'submitted')),
            submitted_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(task_id, case_id, student_id)
        );

        CREATE TABLE IF NOT EXISTS response_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            response_id INTEGER NOT NULL REFERENCES responses(id) ON DELETE CASCADE,
            question_id INTEGER NOT NULL REFERENCES case_questions(id),
            answer TEXT
        );

        CREATE TABLE IF NOT EXISTS feedback_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title VARCHAR2(200) NOT NULL,
            description TEXT,
            page_category VARCHAR2(20) NOT NULL DEFAULT 'case',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS feedback_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES feedback_tasks(id) ON DELETE CASCADE,
            question_text TEXT NOT NULL,
            question_type VARCHAR2(10) NOT NULL DEFAULT 'radio',
            sort_order INTEGER DEFAULT 0,
            required INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS feedback_question_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL REFERENCES feedback_questions(id) ON DELETE CASCADE,
            label TEXT NOT NULL,
            value INTEGER NOT NULL,
            sort_order INTEGER DEFAULT 0,
            requires_comment INTEGER DEFAULT 0,
            comment_hint TEXT
        );

        CREATE TABLE IF NOT EXISTS feedback_task_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES feedback_tasks(id) ON DELETE CASCADE,
            survey_question_id INTEGER NOT NULL REFERENCES case_questions(id),
            UNIQUE(task_id, survey_question_id)
        );

        CREATE TABLE IF NOT EXISTS feedback_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL REFERENCES users(id),
            survey_question_id INTEGER,
            feedback_question_id INTEGER NOT NULL REFERENCES feedback_questions(id),
            selected_option_id INTEGER REFERENCES feedback_question_options(id),
            comment_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()

    # 增量迁移：为旧表补充 task_type 字段
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(tasks)")
    task_cols = [col[1] for col in cursor.fetchall()]
    if 'task_type' not in task_cols:
        cursor.execute("ALTER TABLE tasks ADD COLUMN task_type VARCHAR2(20) DEFAULT 'survey'")
        conn.commit()
        print('[DB] 已添加 tasks.task_type 字段')

    # 增量迁移：为旧表补充任务排序字段 sort_order（按创建顺序初始化，保证初始顺序稳定）
    if 'sort_order' not in task_cols:
        cursor.execute("ALTER TABLE tasks ADD COLUMN sort_order INTEGER DEFAULT 0")
        cursor.execute("""
            UPDATE tasks SET sort_order = (
                SELECT COUNT(*) FROM tasks AS t2
                WHERE t2.created_at < tasks.created_at
                   OR (t2.created_at = tasks.created_at AND t2.id < tasks.id)
            )
        """)
        conn.commit()
        print('[DB] 已添加 tasks.sort_order 字段')

    # 增量迁移：为旧表补充 hint 字段
    cursor.execute("PRAGMA table_info(case_questions)")
    q_cols = [col[1] for col in cursor.fetchall()]
    if 'hint' not in q_cols:
        cursor.execute("ALTER TABLE case_questions ADD COLUMN hint VARCHAR2(500)")
        conn.commit()
        print('[DB] 已添加 case_questions.hint 字段')

    # 增量迁移：为多选题补充开放式文本框配置字段（题目级，一道多选题仅一个）
    if 'open_text_enabled' not in q_cols:
        cursor.execute("ALTER TABLE case_questions ADD COLUMN open_text_enabled INTEGER DEFAULT 0")
        conn.commit()
        print('[DB] 已添加 case_questions.open_text_enabled 字段')
    if 'open_text_title' not in q_cols:
        cursor.execute("ALTER TABLE case_questions ADD COLUMN open_text_title VARCHAR2(200)")
        conn.commit()
        print('[DB] 已添加 case_questions.open_text_title 字段')
    if 'open_text_hint' not in q_cols:
        cursor.execute("ALTER TABLE case_questions ADD COLUMN open_text_hint VARCHAR2(500)")
        conn.commit()
        print('[DB] 已添加 case_questions.open_text_hint 字段')

    # 增量迁移：为题目补充分组标题（部分标题）字段
    if 'section_title' not in q_cols:
        cursor.execute("ALTER TABLE case_questions ADD COLUMN section_title VARCHAR2(200)")
        conn.commit()
        print('[DB] 已添加 case_questions.section_title 字段')

    # 增量迁移：为题目补充是否必答字段（旧题默认必答）
    if 'is_required' not in q_cols:
        cursor.execute("ALTER TABLE case_questions ADD COLUMN is_required INTEGER DEFAULT 1")
        conn.commit()
        print('[DB] 已添加 case_questions.is_required 字段')

    # 增量迁移：为反馈选项补充 comment_hint 字段
    cursor.execute("PRAGMA table_info(feedback_question_options)")
    opt_cols = [col[1] for col in cursor.fetchall()]
    if 'comment_hint' not in opt_cols:
        cursor.execute("ALTER TABLE feedback_question_options ADD COLUMN comment_hint TEXT")
        conn.commit()
        print('[DB] 已添加 feedback_question_options.comment_hint 字段')

    # 增量迁移：为反馈题目补充 required 字段
    cursor.execute("PRAGMA table_info(feedback_questions)")
    q_cols = [col[1] for col in cursor.fetchall()]
    if 'required' not in q_cols:
        cursor.execute("ALTER TABLE feedback_questions ADD COLUMN required INTEGER DEFAULT 0")
        conn.commit()
        print('[DB] 已添加 feedback_questions.required 字段')


def _init_oracle():
    """初始化 Oracle 连接池"""
    global _oracle_pool
    import oracledb
    config = load_database_config()
    dsn = oracledb.makedsn(
        host=config['host'],
        port=config['port'],
        service_name=config['service_name']
    )
    _oracle_pool = oracledb.create_pool(
        user=config['user'],
        password=config['password'],
        dsn=dsn,
        min=config['min_connections'],
        max=config['max_connections'],
        increment=2
    )
    print(f"[DB] Oracle 连接池已创建 (min={config['min_connections']}, max={config['max_connections']})")


def get_engine():
    """获取当前数据库引擎类型"""
    global _engine, _initialized
    if not _initialized:
        _init_db()
    return _engine


def _init_db():
    """初始化数据库引擎（自动选择 SQLite 或 Oracle）"""
    global _engine, _initialized
    with _lock:
        if _initialized:
            return

        config = load_database_config()
        engine_config = config.get('engine', 'sqlite').lower()

        if engine_config == 'oracle':
            try:
                _init_oracle()
                _engine = 'oracle'
                _initialized = True
                return
            except Exception as e:
                print(f"[DB] Oracle 连接失败: {e}")
                print("[DB] 自动降级为 SQLite 模式")

        # 默认使用 SQLite
        _init_sqlite()
        _engine = 'sqlite'
        _initialized = True


def _convert_oracle_format(fmt):
    """将 Oracle 日期格式转换为 SQLite strftime 格式"""
    replacements = [
        ('YYYY', '%Y'), ('YY', '%y'),
        ('MM', '%m'), ('DD', '%d'),
        ('HH24', '%H'), ('HH12', '%I'),
        ('MI', '%M'), ('SS', '%S'),
        ('MON', '%b'), ('MONTH', '%B'),
        ('WW', '%W'), ('IW', '%W'),
        ('Q', ''),  # SQLite 无季度
    ]
    for old, new in replacements:
        fmt = fmt.replace(old, new)
    return fmt


def _adapt_sql(sql):
    """将 Oracle 特有 SQL 语法适配为 SQLite"""
    if sql is None:
        return sql
    import re
    # TO_CHAR(SYSDATE, '<format>') -> strftime('<converted>', 'now')
    sql = re.sub(
        r"TO_CHAR\s*\(\s*SYSDATE\s*,\s*'([^']*)'\s*\)",
        lambda m: f"strftime('{_convert_oracle_format(m.group(1))}', 'now')",
        sql, flags=re.IGNORECASE
    )
    # TO_CHAR(<expr>, '<format>') -> strftime('<converted>', <expr>)
    sql = re.sub(
        r"TO_CHAR\s*\(\s*([^,]+?)\s*,\s*'([^']*)'\s*\)",
        lambda m: f"strftime('{_convert_oracle_format(m.group(2))}', {m.group(1).strip()})",
        sql, flags=re.IGNORECASE
    )
    # 去掉 FROM DUAL
    sql = re.sub(r'\s+FROM\s+DUAL\b', '', sql, flags=re.IGNORECASE)
    # 替换 NVL(...) -> IFNULL(...)
    sql = sql.replace('NVL(', 'IFNULL(')
    # 替换裸 SYSDATE -> datetime('now')
    sql = re.sub(r'\bSYSDATE\b', "datetime('now')", sql, flags=re.IGNORECASE)
    return sql


class _SqliteCursorWrapper:
    """SQLite 游标包装器，自动转译 Oracle SQL"""
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=None):
        adapted = _adapt_sql(sql)
        if params:
            return self._cursor.execute(adapted, params)
        else:
            return self._cursor.execute(adapted)

    def executemany(self, sql, params_list):
        return self._cursor.executemany(_adapt_sql(sql), params_list)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def fetchmany(self, size=None):
        return self._cursor.fetchmany(size) if size else self._cursor.fetchmany()

    def close(self):
        return self._cursor.close()

    @property
    def description(self):
        return self._cursor.description

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    @property
    def arraysize(self):
        return self._cursor.arraysize

    @arraysize.setter
    def arraysize(self, value):
        self._cursor.arraysize = value


class _SqliteConnectionWrapper:
    """SQLite 连接包装器，返回自动适配的游标"""
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return _SqliteCursorWrapper(self._conn.cursor())

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        pass  # SQLite 连接不关闭，由 close_db 统一管理

    def __getattr__(self, name):
        return getattr(self._conn, name)


@contextmanager
def get_connection():
    """获取数据库连接（上下文管理器）"""
    global _initialized
    if not _initialized:
        _init_db()

    if _engine == 'oracle':
        conn = _oracle_pool.acquire()
        try:
            yield conn
        finally:
            conn.close()
    else:
        # 全局单连接并发访问加锁，防止多线程（Timer 线程 + 主线程）同时操作导致卡死
        with _sqlite_lock:
            yield _SqliteConnectionWrapper(_sqlite_conn)


def execute_sql(sql, params=None, fetch=False):
    """执行 SQL（简化接口，兼容 Oracle 和 SQLite）"""
    if not _initialized:
        _init_db()

    sql = _adapt_sql(sql)

    if _engine == 'oracle':
        conn = _oracle_pool.acquire()
        try:
            cursor = conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            if fetch:
                result = cursor.fetchall()
            else:
                result = cursor
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        with _sqlite_lock:
            cursor = _sqlite_conn.cursor()
            adapted = _adapt_sql(sql)
            if params:
                if isinstance(params, dict):
                    cursor.execute(adapted, params)
                else:
                    cursor.execute(adapted, params)
            else:
                cursor.execute(adapted)
            if fetch:
                result = cursor.fetchall()
            else:
                result = cursor
            _sqlite_conn.commit()
            return result


def get_last_rowid(table_name):
    """获取最后插入行的 ID"""
    if _engine == 'oracle':
        seq_map = {
            'cases': 'seq_cases',
            'case_questions': 'seq_case_questions',
            'tasks': 'seq_tasks',
            'responses': 'seq_responses',
            'task_cases': 'seq_task_cases',
            'users': 'seq_users',
            'response_details': 'seq_response_details',
        }
        seq = seq_map.get(table_name, f'seq_{table_name}')
        rows = execute_sql(f"SELECT {seq}.CURRVAL FROM DUAL", fetch=True)
        return rows[0][0] if rows else None
    else:
        with _sqlite_lock:
            cursor = _sqlite_conn.cursor()
            return cursor.lastrowid


def close_db():
    """关闭数据库连接"""
    global _sqlite_conn, _oracle_pool, _initialized
    if _sqlite_conn:
        _sqlite_conn.close()
        _sqlite_conn = None
        print("[DB] SQLite 连接已关闭")
    if _oracle_pool:
        _oracle_pool.close()
        _oracle_pool = None
        print("[DB] Oracle 连接池已关闭")
    _initialized = False
    _engine = None


def test_connection():
    """测试数据库连接"""
    if not _initialized:
        _init_db()
    if _engine == 'oracle':
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 'Oracle连接成功, 当前时间: ' || TO_CHAR(SYSDATE, 'YYYY-MM-DD HH24:MI:SS') FROM DUAL")
            result = cursor.fetchone()
            print(f"[DB] {result[0]}")
            return True
    else:
        rows = execute_sql("SELECT 'SQLite连接成功' as msg", fetch=True)
        print(f"[DB] {rows[0][0]}")
        return True


# 向后兼容别名
get_pool = get_connection
close_pool = close_db
