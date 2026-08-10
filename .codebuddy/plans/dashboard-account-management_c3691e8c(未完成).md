---
name: dashboard-account-management
overview: 在管理员仪表盘增加账号管理功能：添加 student_id 字段到数据库、创建账号管理页面、支持管理员创建/管理医学生账号。
design:
  architecture:
    framework: react
  styleKeywords:
    - Material Blue
    - Card Layout
    - Gradient Header
    - Clean Table
  fontSystem:
    fontFamily: Roboto
    heading:
      size: 20px
      weight: 700
    subheading:
      size: 16px
      weight: 500
    body:
      size: 14px
      weight: 400
  colorSystem:
    primary:
      - "#1565C0"
      - "#1976D2"
      - "#42A5F5"
    background:
      - "#F5F7FA"
      - "#FFFFFF"
    text:
      - "#212121"
      - "#757575"
      - "#9E9E9E"
    functional:
      - "#4CAF50"
      - "#FF5252"
      - "#FF9800"
      - "#9C27B0"
todos:
  - id: add-student-id-column
    content: 在 db.py 的 _create_sqlite_tables 和 sql/schema.sql 中为 users 表添加 student_id 列，并增加数据库迁移逻辑兼容已有 SQLite 库
    status: pending
  - id: add-auth-service-functions
    content: 在 auth_service.py 中添加 create_student_account、get_all_students、delete_student_account、reset_student_password 四个函数
    status: pending
    dependencies:
      - add-student-id-column
  - id: create-account-manager-view
    content: 新建 account_manager_view.py，实现账号管理页面（学生列表、创建弹窗、删除确认、重置密码反馈）
    status: pending
    dependencies:
      - add-auth-service-functions
  - id: integrate-dashboard-routing
    content: 在 main.py 中添加 /admin/accounts 路由、_build_account_management 视图函数、Dashboard 第四个入口卡片
    status: pending
    dependencies:
      - create-account-manager-view
---

## 用户需求
在管理员 Dashboard 界面增加账号管理功能入口，管理员可以创建医学生账号，填写账号名（username）、学号（student_id）、初始密码。创建的学生账号登录系统后，可在学生仪表盘看到已发布/进行中的任务并作答。

## 产品概述
为管理员 Dashboard 增加第四个功能入口卡片"账号管理"，点击后进入账号管理页面。该页面支持创建医学生账号、查看已有学生列表、删除账号和重置密码。

## 核心功能
- **Dashboard 入口**：在管理员仪表盘功能入口区域新增"账号管理"卡片，图标使用管理相关图标，点击进入账号管理页面
- **创建学生账号**：弹窗表单，填写账号名、学号、初始密码（带随机生成按钮），确认后创建 student 角色账号，must_change_password 设为 1
- **学生列表展示**：表格或列表形式展示所有 student 角色账号，包含账号名、学号、姓名、班级、状态、创建时间
- **账号操作**：支持重置密码（随机生成新密码并显示）、删除账号（带确认对话框、仅限 student 角色）
- **数据持久化**：student_id 字段追加到 users 表，兼容 SQLite 和 Oracle

## 技术栈
- 后端：Python + Flet 0.86.x
- 数据库：SQLite（默认）/ Oracle（可选，双模式兼容）
- 密码安全：PBKDF2-HMAC-SHA256（复用现有 hash_password 函数）

## 实现方案

### 数据库变更
在 users 表中新增 `student_id` 列（VARCHAR2(30)）。采用 ALTER TABLE ADD COLUMN 方式在线追加，不影响现有数据。

- **db.py `_create_sqlite_tables()` 第 46 行后**：在 `class_name` 之后插入 `student_id VARCHAR2(30)` 列定义
- **sql/schema.sql 第 30 行后**：同步追加 `student_id VARCHAR2(30)` 列
- **兼容处理**：SQLite 已存在的数据库需执行 `ALTER TABLE users ADD COLUMN student_id VARCHAR2(30)` 兼容迁移

### 服务层新增函数（auth_service.py）
| 函数名 | 功能 |
|--------|------|
| `create_student_account(username, student_id, password, real_name, class_name)` | 管理员创建学生账号，must_change_password=1 |
| `get_all_students()` | 获取所有 student 角色用户列表，含 student_id 字段 |
| `delete_student_account(user_id)` | 删除学生账号（仅限 student 角色，防止误删 admin） |
| `reset_student_password(user_id)` | 重置学生密码为随机6位密码，must_change_password=1，返回新密码 |

### 新增账号管理页面（app/auth/account_manager_view.py）
- **页面布局**：顶部返回按钮 + 标题"账号管理"，右侧"创建账号"按钮
- **学生列表**：使用 `ft.DataTable` 或卡片列表，展示账号名、学号、姓名、班级、状态、创建时间
- **操作列**：每行含"重置密码"和"删除"按钮
- **创建弹窗**：`ft.AlertDialog`，包含账号名、学号、姓名（选填）、班级（选填）、初始密码（带随机生成按钮）
- **删除确认**：复用现有 `_close_dialog` 模式，弹出确认对话框后执行删除
- **重置密码反馈**：重置后直接用 SnackBar 显示新密码

### 路由与导航（main.py）
- 新增路由 `/admin/accounts`，在 `_build_view()` 中添加分支
- 新增 `_build_account_management()` 视图构建函数
- Dashboard 的 `entries` Row 中新增第 4 个 `_entry_card('账号管理', ...)`，图标使用 `ft.Icons.MANAGE_ACCOUNTS`

### 关键设计决策
1. **student_id 字段独立存储**：不与 real_name/class_name 混用，语义清晰，便于后续按学号检索
2. **仅管理员可创建学生账号**：create_student_account 不做角色校验（调用方为管理员页面），内部强制 role='student'
3. **must_change_password=1**：创建的学生账号首次登录时强制修改密码
4. **删除保护**：delete_student_account 仅允许删除 role='student' 的用户，防止误删管理员
5. **按钮 API 兼容**：所有按钮使用 `content=ft.Text(...)` 或纯字符串，不使用 `text` 参数（Flet 0.86.x 不支持）

## 设计风格
延续现有管理员 Dashboard 的设计风格：蓝色渐变主题（#1565C0 - #1976D2）、白色卡片、圆角阴影、灰色背景（#F5F7FA）。

### 账号管理页面布局（从上到下）
1. **顶部导航栏**：蓝色渐变背景，左侧"账号管理"标题 + 返回按钮，右侧"创建账号"按钮（白色文字、加号图标）
2. **学生列表区域**：白色卡片容器，内含带表头的列表视图，每行显示账号名、学号、姓名、班级、状态标签、操作按钮。状态使用彩色标签（active=绿色、disabled=红色）
3. **空状态提示**：当无学生账号时，显示 School 大图标 + "暂无学生账号" 文字

### 创建账号弹窗
- 居中 AlertDialog，标题"创建医学生账号"
- 表单字段：账号名（必填）、学号（必填）、姓名、班级、初始密码
- 密码行右侧带"随机生成"按钮（蓝色文字按钮）
- 底部两个按钮：取消（TextButton）、确认创建（ElevatedButton，蓝色）

### 删除确认弹窗
- 复用现有删除确认模式，AlertDialog 标题"确认删除"
- 内容：确定要删除账号「{username}」吗？
- 按钮：取消 + 确认删除（红色背景 ElevatedButton）

### 重置密码反馈
- 重置成功后 SnackBar 显示新密码（持续时间可适当延长），绿色背景提示
