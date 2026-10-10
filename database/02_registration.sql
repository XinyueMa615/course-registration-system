-- 新课程注册业务库。只保存本系统可修改的数据；课程/教学班由目录库只读提供。
-- MySQL 8.0.16+，InnoDB。业务服务必须在事务中完成容量、冲突与权限检查。
SET NAMES utf8mb4;
CREATE DATABASE IF NOT EXISTS course_registration_v2
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE course_registration_v2;

CREATE TABLE IF NOT EXISTS user_account (
  user_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(60) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL COMMENT '仅存 PBKDF2-SHA256 密码哈希，不保存明文密码',
  must_change_password BOOLEAN NOT NULL DEFAULT FALSE COMMENT '临时密码首次登录后必须修改',
  role ENUM('STUDENT','PROFESSOR','REGISTRAR') NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS auth_session (
  session_id CHAR(43) PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  expires_at DATETIME NOT NULL,
  revoked_at DATETIME NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_auth_session_user (user_id, revoked_at),
  CONSTRAINT fk_auth_session_user FOREIGN KEY (user_id) REFERENCES user_account(user_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS student_profile (
  student_id VARCHAR(20) PRIMARY KEY,
  user_id BIGINT UNSIGNED NULL UNIQUE,
  full_name VARCHAR(100) NOT NULL,
  date_of_birth DATE NOT NULL,
  ssn_encrypted VARBINARY(512) NULL COMMENT '预留加密 SSN；演示可留空，不得保存明文或真实号码',
  status ENUM('ACTIVE','INACTIVE','GRADUATED') NOT NULL DEFAULT 'ACTIVE',
  graduation_date DATE NULL,
  CONSTRAINT fk_v2_student_user FOREIGN KEY (user_id) REFERENCES user_account(user_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS professor_profile (
  professor_id VARCHAR(20) PRIMARY KEY,
  user_id BIGINT UNSIGNED NULL UNIQUE,
  full_name VARCHAR(100) NOT NULL,
  date_of_birth DATE NOT NULL,
  ssn_encrypted VARBINARY(512) NULL COMMENT '预留加密 SSN；演示可留空，不得保存明文或真实号码',
  status ENUM('ACTIVE','INACTIVE') NOT NULL DEFAULT 'ACTIVE',
  department_id VARCHAR(20) NOT NULL COMMENT '引用只读目录库 department_id，由业务服务核对',
  CONSTRAINT fk_v2_professor_user FOREIGN KEY (user_id) REFERENCES user_account(user_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS academic_term (
  term_code VARCHAR(8) PRIMARY KEY,
  year SMALLINT UNSIGNED NOT NULL,
  semester ENUM('SPRING','SUMMER','FALL','WINTER') NOT NULL,
  registration_opens_at DATETIME NOT NULL,
  registration_closes_at DATETIME NOT NULL,
  status ENUM('DRAFT','OPEN','CLOSING','CLOSED') NOT NULL DEFAULT 'DRAFT',
  tuition_per_credit DECIMAL(10,2) NOT NULL DEFAULT 0 COMMENT '演示计费配置；题目未规定费率',
  closed_at DATETIME NULL,
  completed_at DATETIME NULL COMMENT '教务确认教学结束的时间；与选课关闭时间不同',
  closed_by BIGINT UNSIGNED NULL,
  UNIQUE KEY uq_v2_term_year_semester (year, semester),
  CONSTRAINT fk_v2_term_closer FOREIGN KEY (closed_by) REFERENCES user_account(user_id),
  CONSTRAINT chk_v2_term_dates CHECK (registration_closes_at > registration_opens_at),
  CONSTRAINT chk_v2_term_tuition CHECK (tuition_per_credit >= 0)
) ENGINE=InnoDB;

-- 外部目录的教学班 ID 在此仅作引用，不跨库建立外键。
-- 服务首次读取目录时复制 capacity，并在选课事务中锁住本行。
CREATE TABLE IF NOT EXISTS offering_registration_state (
  offering_id VARCHAR(40) PRIMARY KEY,
  term_code VARCHAR(8) NOT NULL,
  capacity TINYINT UNSIGNED NOT NULL,
  enrolled_count TINYINT UNSIGNED NOT NULL DEFAULT 0,
  status ENUM('OPEN','COMMITTED','CANCELLED') NOT NULL DEFAULT 'OPEN',
  cancellation_reason ENUM('NO_PROFESSOR','TOO_FEW_STUDENTS') NULL,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_v2_offering_id_term (offering_id, term_code),
  KEY idx_v2_offering_term (term_code, status),
  CONSTRAINT fk_v2_offering_term FOREIGN KEY (term_code) REFERENCES academic_term(term_code),
  CONSTRAINT chk_v2_offering_capacity CHECK (capacity BETWEEN 3 AND 10),
  CONSTRAINT chk_v2_offering_count CHECK (enrolled_count <= capacity)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS professor_qualification (
  professor_id VARCHAR(20) NOT NULL,
  course_id VARCHAR(20) NOT NULL COMMENT '只读目录库中的课程 ID',
  PRIMARY KEY (professor_id, course_id),
  CONSTRAINT fk_v2_qualification_professor FOREIGN KEY (professor_id)
    REFERENCES professor_profile(professor_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS teaching_assignment (
  offering_id VARCHAR(40) PRIMARY KEY,
  professor_id VARCHAR(20) NOT NULL,
  assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_v2_assignment_professor (professor_id),
  CONSTRAINT fk_v2_assignment_offering FOREIGN KEY (offering_id)
    REFERENCES offering_registration_state(offering_id),
  CONSTRAINT fk_v2_assignment_professor FOREIGN KEY (professor_id)
    REFERENCES professor_profile(professor_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS student_schedule (
  schedule_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  student_id VARCHAR(20) NOT NULL,
  term_code VARCHAR(8) NOT NULL,
  status ENUM('DRAFT','SUBMITTED','FINALIZED','DELETED') NOT NULL DEFAULT 'DRAFT',
  submitted_at DATETIME NULL,
  finalized_at DATETIME NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_v2_student_term (student_id, term_code),
  UNIQUE KEY uq_v2_schedule_id_term (schedule_id, term_code),
  KEY idx_v2_schedule_term (term_code, status),
  CONSTRAINT fk_v2_schedule_student FOREIGN KEY (student_id)
    REFERENCES student_profile(student_id),
  CONSTRAINT fk_v2_schedule_term FOREIGN KEY (term_code)
    REFERENCES academic_term(term_code)
) ENGINE=InnoDB;

-- 保存草稿只写本表；提交成功才生成 enrollment 并占用名额。
CREATE TABLE IF NOT EXISTS schedule_choice (
  choice_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  schedule_id BIGINT UNSIGNED NOT NULL,
  offering_id VARCHAR(40) NOT NULL,
  term_code VARCHAR(8) NOT NULL,
  choice_type ENUM('PRIMARY','ALTERNATE') NOT NULL,
  priority TINYINT UNSIGNED NOT NULL,
  status ENUM('SELECTED','ENROLLED','CANCELLED') NOT NULL DEFAULT 'SELECTED',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_v2_choice_position (schedule_id, choice_type, priority),
  UNIQUE KEY uq_v2_choice_offering (schedule_id, offering_id),
  UNIQUE KEY uq_v2_choice_schedule_offering (schedule_id, choice_id, offering_id),
  CONSTRAINT fk_v2_choice_schedule FOREIGN KEY (schedule_id, term_code)
    REFERENCES student_schedule(schedule_id, term_code),
  CONSTRAINT fk_v2_choice_offering FOREIGN KEY (offering_id, term_code)
    REFERENCES offering_registration_state(offering_id, term_code),
  CONSTRAINT chk_v2_choice_priority CHECK (
    (choice_type = 'PRIMARY' AND priority BETWEEN 1 AND 4)
    OR (choice_type = 'ALTERNATE' AND priority BETWEEN 1 AND 2)
  )
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS enrollment (
  enrollment_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  schedule_id BIGINT UNSIGNED NOT NULL,
  choice_id BIGINT UNSIGNED NOT NULL,
  offering_id VARCHAR(40) NOT NULL,
  status ENUM('ENROLLED','COMMITTED','DROPPED','CANCELLED','COMPLETED') NOT NULL,
  letter_grade ENUM('A','B','C','D','F','I') NULL,
  graded_by VARCHAR(20) NULL,
  graded_at DATETIME NULL,
  enrolled_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_v2_enrollment_choice (choice_id),
  UNIQUE KEY uq_v2_enrollment_schedule_offering (schedule_id, offering_id),
  KEY idx_v2_enrollment_offering_status (offering_id, status),
  CONSTRAINT fk_v2_enrollment_schedule FOREIGN KEY (schedule_id)
    REFERENCES student_schedule(schedule_id),
  CONSTRAINT fk_v2_enrollment_choice_schedule FOREIGN KEY (schedule_id, choice_id, offering_id)
    REFERENCES schedule_choice(schedule_id, choice_id, offering_id),
  CONSTRAINT fk_v2_enrollment_offering FOREIGN KEY (offering_id)
    REFERENCES offering_registration_state(offering_id),
  CONSTRAINT fk_v2_enrollment_grader FOREIGN KEY (graded_by)
    REFERENCES professor_profile(professor_id),
  CONSTRAINT chk_v2_grade_context CHECK (letter_grade IS NULL OR graded_by IS NOT NULL)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS grade_change_log (
  grade_change_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  enrollment_id BIGINT UNSIGNED NOT NULL,
  professor_id VARCHAR(20) NOT NULL,
  old_grade ENUM('A','B','C','D','F','I') NULL,
  new_grade ENUM('A','B','C','D','F','I') NOT NULL,
  changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_v2_grade_log_enrollment FOREIGN KEY (enrollment_id)
    REFERENCES enrollment(enrollment_id),
  CONSTRAINT fk_v2_grade_log_professor FOREIGN KEY (professor_id)
    REFERENCES professor_profile(professor_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS registration_close_run (
  close_run_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  term_code VARCHAR(8) NOT NULL,
  started_by BIGINT UNSIGNED NOT NULL,
  status ENUM('RUNNING','SUCCEEDED','FAILED') NOT NULL,
  started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at DATETIME NULL,
  error_message VARCHAR(500) NULL,
  KEY idx_v2_close_term (term_code, started_at),
  CONSTRAINT fk_v2_close_term FOREIGN KEY (term_code) REFERENCES academic_term(term_code),
  CONSTRAINT fk_v2_close_user FOREIGN KEY (started_by) REFERENCES user_account(user_id)
) ENGINE=InnoDB;

-- 一名学生一个学期发一笔计费事务；最终课表作为 JSON 快照发送。
-- 真实计费系统不可用时，重试同一 idempotency_key，防止重复账单。
CREATE TABLE IF NOT EXISTS billing_outbox (
  billing_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  schedule_id BIGINT UNSIGNED NOT NULL UNIQUE,
  idempotency_key VARCHAR(100) NOT NULL UNIQUE,
  amount DECIMAL(10,2) NOT NULL,
  final_schedule JSON NOT NULL,
  status ENUM('PENDING','RETRYING','SUCCEEDED') NOT NULL DEFAULT 'PENDING',
  attempts INT UNSIGNED NOT NULL DEFAULT 0,
  next_attempt_at DATETIME NULL,
  last_error VARCHAR(500) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  sent_at DATETIME NULL,
  CONSTRAINT fk_v2_billing_schedule FOREIGN KEY (schedule_id)
    REFERENCES student_schedule(schedule_id),
  CONSTRAINT chk_v2_billing_amount CHECK (amount >= 0)
) ENGINE=InnoDB;

-- 本地模拟计费系统的“收件箱”。与 outbox 分开提交，演示网络确认丢失后的幂等重试。
-- 真实部署时由外部计费服务保存此表；本应用只需保留 billing_outbox。
CREATE TABLE IF NOT EXISTS mock_billing_receipt (
  idempotency_key VARCHAR(100) PRIMARY KEY,
  schedule_id BIGINT UNSIGNED NOT NULL UNIQUE,
  amount DECIMAL(10,2) NOT NULL,
  payload_sha256 CHAR(64) NOT NULL,
  final_schedule JSON NOT NULL,
  received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT chk_v2_mock_billing_amount CHECK (amount >= 0)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS audit_log (
  audit_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NULL,
  action VARCHAR(80) NOT NULL,
  entity_type VARCHAR(80) NOT NULL,
  entity_id VARCHAR(80) NOT NULL,
  occurred_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_v2_audit_time (occurred_at),
  CONSTRAINT fk_v2_audit_user FOREIGN KEY (user_id) REFERENCES user_account(user_id)
) ENGINE=InnoDB;

-- 成绩单展示最终有效课程；未录入成绩的课程保留空成绩。
CREATE OR REPLACE VIEW v_report_card AS
SELECT s.student_id, s.term_code, e.offering_id, e.letter_grade, e.graded_at
FROM enrollment e
JOIN student_schedule s ON s.schedule_id = e.schedule_id
WHERE s.status = 'FINALIZED' AND e.status IN ('COMMITTED','COMPLETED');
