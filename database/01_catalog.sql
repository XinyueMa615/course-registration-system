-- 课程设计题目的“旧课程目录”模拟库。真实部署时应替换为旧系统只读接口。
-- MySQL 8.0.16+；本文件只初始化演示目录，不由注册系统运行时执行写入。
CREATE DATABASE IF NOT EXISTS course_catalog_demo
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE course_catalog_demo;

CREATE TABLE IF NOT EXISTS department (
  department_id VARCHAR(20) PRIMARY KEY,
  name VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS course (
  course_id VARCHAR(20) PRIMARY KEY,
  title VARCHAR(120) NOT NULL,
  department_id VARCHAR(20) NOT NULL,
  credits DECIMAL(3,1) NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  CONSTRAINT fk_catalog_course_department FOREIGN KEY (department_id)
    REFERENCES department(department_id),
  CONSTRAINT chk_catalog_course_credits CHECK (credits > 0)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS course_prerequisite (
  course_id VARCHAR(20) NOT NULL,
  prerequisite_course_id VARCHAR(20) NOT NULL,
  minimum_grade ENUM('A','B','C','D') NOT NULL DEFAULT 'D',
  PRIMARY KEY (course_id, prerequisite_course_id),
  CONSTRAINT fk_catalog_prerequisite_course FOREIGN KEY (course_id)
    REFERENCES course(course_id),
  CONSTRAINT fk_catalog_prerequisite_required FOREIGN KEY (prerequisite_course_id)
    REFERENCES course(course_id),
  CONSTRAINT chk_catalog_not_self_prerequisite CHECK (course_id <> prerequisite_course_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS course_offering (
  offering_id VARCHAR(40) PRIMARY KEY,
  course_id VARCHAR(20) NOT NULL,
  term_code VARCHAR(8) NOT NULL COMMENT '如 2026FA；与注册库学期代码对应',
  section_code VARCHAR(20) NOT NULL,
  capacity TINYINT UNSIGNED NOT NULL DEFAULT 10,
  UNIQUE KEY uq_catalog_course_section (course_id, term_code, section_code),
  KEY idx_catalog_offering_term (term_code, course_id),
  CONSTRAINT fk_catalog_offering_course FOREIGN KEY (course_id)
    REFERENCES course(course_id),
  CONSTRAINT chk_catalog_capacity CHECK (capacity BETWEEN 3 AND 10)
) ENGINE=InnoDB;

-- 一门课可以每周上多次；将每一次上课时间分别保存，才能正确检查时间冲突。
CREATE TABLE IF NOT EXISTS offering_meeting (
  meeting_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  offering_id VARCHAR(40) NOT NULL,
  weekday TINYINT UNSIGNED NOT NULL COMMENT '1=周一，7=周日',
  start_period TINYINT UNSIGNED NOT NULL,
  end_period TINYINT UNSIGNED NOT NULL,
  building VARCHAR(80),
  room_number VARCHAR(20),
  KEY idx_catalog_meeting_offering (offering_id),
  CONSTRAINT fk_catalog_meeting_offering FOREIGN KEY (offering_id)
    REFERENCES course_offering(offering_id),
  CONSTRAINT chk_catalog_weekday CHECK (weekday BETWEEN 1 AND 7),
  CONSTRAINT chk_catalog_period CHECK (start_period > 0 AND end_period >= start_period)
) ENGINE=InnoDB;
