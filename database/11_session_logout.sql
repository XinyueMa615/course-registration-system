-- 已有数据库只需执行一次；新装数据库的 02_registration.sql 已包含本字段。
-- 每次退出登录时递增版本号，使该账号之前签发的会话令牌立即失效。
USE course_registration_v2;
ALTER TABLE user_account
  ADD COLUMN session_version INT UNSIGNED NOT NULL DEFAULT 0
  COMMENT '退出登录时递增，使旧会话令牌立即失效'
  AFTER must_change_password;
