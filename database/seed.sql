-- 课程注册系统演示数据
-- 必须先执行 schema.sql。下面账号仅用于本机开发，首次登录后应修改密码。

USE school_db;

INSERT INTO department (dept_name, building, budget) VALUES
    ('计算机学院', '信息楼', 800000.00),
    ('数学学院', '理学楼', 500000.00),
    ('人文学院', '文科楼', 350000.00)
ON DUPLICATE KEY UPDATE
    building = VALUES(building),
    budget = VALUES(budget);

INSERT INTO classroom (building, room_number, room_capacity) VALUES
    ('信息楼', '101', 10),
    ('信息楼', '201', 10),
    ('理学楼', '101', 10),
    ('文科楼', '301', 10)
ON DUPLICATE KEY UPDATE room_capacity = VALUES(room_capacity);

INSERT INTO users (username, password, role, must_change_password) VALUES
    ('admin', 'DevOnly_2026!', 'admin', TRUE),
    ('teacher_zhang', 'DevOnly_2026!', 'teacher', TRUE),
    ('teacher_li', 'DevOnly_2026!', 'teacher', TRUE),
    ('student_zhang', 'DevOnly_2026!', 'student', TRUE),
    ('student_wang', 'DevOnly_2026!', 'student', TRUE)
ON DUPLICATE KEY UPDATE
    role = VALUES(role),
    is_active = TRUE;

INSERT INTO student
    (ID, name, dept_name, tot_cred, entrance_year, grade, phone, email, user_id)
VALUES
    ('S001', '张同学', '计算机学院', 4.0, 2025, 2, '13800000001',
     'student.zhang@example.edu',
     (SELECT user_id FROM users WHERE username = 'student_zhang')),
    ('S002', '王同学', '计算机学院', 4.0, 2025, 2, '13800000002',
     'student.wang@example.edu',
     (SELECT user_id FROM users WHERE username = 'student_wang'))
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    dept_name = VALUES(dept_name),
    user_id = VALUES(user_id);

INSERT INTO instructor
    (ID, name, dept_name, phone, email, user_id)
VALUES
    ('T001', '张老师', '计算机学院', '13900000001',
     'teacher.zhang@example.edu',
     (SELECT user_id FROM users WHERE username = 'teacher_zhang')),
    ('T002', '李老师', '数学学院', '13900000002',
     'teacher.li@example.edu',
     (SELECT user_id FROM users WHERE username = 'teacher_li'))
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    dept_name = VALUES(dept_name),
    user_id = VALUES(user_id);

INSERT INTO course
    (course_id, title, dept_name, credits, target_grade, target_semester, is_elective)
VALUES
    ('CS100', '程序设计基础', '计算机学院', 4.0, 1, 'Spring', FALSE),
    ('CS102', '数据结构', '计算机学院', 4.0, 2, 'Fall', FALSE),
    ('CS201', '软件工程', '计算机学院', 3.0, 2, 'Fall', FALSE),
    ('CS202', '数据库系统', '计算机学院', 3.0, 2, 'Fall', FALSE),
    ('MA101', '高等数学', '数学学院', 4.0, 1, 'Fall', FALSE),
    ('GE101', '学术写作', '人文学院', 2.0, NULL, NULL, TRUE),
    ('GE102', '艺术鉴赏', '人文学院', 2.0, NULL, NULL, TRUE),
    ('GE103', '大学生职业发展', '人文学院', 2.0, NULL, NULL, TRUE)
ON DUPLICATE KEY UPDATE
    title = VALUES(title),
    dept_name = VALUES(dept_name),
    credits = VALUES(credits),
    target_grade = VALUES(target_grade),
    target_semester = VALUES(target_semester),
    is_elective = VALUES(is_elective);

INSERT INTO prereq (course_id, prereq_id, minimum_grade) VALUES
    ('CS102', 'CS100', 'D'),
    ('CS202', 'CS100', 'D')
ON DUPLICATE KEY UPDATE minimum_grade = VALUES(minimum_grade);

INSERT INTO registration_period
    (semester, year, status, opens_at, closes_at)
VALUES
    ('Fall', 2026, 'OPEN', '2026-09-01 08:00:00', '2026-10-31 23:59:59')
ON DUPLICATE KEY UPDATE
    status = VALUES(status),
    opens_at = VALUES(opens_at),
    closes_at = VALUES(closes_at);

INSERT INTO section
    (course_id, sec_id, semester, year, capacity, building, room_number,
     day_of_week, start_period, end_period, schedule, status)
VALUES
    ('CS100', '01', 'Spring', 2026, 10, '信息楼', '101', 1, 1, 2, NULL, 'FINALIZED'),
    ('CS102', '01', 'Fall', 2026, 10, '信息楼', '101', 1, 1, 2, NULL, 'OPEN'),
    ('CS201', '01', 'Fall', 2026, 10, '信息楼', '201', 2, 3, 4, NULL, 'OPEN'),
    ('CS202', '01', 'Fall', 2026, 10, '信息楼', '101', 3, 5, 6, NULL, 'OPEN'),
    ('MA101', '01', 'Fall', 2026, 10, '理学楼', '101', 4, 1, 2, NULL, 'OPEN'),
    ('GE101', '01', 'Fall', 2026, 10, '文科楼', '301', 4, 7, 8, NULL, 'OPEN'),
    ('GE102', '01', 'Fall', 2026, 10, '文科楼', '301', 5, 3, 4, NULL, 'OPEN'),
    ('GE103', '01', 'Fall', 2026, 10, '文科楼', '301', 5, 7, 8, NULL, 'OPEN')
ON DUPLICATE KEY UPDATE
    capacity = VALUES(capacity),
    building = VALUES(building),
    room_number = VALUES(room_number),
    day_of_week = VALUES(day_of_week),
    start_period = VALUES(start_period),
    end_period = VALUES(end_period),
    status = VALUES(status);

INSERT INTO instructor_qualification (teacher_id, course_id) VALUES
    ('T001', 'CS100'),
    ('T001', 'CS102'),
    ('T001', 'CS201'),
    ('T001', 'CS202'),
    ('T002', 'MA101'),
    ('T002', 'GE101'),
    ('T002', 'GE102'),
    ('T002', 'GE103')
ON DUPLICATE KEY UPDATE approved_at = approved_at;

INSERT INTO teaches (teacher_id, course_id, sec_id, semester, year) VALUES
    ('T001', 'CS100', '01', 'Spring', 2026),
    ('T001', 'CS102', '01', 'Fall', 2026),
    ('T001', 'CS201', '01', 'Fall', 2026),
    ('T001', 'CS202', '01', 'Fall', 2026),
    ('T002', 'MA101', '01', 'Fall', 2026),
    ('T002', 'GE101', '01', 'Fall', 2026),
    ('T002', 'GE102', '01', 'Fall', 2026),
    ('T002', 'GE103', '01', 'Fall', 2026)
ON DUPLICATE KEY UPDATE teacher_id = VALUES(teacher_id);

INSERT INTO takes
    (ID, course_id, sec_id, semester, year, status, score,
     regular_score, final_score, letter_grade, source)
VALUES
    ('S001', 'CS100', '01', 'Spring', 2026, 'completed', 85.0, 88.0, 84.0, 'B', 'LEGACY'),
    ('S002', 'CS100', '01', 'Spring', 2026, 'completed', 78.0, 80.0, 77.0, 'C', 'LEGACY')
ON DUPLICATE KEY UPDATE
    status = VALUES(status),
    score = VALUES(score),
    regular_score = VALUES(regular_score),
    final_score = VALUES(final_score),
    letter_grade = VALUES(letter_grade);
