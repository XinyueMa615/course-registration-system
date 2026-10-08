-- 已经运行过 02_registration.sql 的现有数据库只需执行本迁移一次。
-- 幂等；不会修改现有账单或学生课表。
USE course_registration_v2;
CREATE TABLE IF NOT EXISTS mock_billing_receipt (
  idempotency_key VARCHAR(100) PRIMARY KEY,
  schedule_id BIGINT UNSIGNED NOT NULL UNIQUE,
  amount DECIMAL(10,2) NOT NULL,
  payload_sha256 CHAR(64) NOT NULL,
  final_schedule JSON NOT NULL,
  received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT chk_v2_mock_billing_amount CHECK (amount >= 0)
) ENGINE=InnoDB;
