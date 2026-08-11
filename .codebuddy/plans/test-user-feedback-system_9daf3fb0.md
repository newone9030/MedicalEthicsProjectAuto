---
name: test-user-feedback-system
overview: 完整反馈系统：管理员维护反馈任务（按页面分类），测试用户完成作答后进入9步以上反馈流程——引导→说明→案例题评价(N页)→作答要求与任务负担→课程影响→系统与隐私体验→开放式反馈→确认提交。
todos:
  - id: db-migration
    content: 修改 app/db.py：_migrate_sqlite 增加 user_type 迁移；_create_sqlite_tables 新增 feedback_tasks(page_category)/feedback_questions/feedback_question_options/feedback_task_mappings/feedback_responses(survey_question_id nullable) 五张表
    status: completed
  - id: auth-service
    content: 修改 app/auth/auth_service.py：register_user 加 user_type 参数和 INSERT 列；login SELECT 加 u.user_type 解包扩展为10变量；get_student_list SELECT 加 u.user_type row[8]
    status: completed
    dependencies:
      - db-migration
  - id: feedback-admin-service
    content: 新建 app/auth/feedback_admin_service.py：反馈任务CRUD(含page_category)、题目CRUD、选项CRUD、映射CRUD、get_all_survey_questions
    status: completed
    dependencies:
      - db-migration
  - id: account-manager-view
    content: 修改 app/auth/account_manager_view.py：open_create_dlg 加 user_type Dropdown；_build_student_row 加类型标签；refresh_stats 和初始统计加测试用户计数
    status: completed
    dependencies:
      - auth-service
  - id: feedback-task-manager-view
    content: 新建 app/auth/feedback_task_manager_view.py：列表页(按category分组)+编辑页(含category选择、题目管理、选项管理、仅case类显示关联调查题区域)
    status: completed
    dependencies:
      - feedback-admin-service
  - id: feedback-service
    content: 新建 app/student/feedback_service.py：get_student_answered_questions、get_feedback_tasks_for_question、get_feedback_tasks_by_category、submit_feedbacks、has_feedback
    status: completed
    dependencies:
      - db-migration
  - id: feedback-view
    content: 新建 app/student/feedback_view.py：8步反馈视图(引导+说明+N案例评价+4固定类别页+确认提交)，每页统一渲染radio/open反馈题目，数据暂存内存
    status: completed
    dependencies:
      - feedback-service
  - id: dashboard-and-main
    content: 修改 main.py(+/admin/feedback/*和/student/feedback路由、_build_admin_dashboard加入口卡片、_build_feedback_page)和 student_dashboard_view.py(refresh_task末尾追加测试用户反馈入口卡片)
    status: completed
    dependencies:
      - feedback-view
      - feedback-task-manager-view
      - account-manager-view
---

## 产品概述
为医学生伦理调查研究系统增加测试用户/正式用户分类管理，管理员可维护反馈任务（按 page_category 分类）。测试学生完成全部任务后进入8步多页面反馈流程。

## 核心功能

### 一、账号分类管理
- 管理员创建账号时通过下拉框选择用户类型：正式用户 / 测试用户
- 学生列表中以彩色标签展示用户类型（橙色"测试"/蓝色"正式"）
- 统计栏增加测试用户计数

### 二、管理员反馈任务维护
- 管理员仪表盘新增"反馈任务维护"入口卡片
- 创建/编辑反馈任务时可设置 page_category：`case`、`task_burden`、`course_impact`、`system_privacy`、`open_feedback`
- 两种反馈题目类型：单选题（radio，支持条件文本框触发）+ 开放题（open）
- 仅 `case` 类任务通过 feedback_task_mappings 关联到具体调查题；其余4类直接按 category 展示

### 三、测试用户8步反馈流程
1. **引导页** - 固定引导文字 + "下一步"
2. **说明页** - 固定说明文字 + "开始填写"
3. **~N+2 案例题评价页** - 每道已答题一页，加载 page_category='case' 且已关联该题的反馈任务
4. **作答要求与任务负担页** - 固定引导文案 + page_category='task_burden' 的全部反馈任务
5. **课程影响页** - 固定引导文案 + page_category='course_impact' 的全部反馈任务
6. **系统与隐私体验页** - 固定引导文案 + page_category='system_privacy' 的全部反馈任务
7. **开放式反馈页** - 固定引导文案 + page_category='open_feedback' 的全部反馈任务
8. **确认提交页** - 汇总统计 + 批量写入数据库


## 技术栈
- Python + Flet 0.86 + SQLite3 WAL
- 同步事件处理器由 main.py monkey-patch 自动包装为 async
- page.go(route) 导航，session 传递状态

## 实现方案

### 1. 数据库层 (app/db.py)

**a) users 表迁移**：`_migrate_sqlite` 中检查 user_type 列，不存在则：
```sql
ALTER TABLE users ADD COLUMN user_type VARCHAR2(10) DEFAULT 'formal'
```

**b) 新建5张表**：在 `_create_sqlite_tables` 末尾追加（含 page_category 字段，survey_question_id 允许 NULL）：

```sql
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
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS feedback_question_options (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL REFERENCES feedback_questions(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    value INTEGER NOT NULL,
    sort_order INTEGER DEFAULT 0,
    requires_comment INTEGER DEFAULT 0
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
```

### 2. 认证服务层 (app/auth/auth_service.py)

**register_user(L46)**：增加 `user_type: str = 'formal'` 参数，INSERT 语句(L83-95)增加 `user_type` 列和 `:utype` 绑定。

**login(L226)**：SELECT(L236-238)增加 `u.user_type`，解包(L245)从9变量扩展为10变量 `user_id, uname, pw_hash, salt, role, rname, cname, status, mcp, utype = row`。返回 user dict(L258-265)增加 `'user_type': utype`。

**get_student_list(L105)**：SELECT(L113-117)增加 `u.user_type`。返回 list 每项(L122-131)增加 `'user_type': row[8]`。

### 3. 反馈任务管理服务 (app/auth/feedback_admin_service.py 新建)

```python
def create_feedback_task(title, description, page_category='case') -> dict
def update_feedback_task(task_id, title, description, page_category) -> dict
def delete_feedback_task(task_id) -> dict
def get_feedback_task_list(page_category=None) -> list  # 可按category筛选
def get_feedback_task_detail(task_id) -> dict  # 含questions和options
def add_feedback_question(task_id, question_text, question_type='radio') -> dict
def update_feedback_question(question_id, question_text, question_type=None) -> dict
def delete_feedback_question(question_id) -> dict
def add_feedback_option(question_id, label, value, sort_order, requires_comment=0) -> dict
def update_feedback_option(option_id, label, value, requires_comment) -> dict
def delete_feedback_option(option_id) -> dict
def get_feedback_task_mappings(task_id) -> list
def add_feedback_task_mapping(task_id, survey_question_id) -> dict
def remove_feedback_task_mapping(task_id, survey_question_id) -> dict
def get_all_survey_questions() -> list  # 所有case_questions，含case标题
```

### 4. 反馈任务管理视图 (app/auth/feedback_task_manager_view.py 新建)

**列表页**：按 page_category 分组展示卡片，创建按钮先选 category。

**编辑页**：包含标题、描述、page_category Dropdown（创建后不可改）、题目管理（添加单选/开放题）、选项管理（仅单选）。仅 category='case' 时显示"关联调查题"区域。复用现有卡片/对话框样式。

### 5. 学生反馈服务 (app/student/feedback_service.py 新建)

```python
def get_student_answered_questions(student_id, task_id) -> list
# JOIN: responses→response_details→case_questions→cases→task_cases
# WHERE r.status='submitted', 按 tc.sort_order, cq.sort_order 排序

def get_feedback_tasks_for_question(survey_question_id) -> list
# JOIN: feedback_task_mappings→feedback_tasks→feedback_questions→feedback_question_options
# 仅查 page_category='case'

def get_feedback_tasks_by_category(page_category) -> list
# 按 page_category 查所有任务，含questions和options，用于页面4-7

def submit_feedbacks(student_id, feedbacks_list) -> dict
# 批量 INSERT INTO feedback_responses，先 DELETE 已有记录

def has_feedback(student_id) -> bool
```

### 6. 学生反馈视图 (app/student/feedback_view.py 新建)

**step_index 映射**：
- 0=引导页，1=说明页
- 2 ~ N+1 = 案例评价页（N=answered_questions 数量）
- N+2 = 作答要求与任务负担页
- N+3 = 课程影响页
- N+4 = 系统与隐私体验页
- N+5 = 开放式反馈页
- N+6 = 确认提交页

**每页渲染逻辑统一**：
- 顶部固定引导文案（取自配置）
- 反馈任务题目：radio类型→RadioGroup+条件TextField，open类型→TextField(multiline)
- 导航按钮：上一页/下一页/提交

**固定引导文案**：
- 作答要求与任务负担："请评价作答要求和任务负担——请根据您完成所有情境任务的实际体验，评价作答要求的清晰度、任务数量和完成时间是否合理。"
- 课程影响："请评价课程影响——请根据您的真实感受，评价本次预测试对您课程学习的影响。"
- 系统与隐私体验："请评价系统与隐私体验——请根据您使用本电子调查系统的实际体验，评价系统操作流程、界面设计和隐私保护。"
- 开放式反馈："开放式反馈——如有任何其他意见、建议或您认为需要补充的内容，请在下方自由填写。"

### 7. 管理员账号管理视图 (app/auth/account_manager_view.py)

- `open_create_dlg(L171)`：create_password 后增加 user_type Dropdown（正式用户/测试用户）
- `do_create(L196)`：传入 `user_type=user_type_dropdown.value`
- `_build_student_row(L72)`：status 标签前增加类型标签（测试=#FFF3E0/#FF9800，正式=#E3F2FD/#1565C0）
- `refresh_stats(L36)` 和初始统计(L351-377)：增加 `test_count` 容器

### 8. 学生仪表盘 (app/student/student_dashboard_view.py)

refresh_task末尾(L450 _add_history_tasks之后)：
- 条件：`user_type=='test'` + `get_active_task_for_student() is None` + bg completed + `not has_feedback()`
- 追加反馈入口卡片："预测试最终反馈" + 说明文字 + `ElevatedButton("进入反馈")` → `page.go('/student/feedback')`

### 9. 主路由 (main.py)

新增路由：
- `/admin/feedback/tasks` → `_build_feedback_task_list(page)`
- `/admin/feedback/task/editor` → `_build_feedback_task_editor(page, task_id)`
- `/student/feedback` → `_build_feedback_page(page)`

`_build_feedback_page`：加载已答题+各category任务，构建feedback_view，on_submit_callback中调用submit_feedbacks后page.go('/student/dashboard')。

管理员仪表盘增加 `_entry_card('反馈任务维护', ...)`。


## Agent Extensions
### SubAgent
- **code-explorer**
  - Purpose: 在实现过程中跨文件定位代码引用，确认函数签名、列索引和数据结构
  - Expected outcome: 准确定位每处修改的具体行号，确保INSERT/SELECT列数与索引匹配
