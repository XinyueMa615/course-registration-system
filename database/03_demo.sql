-- 无真实个人资料和密码的本地演示数据；先执行 01_catalog.sql、02_registration.sql。
USE course_catalog_demo;

INSERT INTO department (department_id,name) VALUES
 ('CS','计算机系'),('MATH','数学系'),('ART','艺术系')
ON DUPLICATE KEY UPDATE name=VALUES(name);

INSERT INTO course (course_id,title,department_id,credits) VALUES
 ('CS101','程序设计基础','CS',4),('CS201','数据结构','CS',4),
 ('CS301','软件工程','CS',3),('CS302','数据库系统','CS',3),
 ('MA101','高等数学','MATH',4),('AR101','艺术导论','ART',2),
 ('AR102','设计基础','ART',2)
ON DUPLICATE KEY UPDATE title=VALUES(title),department_id=VALUES(department_id),credits=VALUES(credits);

INSERT INTO course_prerequisite (course_id,prerequisite_course_id,minimum_grade) VALUES
 ('CS201','CS101','D'),('CS301','CS201','D')
ON DUPLICATE KEY UPDATE minimum_grade=VALUES(minimum_grade);

INSERT INTO course_offering (offering_id,course_id,term_code,section_code,capacity) VALUES
 ('2026FA-CS101-01','CS101','2026FA','01',10),
 ('2026FA-CS201-01','CS201','2026FA','01',10),
 ('2026FA-CS301-01','CS301','2026FA','01',10),
 ('2026FA-CS302-01','CS302','2026FA','01',10),
 ('2026FA-MA101-01','MA101','2026FA','01',10),
 ('2026FA-AR101-01','AR101','2026FA','01',10),
 ('2026FA-AR102-01','AR102','2026FA','01',10)
ON DUPLICATE KEY UPDATE capacity=VALUES(capacity);

INSERT INTO offering_meeting
 (meeting_id,offering_id,weekday,start_period,end_period,building,room_number) VALUES
 (1,'2026FA-CS101-01',1,1,2,'信息楼','101'),
 (2,'2026FA-CS101-01',3,1,2,'信息楼','101'),
 (3,'2026FA-CS201-01',2,1,2,'信息楼','101'),
 (4,'2026FA-CS301-01',2,3,4,'信息楼','101'),
 (5,'2026FA-CS302-01',3,3,4,'信息楼','201'),
 (6,'2026FA-MA101-01',4,1,2,'理学楼','101'),
 (7,'2026FA-AR101-01',4,3,4,'艺术楼','101'),
 (8,'2026FA-AR102-01',5,1,2,'艺术楼','101')
ON DUPLICATE KEY UPDATE weekday=VALUES(weekday),start_period=VALUES(start_period),
 end_period=VALUES(end_period),building=VALUES(building),room_number=VALUES(room_number);

USE course_registration_v2;

INSERT INTO academic_term
 (term_code,year,semester,registration_opens_at,registration_closes_at,status,tuition_per_credit)
VALUES ('2026FA',2026,'FALL','2026-09-01 08:00:00','2026-10-15 23:59:59','OPEN',500)
ON DUPLICATE KEY UPDATE registration_opens_at=VALUES(registration_opens_at),
 registration_closes_at=VALUES(registration_closes_at),tuition_per_credit=VALUES(tuition_per_credit);

INSERT INTO student_profile (student_id,full_name,date_of_birth) VALUES
 ('S001','测试学生甲','2005-01-01'),('S002','测试学生乙','2005-02-01'),
 ('S003','测试学生丙','2005-03-01'),('S004','测试学生丁','2005-04-01')
ON DUPLICATE KEY UPDATE full_name=VALUES(full_name);

INSERT INTO professor_profile (professor_id,full_name,date_of_birth,department_id) VALUES
 ('P001','测试教师甲','1980-01-01','CS'),
 ('P002','测试教师乙','1982-01-01','MATH'),
 ('P003','测试教师丙','1983-01-01','ART')
ON DUPLICATE KEY UPDATE full_name=VALUES(full_name),department_id=VALUES(department_id);

INSERT INTO offering_registration_state (offering_id,term_code,capacity) VALUES
 ('2026FA-CS101-01','2026FA',10),('2026FA-CS201-01','2026FA',10),
 ('2026FA-CS301-01','2026FA',10),('2026FA-CS302-01','2026FA',10),
 ('2026FA-MA101-01','2026FA',10),('2026FA-AR101-01','2026FA',10),
 ('2026FA-AR102-01','2026FA',10)
ON DUPLICATE KEY UPDATE capacity=VALUES(capacity);

INSERT INTO professor_qualification (professor_id,course_id) VALUES
 ('P001','CS101'),('P001','CS201'),('P001','CS301'),('P001','CS302'),
 ('P002','MA101'),('P003','AR101'),('P003','AR102')
ON DUPLICATE KEY UPDATE course_id=VALUES(course_id);

INSERT INTO teaching_assignment (offering_id,professor_id) VALUES
 ('2026FA-CS101-01','P001'),('2026FA-CS201-01','P001'),
 ('2026FA-CS301-01','P001'),('2026FA-CS302-01','P001'),
 ('2026FA-MA101-01','P002'),('2026FA-AR101-01','P003'),
 ('2026FA-AR102-01','P003')
ON DUPLICATE KEY UPDATE professor_id=VALUES(professor_id);

-- 一名学生的 4 主选 + 2 备选草稿；草稿不占名额。
INSERT INTO student_schedule (student_id,term_code,status)
VALUES ('S001','2026FA','DRAFT')
ON DUPLICATE KEY UPDATE student_id=VALUES(student_id);

INSERT INTO schedule_choice
 (schedule_id,offering_id,term_code,choice_type,priority) VALUES
 ((SELECT schedule_id FROM student_schedule WHERE student_id='S001' AND term_code='2026FA'),'2026FA-CS101-01','2026FA','PRIMARY',1),
 ((SELECT schedule_id FROM student_schedule WHERE student_id='S001' AND term_code='2026FA'),'2026FA-CS302-01','2026FA','PRIMARY',2),
 ((SELECT schedule_id FROM student_schedule WHERE student_id='S001' AND term_code='2026FA'),'2026FA-MA101-01','2026FA','PRIMARY',3),
 ((SELECT schedule_id FROM student_schedule WHERE student_id='S001' AND term_code='2026FA'),'2026FA-AR101-01','2026FA','PRIMARY',4),
 ((SELECT schedule_id FROM student_schedule WHERE student_id='S001' AND term_code='2026FA'),'2026FA-CS201-01','2026FA','ALTERNATE',1),
 ((SELECT schedule_id FROM student_schedule WHERE student_id='S001' AND term_code='2026FA'),'2026FA-AR102-01','2026FA','ALTERNATE',2)
ON DUPLICATE KEY UPDATE offering_id=VALUES(offering_id);
