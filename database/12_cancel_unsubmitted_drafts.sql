-- 第五版本补充：选课截止时明确取消仍未提交的草稿课表。
-- 已有数据库只执行一次；全新数据库无需执行（02_registration.sql 已包含这些字段）。
SET NAMES utf8mb4;
USE course_registration_v2;

ALTER TABLE student_schedule
  MODIFY COLUMN status ENUM('DRAFT','SUBMITTED','FINALIZED','CANCELLED','DELETED')
    NOT NULL DEFAULT 'DRAFT',
  ADD COLUMN cancelled_at DATETIME NULL
    COMMENT '未提交草稿因选课截止而取消的时间' AFTER finalized_at;

-- 修复升级前已经关闭学期里遗留的不可编辑草稿；开放学期草稿不受影响。
UPDATE schedule_choice c
JOIN student_schedule s ON s.schedule_id = c.schedule_id
JOIN academic_term t ON t.term_code = s.term_code
SET c.status = 'CANCELLED'
WHERE s.status = 'DRAFT' AND t.status = 'CLOSED' AND c.status = 'SELECTED';

UPDATE student_schedule s
JOIN academic_term t ON t.term_code = s.term_code
SET s.status = 'CANCELLED', s.cancelled_at = COALESCE(t.closed_at, NOW())
WHERE s.status = 'DRAFT' AND t.status = 'CLOSED';
