-- ============================================
-- 医学生伦理调查研究系统 - Oracle 建表脚本
-- 版本: 1.0
-- 使用方法: sqlplus survey_admin/password@XEPDB1 @schema.sql
-- ============================================

-- 清理旧对象（如果存在）
BEGIN
   FOR t IN (SELECT table_name FROM user_tables WHERE table_name IN ('RESPONSE_DETAILS','RESPONSES','TASK_CASES','TASKS','CASE_QUESTIONS','CASES','USERS'))
   LOOP
      EXECUTE IMMEDIATE 'DROP TABLE ' || t.table_name || ' CASCADE CONSTRAINTS';
   END LOOP;
   FOR s IN (SELECT sequence_name FROM user_sequences WHERE sequence_name IN ('SEQ_USERS','SEQ_CASES','SEQ_CASE_QUESTIONS','SEQ_TASKS','SEQ_TASK_CASES','SEQ_RESPONSES','SEQ_RESPONSE_DETAILS'))
   LOOP
      EXECUTE IMMEDIATE 'DROP SEQUENCE ' || s.sequence_name;
   END LOOP;
END;
/

-- ============================================
-- 1. 用户表
-- ============================================
CREATE TABLE users (
    id              NUMBER PRIMARY KEY,
    username        VARCHAR2(50) NOT NULL UNIQUE,
    password_hash   VARCHAR2(128) NOT NULL,
    salt            VARCHAR2(64) NOT NULL,
    role            VARCHAR2(10) NOT NULL CHECK (role IN ('admin', 'student')),
    real_name       VARCHAR2(50),
    class_name      VARCHAR2(100),
    student_id      VARCHAR2(50),
    status          VARCHAR2(10) DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    must_change_password NUMBER(1) DEFAULT 0 CHECK (must_change_password IN (0, 1)),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE users IS '系统用户表';
COMMENT ON COLUMN users.role IS '用户角色: admin-管理员, student-医学生';
COMMENT ON COLUMN users.student_id IS '学号';
COMMENT ON COLUMN users.status IS '账号状态: active-启用, disabled-禁用';
COMMENT ON COLUMN users.must_change_password IS '是否需要强制修改密码: 0-否, 1-是';

CREATE SEQUENCE seq_users START WITH 1 INCREMENT BY 1 NOCACHE;

CREATE OR REPLACE TRIGGER trg_users_id
BEFORE INSERT ON users
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT seq_users.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- 插入默认管理员账号 (密码: admin123, 部署后务必修改)
INSERT INTO users (username, password_hash, salt, role, real_name, status, must_change_password)
VALUES ('admin', 'PLACEHOLDER_HASH', 'PLACEHOLDER_SALT', 'admin', '系统管理员', 'active', 0);

-- ============================================
-- 2. 案例表
-- ============================================
CREATE TABLE cases (
    id          NUMBER PRIMARY KEY,
    title       VARCHAR2(200) NOT NULL,
    body        CLOB NOT NULL,
    theme       VARCHAR2(50) NOT NULL,
    created_by  NUMBER NOT NULL REFERENCES users(id),
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE cases IS '伦理案例表';
COMMENT ON COLUMN cases.theme IS '伦理主题分类: 患者隐私/知情同意/临终伦理/科研诚信/医患关系';

CREATE SEQUENCE seq_cases START WITH 1 INCREMENT BY 1 NOCACHE;

CREATE OR REPLACE TRIGGER trg_cases_id
BEFORE INSERT ON cases
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT seq_cases.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ============================================
-- 3. 案例题目表
-- ============================================
CREATE TABLE case_questions (
    id                  NUMBER PRIMARY KEY,
    case_id             NUMBER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    question_text       VARCHAR2(500) NOT NULL,
    question_type       VARCHAR2(20) NOT NULL CHECK (question_type IN ('single_choice', 'multiple_choice', 'open')),
    options             CLOB,
    hint                VARCHAR2(500),
    sort_order          NUMBER DEFAULT 0,
    open_text_enabled   NUMBER(1) DEFAULT 0,
    open_text_title     VARCHAR2(200),
    open_text_hint      VARCHAR2(500),
    section_title       VARCHAR2(200),
    is_required         NUMBER(1) DEFAULT 1
);

COMMENT ON TABLE case_questions IS '案例题目表';
COMMENT ON COLUMN case_questions.question_type IS '题型: single_choice-单选, multiple_choice-多选, open-开放式文本题';
COMMENT ON COLUMN case_questions.options IS '选项JSON, 格式: ["选项A","选项B","选项C"]';
COMMENT ON COLUMN case_questions.hint IS '作答提示，管理员维护，可为空';
COMMENT ON COLUMN case_questions.open_text_enabled IS '多选题是否启用开放式文本框: 0-否, 1-是（仅多选题有效，一道多选题仅一个）';
COMMENT ON COLUMN case_questions.open_text_title IS '多选题开放式文本框的标题栏';
COMMENT ON COLUMN case_questions.open_text_hint IS '多选题开放式文本框的录入提示';
COMMENT ON COLUMN case_questions.section_title IS '分组标题（可选）';
COMMENT ON COLUMN case_questions.is_required IS '是否必答: 1-必答, 0-非必答（可跳过）';

CREATE SEQUENCE seq_case_questions START WITH 1 INCREMENT BY 1 NOCACHE;

CREATE OR REPLACE TRIGGER trg_case_questions_id
BEFORE INSERT ON case_questions
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT seq_case_questions.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ============================================
-- 4. 任务表
-- ============================================
CREATE TABLE tasks (
    id              NUMBER PRIMARY KEY,
    name            VARCHAR2(200) NOT NULL,
    description     CLOB,
    start_time      TIMESTAMP NOT NULL,
    end_time        TIMESTAMP NOT NULL,
    status          VARCHAR2(20) DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'active', 'closed')),
    task_type       VARCHAR2(20) DEFAULT 'survey' CHECK (task_type IN ('survey', 'background')),
    sort_order      NUMBER DEFAULT 0,
    created_by      NUMBER NOT NULL REFERENCES users(id),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE tasks IS '调研任务表';
COMMENT ON COLUMN tasks.status IS '任务状态: draft-草稿, published-已发布(待开始), active-进行中, closed-已关闭';
COMMENT ON COLUMN tasks.task_type IS '任务类型: survey-普通调查, background-背景资料问卷';
COMMENT ON COLUMN tasks.sort_order IS '任务顺序，管理员可调整，学生按顺序作答';

CREATE SEQUENCE seq_tasks START WITH 1 INCREMENT BY 1 NOCACHE;

CREATE OR REPLACE TRIGGER trg_tasks_id
BEFORE INSERT ON tasks
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT seq_tasks.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ============================================
-- 5. 任务-案例关联表
-- ============================================
CREATE TABLE task_cases (
    id          NUMBER PRIMARY KEY,
    task_id     NUMBER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    case_id     NUMBER NOT NULL REFERENCES cases(id),
    sort_order  NUMBER DEFAULT 0,
    UNIQUE (task_id, case_id)
);

COMMENT ON TABLE task_cases IS '任务与案例的关联表';

CREATE SEQUENCE seq_task_cases START WITH 1 INCREMENT BY 1 NOCACHE;

CREATE OR REPLACE TRIGGER trg_task_cases_id
BEFORE INSERT ON task_cases
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT seq_task_cases.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ============================================
-- 6. 作答记录表
-- ============================================
CREATE TABLE responses (
    id              NUMBER PRIMARY KEY,
    task_id         NUMBER NOT NULL REFERENCES tasks(id),
    case_id         NUMBER NOT NULL REFERENCES cases(id),
    student_id      NUMBER NOT NULL REFERENCES users(id),
    status          VARCHAR2(10) DEFAULT 'draft' CHECK (status IN ('draft', 'submitted')),
    submitted_at    TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_response UNIQUE (task_id, case_id, student_id)
);

COMMENT ON TABLE responses IS '学生作答记录表';
COMMENT ON COLUMN responses.status IS '作答状态: draft-暂存, submitted-已提交';

CREATE SEQUENCE seq_responses START WITH 1 INCREMENT BY 1 NOCACHE;

CREATE OR REPLACE TRIGGER trg_responses_id
BEFORE INSERT ON responses
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT seq_responses.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ============================================
-- 7. 作答明细表
-- ============================================
CREATE TABLE response_details (
    id              NUMBER PRIMARY KEY,
    response_id     NUMBER NOT NULL REFERENCES responses(id) ON DELETE CASCADE,
    question_id     NUMBER NOT NULL REFERENCES case_questions(id),
    answer          CLOB
);

COMMENT ON TABLE response_details IS '学生作答明细表';
COMMENT ON COLUMN response_details.answer IS '答案内容: 单选题存选项文本, 多选题存JSON数组, 开放题存文本';

CREATE SEQUENCE seq_response_details START WITH 1 INCREMENT BY 1 NOCACHE;

CREATE OR REPLACE TRIGGER trg_response_details_id
BEFORE INSERT ON response_details
FOR EACH ROW
BEGIN
    IF :NEW.id IS NULL THEN
        SELECT seq_response_details.NEXTVAL INTO :NEW.id FROM DUAL;
    END IF;
END;
/

-- ============================================
-- 完成
-- ============================================
PROMPT 所有表创建完成！
PROMPT 请修改管理员密码后使用系统。
