---
name: student-font-and-question-navigation
overview: 1. 医学生页面字号整体增大2号（background_survey_view、survey_taker_view、student_dashboard_view） 2. 非背景调查任务改为单题显示，逐题切换，支持暂存和一次性提交
todos:
  - id: increase-font-sizes
    content: 增大背景资料问卷页、任务作答页、学生仪表盘、知情同意页及学生头部中所有文本字号+2
    status: completed
  - id: redesign-question-pagination
    content: 重构 survey_taker_view.py：将案例分页改为题目逐题分页，支持逐题暂存和一次性提交
    status: completed
    dependencies:
      - increase-font-sizes
---

## 用户需求

### 1. 学生页面全局字体增大
医学生能访问的所有页面中，字号统一增大2个号，包括：
- 背景资料问卷页（background_survey_view.py）
- 任务作答页（survey_taker_view.py）
- 学生仪表盘（student_dashboard_view.py）
- 知情同意页（main.py 中 _build_consent_page）
- 学生仪表盘头部（main.py 中 _build_student_page）

### 2. 任务作答逐题分页改版
针对非背景调查的普通任务，将当前"按案例分页"改为"按题目逐题显示"：
- 每页仅显示一道题目，通过"上一题"/"下一题"按钮切换
- 每道题目可独立暂存（保存草稿到数据库）
- 到达最后一题时，"下一题"按钮替换为"提交全部"按钮
- 点击"提交全部"一次性提交所有案例的所有题目
- 进度条按题目总数计算，显示当前题目所在的案例信息和题号
- 背景调查任务保持现有布局不变（按案例分组，所有题目同页显示）

## 核心功能
- 字号+2：覆盖学生端所有页面的标题、正文、提示、标签、进度等文本元素
- 逐题分页：将问卷作答页从案例维度改为题目维度导航
- 逐题暂存：每道题可独立保存草稿
- 统一提交：所有题目完成后一次性提交，保持现有提交校验逻辑

## 技术方案

### 字号修改策略
采用手动逐文件、逐处+2的方式修改，因为 Flet 框架中字号分散在各个控件的 `size` 参数中，无法通过全局主题统一控制。涉及文件：

| 文件 | 当前字号范围 | 修改后范围 |
|------|-------------|-----------|
| `background_survey_view.py` | 10-20 | 12-22 |
| `survey_taker_view.py` | 11-20 | 13-22 |
| `student_dashboard_view.py` | 10-22 | 12-24 |
| `main.py`（学生视图部分） | 13-20 | 15-22 |

### 逐题分页架构设计

#### 数据结构重构
当前 `survey_taker_view.py` 使用 `active_cases`（案例列表）+ `current_case_idx`（当前案例索引）进行案例级翻页。改版后：

```
flat_questions = []  # 展平后的题目列表
# 结构: [(case_dict, question_dict), ...]
# 遍历所有 active_cases，将其下所有题目展平为线性列表

current_question_idx = [0]  # 当前题目在 flat_questions 中的索引
```

#### 导航逻辑
- `go_prev()`: `current_question_idx[0] -= 1`，当 idx=0 时隐藏"上一题"
- `go_next()`: `current_question_idx[0] += 1`，当 idx=len-1 时显示"提交全部"替代"下一题"
- 进度条：`progress = (idx + 0.5) / len(flat_questions)`

#### 标题栏显示
```
案例 1/3: 案例名称 | 第 2/5 题
```
从 `flat_questions[idx]` 的元组中获取 case 信息和 question 在 case 内的序号。

#### 暂存逻辑
当前 `handle_save_draft` 保存整个案例的答案。改为只保存当前题目的答案：
- 仅收集当前题目对应的 `{qid: answer}` 字典
- 调用 `save_draft(task_id, case['id'], student_id, case_answers)`
- 成功提示改为"题目已暂存"

#### 提交流程（保持不变）
`handle_submit` 遍历所有 `active_cases` 的所有题目，收集全部答案，一次性提交。现有的未完成检查、确认对话框逻辑均保持不变。

### 关键设计决策
1. **背景调查页面不受逐题分页影响**：背景调查页面通过 `_build_background_page` 独立路由，使用 `build_background_survey_view` 构建，保持案例分组布局
2. **all_answers 字典保持不变**：仍使用 `{case_id}_{qid}` 作为 key，跨题目翻页时状态保持
3. **readonly 模式兼容**：只读模式（查看已提交作答）仍使用逐题翻页，但隐藏暂存和提交按钮
4. **按钮文案变化**：`上一案例/下一案例` → `上一题/下一题`
