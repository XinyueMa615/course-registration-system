-- 已有数据库执行一次；只增加可空列，不改变已开放的选课学期。
-- CLOSED 仅表示选课截止，不能自动视为整个学期已完成。
SET NAMES utf8mb4;
USE course_registration_v2;

ALTER TABLE academic_term
  ADD COLUMN completed_at DATETIME NULL
    COMMENT '教务确认教学结束的时间；与选课关闭时间不同'
    AFTER closed_at;
