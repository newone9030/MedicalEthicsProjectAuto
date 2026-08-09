"""
系统配置常量
"""

import os
import configparser

# 项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 数据库配置文件路径（可覆盖）
DATABASE_INI_PATH = os.environ.get('DB_CONFIG', os.path.join(BASE_DIR, 'database.ini'))

# SQL 文件路径
SCHEMA_SQL_PATH = os.path.join(BASE_DIR, 'sql', 'schema.sql')

# 密码安全
PBKDF2_ITERATIONS = 100000
SALT_LENGTH = 32

# 伦理主题分类
THEME_OPTIONS = ['患者隐私', '知情同意', '临终伦理', '科研诚信', '医患关系']

# 案例题型
QUESTION_TYPES = {
    'single_choice': '单选题',
    'multiple_choice': '多选题',
    'open': '开放式文本题'
}

# 任务状态
TASK_STATUS = {
    'draft': '草稿',
    'published': '已发布',
    'active': '进行中',
    'closed': '已关闭'
}


def load_database_config():
    """从 database.ini 加载 Oracle 连接配置"""
    if not os.path.exists(DATABASE_INI_PATH):
        raise FileNotFoundError(
            f"数据库配置文件不存在: {DATABASE_INI_PATH}\n"
            "请复制 database.ini 模板并填写正确的 Oracle 连接信息"
        )

    config = configparser.ConfigParser()
    config.read(DATABASE_INI_PATH, encoding='utf-8')

    if 'oracle' not in config:
        raise ValueError("database.ini 中缺少 [oracle] 配置节")

    section = config['oracle']

    return {
        'engine': section.get('engine', 'sqlite'),
        'host': section.get('host', 'localhost'),
        'port': int(section.get('port', '1521')),
        'service_name': section.get('service_name', 'XEPDB1'),
        'user': section.get('user', 'survey_admin'),
        'password': section.get('password', ''),
        'min_connections': int(section.get('min_connections', '2')),
        'max_connections': int(section.get('max_connections', '20')),
    }
