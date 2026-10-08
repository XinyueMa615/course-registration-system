-- 仅供已经执行过旧版 02_registration.sql 的数据库使用，执行一次。
-- 两列原来未被应用读写；执行前请确认没有人工录入的身份号码。
-- 新装数据库直接运行最新版 02_registration.sql，不要再运行本迁移。
USE course_registration_v2;

ALTER TABLE student_profile
  RENAME COLUMN identity_number_encrypted TO ssn_encrypted;

ALTER TABLE professor_profile
  RENAME COLUMN identity_number_encrypted TO ssn_encrypted;
