-- 已有数据库仅执行一次；先确认 academic_term 尚无 grade_entry_closed_at 列。
-- 若 .env 的 DB_NAME 不是 course_registration_v2，请先把下一行 USE 改为实际业务库名。
SET NAMES utf8mb4;
USE course_registration_v2;

ALTER TABLE academic_term
  ADD COLUMN grade_entry_closed_at DATETIME NULL
    COMMENT '教务关闭本学期教师录分的时间；关闭后名单和成绩仍可查看'
    AFTER completed_at;
