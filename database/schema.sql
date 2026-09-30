-- 课程注册系统数据库结构
-- 适用：MySQL 8.0+

CREATE DATABASE IF NOT EXISTS school_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE school_db;

CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL COMMENT '当前兼容旧程序；后续迁移为密码哈希',
    role ENUM('student', 'teacher', 'admin') NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    must_change_password BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS department (
    dept_name VARCHAR(80) PRIMARY KEY,
    building VARCHAR(80),
    budget DECIMAL(14, 2) NOT NULL DEFAULT 0,
    CONSTRAINT chk_department_budget CHECK (budget >= 0)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS classroom (
    building VARCHAR(80) NOT NULL,
    room_number VARCHAR(20) NOT NULL,
    room_capacity SMALLINT UNSIGNED NOT NULL DEFAULT 10,
    PRIMARY KEY (building, room_number),
    CONSTRAINT chk_room_capacity CHECK (room_capacity > 0)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS student (
    ID VARCHAR(20) PRIMARY KEY,
    name VARCHAR(80) NOT NULL,
    dept_name VARCHAR(80) NOT NULL,
    tot_cred DECIMAL(6, 1) NOT NULL DEFAULT 0,
    entrance_year SMALLINT UNSIGNED NOT NULL,
    grade TINYINT UNSIGNED NULL COMMENT '当前年级，1-4',
    phone VARCHAR(30),
    email VARCHAR(120),
    user_id BIGINT UNSIGNED NOT NULL UNIQUE,
    CONSTRAINT fk_student_department FOREIGN KEY (dept_name)
        REFERENCES department (dept_name),
    CONSTRAINT fk_student_user FOREIGN KEY (user_id)
        REFERENCES users (user_id),
    CONSTRAINT chk_student_credit CHECK (tot_cred >= 0),
    CONSTRAINT chk_student_grade CHECK (grade IS NULL OR grade BETWEEN 1 AND 8)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS instructor (
    ID VARCHAR(20) PRIMARY KEY,
    name VARCHAR(80) NOT NULL,
    dept_name VARCHAR(80) NOT NULL,
    phone VARCHAR(30),
    email VARCHAR(120),
    user_id BIGINT UNSIGNED NOT NULL UNIQUE,
    CONSTRAINT fk_instructor_department FOREIGN KEY (dept_name)
        REFERENCES department (dept_name),
    CONSTRAINT fk_instructor_user FOREIGN KEY (user_id)
        REFERENCES users (user_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS course (
    course_id VARCHAR(20) PRIMARY KEY,
    title VARCHAR(120) NOT NULL,
    dept_name VARCHAR(80) NOT NULL,
    credits DECIMAL(3, 1) NOT NULL,
    target_grade TINYINT UNSIGNED NULL,
    target_semester ENUM('Spring', 'Summer', 'Fall', 'Winter') NULL,
    is_elective BOOLEAN NOT NULL DEFAULT FALSE,
    catalog_active BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT fk_course_department FOREIGN KEY (dept_name)
        REFERENCES department (dept_name),
    CONSTRAINT chk_course_credits CHECK (credits > 0),
    CONSTRAINT chk_course_target_grade CHECK (
        target_grade IS NULL OR target_grade BETWEEN 1 AND 8
    )
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS prereq (
    course_id VARCHAR(20) NOT NULL,
    prereq_id VARCHAR(20) NOT NULL,
    minimum_grade ENUM('A', 'B', 'C', 'D') NOT NULL DEFAULT 'D',
    PRIMARY KEY (course_id, prereq_id),
    CONSTRAINT fk_prereq_course FOREIGN KEY (course_id)
        REFERENCES course (course_id),
    CONSTRAINT fk_prereq_required_course FOREIGN KEY (prereq_id)
        REFERENCES course (course_id),
    CONSTRAINT chk_prereq_not_self CHECK (course_id <> prereq_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS registration_period (
    period_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    semester ENUM('Spring', 'Summer', 'Fall', 'Winter') NOT NULL,
    year SMALLINT UNSIGNED NOT NULL,
    status ENUM('DRAFT', 'OPEN', 'CLOSED', 'PROCESSED') NOT NULL DEFAULT 'DRAFT',
    opens_at DATETIME NULL,
    closes_at DATETIME NULL,
    closed_by BIGINT UNSIGNED NULL,
    closed_at DATETIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_registration_term (semester, year),
    CONSTRAINT fk_registration_closed_by FOREIGN KEY (closed_by)
        REFERENCES users (user_id),
    CONSTRAINT chk_registration_dates CHECK (
        closes_at IS NULL OR opens_at IS NULL OR closes_at > opens_at
    )
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS section (
    course_id VARCHAR(20) NOT NULL,
    sec_id VARCHAR(20) NOT NULL,
    semester ENUM('Spring', 'Summer', 'Fall', 'Winter') NOT NULL,
    year SMALLINT UNSIGNED NOT NULL,
    capacity TINYINT UNSIGNED NOT NULL DEFAULT 10,
    building VARCHAR(80) NULL,
    room_number VARCHAR(20) NULL,
    day_of_week TINYINT UNSIGNED NULL COMMENT '1=星期一，7=星期日',
    start_period TINYINT UNSIGNED NULL,
    end_period TINYINT UNSIGNED NULL,
    schedule VARCHAR(120) NULL,
    status ENUM('PLANNED', 'OPEN', 'CANCELLED', 'FINALIZED') NOT NULL DEFAULT 'PLANNED',
    cancellation_reason VARCHAR(255) NULL,
    PRIMARY KEY (course_id, sec_id, semester, year),
    CONSTRAINT fk_section_course FOREIGN KEY (course_id)
        REFERENCES course (course_id),
    CONSTRAINT fk_section_classroom FOREIGN KEY (building, room_number)
        REFERENCES classroom (building, room_number),
    CONSTRAINT chk_section_capacity CHECK (capacity BETWEEN 1 AND 10),
    CONSTRAINT chk_section_day CHECK (day_of_week IS NULL OR day_of_week BETWEEN 1 AND 7),
    CONSTRAINT chk_section_period CHECK (
        (start_period IS NULL AND end_period IS NULL)
        OR (start_period > 0 AND end_period >= start_period)
    )
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS instructor_qualification (
    teacher_id VARCHAR(20) NOT NULL,
    course_id VARCHAR(20) NOT NULL,
    approved_by BIGINT UNSIGNED NULL,
    approved_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (teacher_id, course_id),
    CONSTRAINT fk_qualification_teacher FOREIGN KEY (teacher_id)
        REFERENCES instructor (ID),
    CONSTRAINT fk_qualification_course FOREIGN KEY (course_id)
        REFERENCES course (course_id),
    CONSTRAINT fk_qualification_approver FOREIGN KEY (approved_by)
        REFERENCES users (user_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS teaching_application (
    application_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    teacher_id VARCHAR(20) NOT NULL,
    course_id VARCHAR(20) NOT NULL,
    sec_id VARCHAR(20) NOT NULL,
    semester ENUM('Spring', 'Summer', 'Fall', 'Winter') NOT NULL,
    year SMALLINT UNSIGNED NOT NULL,
    status ENUM('PENDING', 'APPROVED', 'REJECTED', 'WITHDRAWN') NOT NULL DEFAULT 'PENDING',
    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_by BIGINT UNSIGNED NULL,
    reviewed_at DATETIME NULL,
    UNIQUE KEY uq_teacher_application (
        teacher_id, course_id, sec_id, semester, year
    ),
    CONSTRAINT fk_application_teacher FOREIGN KEY (teacher_id)
        REFERENCES instructor (ID),
    CONSTRAINT fk_application_section FOREIGN KEY (course_id, sec_id, semester, year)
        REFERENCES section (course_id, sec_id, semester, year),
    CONSTRAINT fk_application_reviewer FOREIGN KEY (reviewed_by)
        REFERENCES users (user_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS teaches (
    teacher_id VARCHAR(20) NOT NULL,
    course_id VARCHAR(20) NOT NULL,
    sec_id VARCHAR(20) NOT NULL,
    semester ENUM('Spring', 'Summer', 'Fall', 'Winter') NOT NULL,
    year SMALLINT UNSIGNED NOT NULL,
    assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (course_id, sec_id, semester, year),
    KEY idx_teaches_teacher (teacher_id),
    CONSTRAINT fk_teaches_teacher FOREIGN KEY (teacher_id)
        REFERENCES instructor (ID),
    CONSTRAINT fk_teaches_section FOREIGN KEY (course_id, sec_id, semester, year)
        REFERENCES section (course_id, sec_id, semester, year)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS course_preference (
    preference_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    period_id BIGINT UNSIGNED NOT NULL,
    student_id VARCHAR(20) NOT NULL,
    course_id VARCHAR(20) NOT NULL,
    sec_id VARCHAR(20) NOT NULL,
    semester ENUM('Spring', 'Summer', 'Fall', 'Winter') NOT NULL,
    year SMALLINT UNSIGNED NOT NULL,
    choice_type ENUM('PRIMARY', 'ALTERNATE') NOT NULL,
    priority TINYINT UNSIGNED NOT NULL,
    status ENUM('DRAFT', 'SUBMITTED', 'ALLOCATED', 'REJECTED', 'CANCELLED')
        NOT NULL DEFAULT 'DRAFT',
    rejection_reason VARCHAR(255) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_preference_priority (period_id, student_id, choice_type, priority),
    UNIQUE KEY uq_preference_course (period_id, student_id, course_id),
    CONSTRAINT fk_preference_period FOREIGN KEY (period_id)
        REFERENCES registration_period (period_id),
    CONSTRAINT fk_preference_student FOREIGN KEY (student_id)
        REFERENCES student (ID),
    CONSTRAINT fk_preference_section FOREIGN KEY (course_id, sec_id, semester, year)
        REFERENCES section (course_id, sec_id, semester, year),
    CONSTRAINT chk_preference_priority CHECK (
        (choice_type = 'PRIMARY' AND priority BETWEEN 1 AND 4)
        OR (choice_type = 'ALTERNATE' AND priority BETWEEN 1 AND 2)
    )
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS takes (
    ID VARCHAR(20) NOT NULL,
    course_id VARCHAR(20) NOT NULL,
    sec_id VARCHAR(20) NOT NULL,
    semester ENUM('Spring', 'Summer', 'Fall', 'Winter') NOT NULL,
    year SMALLINT UNSIGNED NOT NULL,
    status ENUM('selected', 'completed', 'dropped', 'cancelled') NOT NULL DEFAULT 'selected',
    score DECIMAL(5, 2) NULL,
    regular_score DECIMAL(5, 2) NULL,
    final_score DECIMAL(5, 2) NULL,
    letter_grade ENUM('A', 'B', 'C', 'D', 'F', 'I') NULL,
    select_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source ENUM('PRIMARY', 'ALTERNATE', 'MANUAL', 'LEGACY') NOT NULL DEFAULT 'MANUAL',
    PRIMARY KEY (ID, course_id, sec_id, semester, year),
    KEY idx_takes_section (course_id, sec_id, semester, year, status),
    CONSTRAINT fk_takes_student FOREIGN KEY (ID)
        REFERENCES student (ID),
    CONSTRAINT fk_takes_section FOREIGN KEY (course_id, sec_id, semester, year)
        REFERENCES section (course_id, sec_id, semester, year),
    CONSTRAINT chk_takes_scores CHECK (
        (score IS NULL OR score BETWEEN 0 AND 100)
        AND (regular_score IS NULL OR regular_score BETWEEN 0 AND 100)
        AND (final_score IS NULL OR final_score BETWEEN 0 AND 100)
    )
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS billing_job (
    billing_job_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    student_id VARCHAR(20) NOT NULL,
    period_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(10, 2) NOT NULL DEFAULT 0,
    status ENUM('PENDING', 'SUCCEEDED', 'FAILED', 'RETRYING') NOT NULL DEFAULT 'PENDING',
    retry_count TINYINT UNSIGNED NOT NULL DEFAULT 0,
    next_retry_at DATETIME NULL,
    external_reference VARCHAR(100) NULL,
    last_error VARCHAR(500) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_billing_student_period (student_id, period_id),
    CONSTRAINT fk_billing_student FOREIGN KEY (student_id)
        REFERENCES student (ID),
    CONSTRAINT fk_billing_period FOREIGN KEY (period_id)
        REFERENCES registration_period (period_id),
    CONSTRAINT chk_billing_amount CHECK (amount >= 0)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NULL,
    action VARCHAR(80) NOT NULL,
    entity_type VARCHAR(80) NOT NULL,
    entity_id VARCHAR(160) NULL,
    details JSON NULL,
    ip_address VARCHAR(45) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_audit_created_at (created_at),
    KEY idx_audit_user (user_id),
    CONSTRAINT fk_audit_user FOREIGN KEY (user_id)
        REFERENCES users (user_id)
) ENGINE=InnoDB;

CREATE OR REPLACE VIEW v_student_schedule AS
SELECT
    t.ID AS student_id,
    c.title AS course_name,
    s.course_id,
    s.sec_id AS section_id,
    CASE
        WHEN s.day_of_week IS NOT NULL
             AND s.start_period IS NOT NULL
             AND s.end_period IS NOT NULL
        THEN CONCAT(
            '星期', ELT(s.day_of_week, '一', '二', '三', '四', '五', '六', '日'),
            ' ', s.start_period, '-', s.end_period, '节'
        )
        ELSE s.schedule
    END AS class_time,
    s.building,
    s.room_number AS room,
    i.name AS instructor_name,
    s.semester,
    s.year
FROM takes t
JOIN section s
  ON t.course_id = s.course_id
 AND t.sec_id = s.sec_id
 AND t.semester = s.semester
 AND t.year = s.year
JOIN course c ON s.course_id = c.course_id
LEFT JOIN teaches te
  ON s.course_id = te.course_id
 AND s.sec_id = te.sec_id
 AND s.semester = te.semester
 AND s.year = te.year
LEFT JOIN instructor i ON te.teacher_id = i.ID
WHERE t.status = 'selected';

CREATE OR REPLACE VIEW v_student_transcript AS
SELECT
    s.ID AS student_id,
    s.name AS student_name,
    c.course_id,
    c.title AS course_name,
    c.credits AS course_credits,
    t.score AS grade,
    t.letter_grade,
    t.regular_score,
    t.final_score,
    t.semester,
    t.year
FROM takes t
JOIN student s ON t.ID = s.ID
JOIN course c ON t.course_id = c.course_id
WHERE t.status IN ('selected', 'completed');

DROP TRIGGER IF EXISTS trg_takes_capacity_insert;
DROP TRIGGER IF EXISTS trg_takes_capacity_update;

DELIMITER $$

CREATE TRIGGER trg_takes_capacity_insert
BEFORE INSERT ON takes
FOR EACH ROW
BEGIN
    DECLARE maximum_capacity INT;
    DECLARE enrolled_count INT;

    IF NEW.status = 'selected' THEN
        SELECT capacity INTO maximum_capacity
        FROM section
        WHERE course_id = NEW.course_id
          AND sec_id = NEW.sec_id
          AND semester = NEW.semester
          AND year = NEW.year
        FOR UPDATE;

        SELECT COUNT(*) INTO enrolled_count
        FROM takes
        WHERE course_id = NEW.course_id
          AND sec_id = NEW.sec_id
          AND semester = NEW.semester
          AND year = NEW.year
          AND status = 'selected';

        IF enrolled_count >= maximum_capacity THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'capacity exceeded: section is full';
        END IF;
    END IF;
END$$

CREATE TRIGGER trg_takes_capacity_update
BEFORE UPDATE ON takes
FOR EACH ROW
BEGIN
    DECLARE maximum_capacity INT;
    DECLARE enrolled_count INT;

    IF OLD.status <> 'selected' AND NEW.status = 'selected' THEN
        SELECT capacity INTO maximum_capacity
        FROM section
        WHERE course_id = NEW.course_id
          AND sec_id = NEW.sec_id
          AND semester = NEW.semester
          AND year = NEW.year
        FOR UPDATE;

        SELECT COUNT(*) INTO enrolled_count
        FROM takes
        WHERE course_id = NEW.course_id
          AND sec_id = NEW.sec_id
          AND semester = NEW.semester
          AND year = NEW.year
          AND status = 'selected';

        IF enrolled_count >= maximum_capacity THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'capacity exceeded: section is full';
        END IF;
    END IF;
END$$

DELIMITER ;
