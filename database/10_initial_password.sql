-- 已有数据库只需执行一次；新装数据库的 02_registration.sql 已包含本字段。
USE course_registration_v2;
ALTER TABLE user_account
  ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT FALSE
  COMMENT '临时密码首次登录后必须修改';
