-- 第五版本：会话撤销和完整成绩单。已有数据库执行一次；新装数据库不需运行。
SET NAMES utf8mb4;
USE course_registration_v2;

CREATE TABLE IF NOT EXISTS auth_session (
  session_id CHAR(43) PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  expires_at DATETIME NOT NULL,
  revoked_at DATETIME NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_auth_session_user (user_id, revoked_at),
  CONSTRAINT fk_auth_session_user FOREIGN KEY (user_id) REFERENCES user_account(user_id)
) ENGINE=InnoDB;

CREATE OR REPLACE VIEW v_report_card AS
SELECT s.student_id, s.term_code, e.offering_id, e.letter_grade, e.graded_at
FROM enrollment e
JOIN student_schedule s ON s.schedule_id = e.schedule_id
WHERE s.status = 'FINALIZED' AND e.status IN ('COMMITTED','COMPLETED');
