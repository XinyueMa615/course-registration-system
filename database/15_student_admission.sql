-- 第七版补充：学生所属院系与入学学期。只执行一次；全新数据库无需执行。
-- 执行前备份业务库，并将 USE 改成当前 .env 的 DB_NAME。
-- 不猜测旧学生的院系或入学学期；由教务核对后补录。
SET NAMES utf8mb4;
USE course_registration_v2;

ALTER TABLE student_profile
  ADD COLUMN department_id VARCHAR(20) NULL
    COMMENT '引用只读目录库 department_id；旧档案可待教务补录' AFTER graduation_date,
  ADD COLUMN admission_term_code VARCHAR(8) NULL
    COMMENT '学生入学学期；旧档案不从首次课表猜测' AFTER department_id,
  ADD KEY idx_student_admission_term (admission_term_code),
  ADD CONSTRAINT fk_student_admission_term FOREIGN KEY (admission_term_code)
    REFERENCES academic_term(term_code);
