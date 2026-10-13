-- 仅供本机 course_catalog_v6_test：春季/秋季各增加两门培养方案课程。
-- 管理员在 Workbench 执行；业务应用始终只读课程目录。
-- 修改别的环境时，请先核对课程代码、学期和已有教学班，再改库名。
SET NAMES utf8mb4;
USE course_catalog_v6_test;

START TRANSACTION;

INSERT INTO course (course_id,title,department_id,credits) VALUES
  ('931102','微积分AⅡ','CS',3.0),
  ('LD2001','劳动教育','CS',2.0),
  ('213002','计算机硬件系统设计实验I','CS',1.5),
  ('931103','微积分AⅢ','CS',3.0)
ON DUPLICATE KEY UPDATE course_id=course_id;

INSERT INTO course_offering (offering_id,course_id,term_code,section_code,capacity) VALUES
  ('2026SP-931102-01','931102','2026SP','01',10),
  ('2026SP-LD2001-01','LD2001','2026SP','01',10),
  ('2026FA-213002-01','213002','2026FA','01',10),
  ('2026FA-931103-01','931103','2026FA','01',10)
ON DUPLICATE KEY UPDATE offering_id=offering_id;

INSERT INTO offering_meeting (offering_id,weekday,start_period,end_period,building,room_number)
SELECT data.offering_id,data.weekday,data.start_period,data.end_period,'信息楼',data.room_number
FROM (
  SELECT '2026SP-931102-01' AS offering_id,4 AS weekday,3 AS start_period,4 AS end_period,'207' AS room_number UNION ALL
  SELECT '2026SP-LD2001-01',5,3,4,'208' UNION ALL
  SELECT '2026FA-213002-01',4,1,2,'309' UNION ALL
  SELECT '2026FA-931103-01',5,3,4,'310'
) AS data
WHERE NOT EXISTS (
  SELECT 1 FROM offering_meeting m WHERE m.offering_id=data.offering_id
);

COMMIT;

SELECT o.term_code,c.course_id,c.title,o.offering_id,o.capacity
FROM course_offering o JOIN course c ON c.course_id=o.course_id
WHERE o.offering_id IN ('2026SP-931102-01','2026SP-LD2001-01',
                        '2026FA-213002-01','2026FA-931103-01')
ORDER BY o.term_code,o.course_id;
