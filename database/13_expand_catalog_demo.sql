-- 可重复执行的演示目录扩充：2026FA 共 12 门课程，每门 3 个教学班。
-- 只写课程目录模拟库；不改学生课表、教师认领或既有教学班。
-- 请用 MySQL Workbench 的管理员连接执行。真实旧 Ingres 目录仍由原系统维护。
SET NAMES utf8mb4;
USE course_catalog_demo;

DROP TEMPORARY TABLE IF EXISTS extra_demo_section;
CREATE TEMPORARY TABLE extra_demo_section (
  course_id VARCHAR(20) NOT NULL,
  section_code VARCHAR(20) NOT NULL,
  weekday TINYINT UNSIGNED NOT NULL,
  start_period TINYINT UNSIGNED NOT NULL,
  end_period TINYINT UNSIGNED NOT NULL,
  building VARCHAR(80) NOT NULL,
  room_number VARCHAR(20) NOT NULL,
  PRIMARY KEY (course_id,section_code)
);

INSERT INTO extra_demo_section
  (course_id,section_code,weekday,start_period,end_period,building,room_number) VALUES
  ('CS101','02',1,3,4,'信息楼','102'),
  ('CS101','03',2,5,6,'信息楼','103'),
  ('CS201','02',1,5,6,'信息楼','201'),
  ('CS201','03',3,5,6,'信息楼','202'),
  ('CS301','02',4,5,6,'信息楼','301'),
  ('CS301','03',5,3,4,'信息楼','302'),
  ('CS302','02',2,7,8,'信息楼','303'),
  ('CS302','03',5,5,6,'信息楼','304'),
  ('MA101','02',1,7,8,'理学楼','102'),
  ('MA101','03',3,7,8,'理学楼','103'),
  ('AR101','02',2,9,10,'艺术楼','102'),
  ('AR101','03',4,7,8,'艺术楼','103'),
  ('AR102','02',3,9,10,'艺术楼','202'),
  ('AR102','03',5,7,8,'艺术楼','203'),
  ('CS102','01',2,3,4,'信息楼','105'),
  ('CS102','02',4,3,4,'信息楼','106'),
  ('CS102','03',5,9,10,'信息楼','107'),
  ('CS202','01',1,9,10,'信息楼','205'),
  ('CS202','02',3,3,4,'信息楼','206'),
  ('CS202','03',4,9,10,'信息楼','207'),
  ('CS303','01',2,1,2,'信息楼','305'),
  ('CS303','02',4,1,2,'信息楼','306'),
  ('CS303','03',5,1,2,'信息楼','307'),
  ('MA102','01',1,1,2,'理学楼','201'),
  ('MA102','02',3,1,2,'理学楼','202'),
  ('MA102','03',5,1,2,'理学楼','203'),
  ('AR103','01',2,5,6,'艺术楼','301'),
  ('AR103','02',4,5,6,'艺术楼','302'),
  ('AR103','03',5,5,6,'艺术楼','303');

START TRANSACTION;

INSERT INTO course (course_id,title,department_id,credits) VALUES
  ('CS102','Web 应用开发基础','CS',3),
  ('CS202','计算机网络','CS',3),
  ('CS303','操作系统','CS',4),
  ('MA102','线性代数','MATH',3),
  ('AR103','数字媒体基础','ART',2)
ON DUPLICATE KEY UPDATE course_id=course_id;

INSERT INTO course_prerequisite (course_id,prerequisite_course_id,minimum_grade) VALUES
  ('CS202','CS101','D'),
  ('CS303','CS201','D')
ON DUPLICATE KEY UPDATE course_id=course_id;

INSERT INTO course_offering (offering_id,course_id,term_code,section_code,capacity)
SELECT CONCAT('2026FA-',e.course_id,'-',e.section_code),e.course_id,'2026FA',e.section_code,10
FROM extra_demo_section AS e
WHERE NOT EXISTS (
  SELECT 1 FROM course_offering AS o
  WHERE o.course_id=e.course_id AND o.term_code='2026FA' AND o.section_code=e.section_code
);

INSERT INTO offering_meeting
  (offering_id,weekday,start_period,end_period,building,room_number)
SELECT o.offering_id,e.weekday,e.start_period,e.end_period,e.building,e.room_number
FROM extra_demo_section AS e
JOIN course_offering AS o
  ON o.course_id=e.course_id AND o.term_code='2026FA' AND o.section_code=e.section_code
WHERE NOT EXISTS (
  SELECT 1 FROM offering_meeting AS m WHERE m.offering_id=o.offering_id
);

COMMIT;
DROP TEMPORARY TABLE extra_demo_section;

-- 预期：12 门课程，每门 3 个教学班，合计 36 个教学班。
SELECT course_id,COUNT(*) AS teaching_sections
FROM course_offering WHERE term_code='2026FA'
GROUP BY course_id ORDER BY course_id;
