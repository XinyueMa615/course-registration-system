-- 2026 春/秋两学期的计算机系演示培养方案课程。管理员在“目录模拟库”执行。
-- 标准全新安装用 course_catalog_demo；本机第六/七版本测试库执行前把 USE 改成
-- .env 的 CATALOG_DB（目前是 course_catalog_v6_test）。可重复执行；不删除旧课、课表或成绩。
-- 课程和建议学期取自《计算机科学与技术学院本科培养方案2022版（2023年修订）》；
-- 下方两条先修规则是本项目为测试设计的，并非培养方案原文规定。
SET NAMES utf8mb4;
USE course_catalog_demo;

START TRANSACTION;

INSERT INTO course (course_id,title,department_id,credits) VALUES
  ('212002','面向对象程序设计','CS',3.5),
  ('211001','离散数学Ⅰ','CS',3.5),
  ('211002','模拟与数字逻辑电路','CS',3.5),
  ('941015','基础物理学','CS',3.5),
  ('213001','程序设计基础课程设计','CS',1.0),
  ('931102','微积分AⅡ','CS',3.0),
  ('LD2001','劳动教育','CS',2.0),
  ('212003','数据结构','CS',5.0),
  ('211003','离散数学Ⅱ','CS',3.5),
  ('211004','计算机组成原理','CS',3.0),
  ('211011','计算思维和计算科学','CS',3.0),
  ('211012','数学建模','CS',2.0),
  ('213002','计算机硬件系统设计实验I','CS',1.5),
  ('931103','微积分AⅢ','CS',3.0)
ON DUPLICATE KEY UPDATE course_id=course_id;

-- S001 的 212002“面向对象程序设计”为 F：选 212003“数据结构”时失败。
-- S001 的 211001“离散数学Ⅰ”为 B：选 211012“数学建模”时通过。
INSERT INTO course_prerequisite (course_id,prerequisite_course_id,minimum_grade)
VALUES ('212003','212002','D'),('211012','211001','D')
ON DUPLICATE KEY UPDATE prerequisite_course_id=VALUES(prerequisite_course_id),
                        minimum_grade=VALUES(minimum_grade);

INSERT INTO course_offering (offering_id,course_id,term_code,section_code,capacity) VALUES
  ('2026SP-212002-01','212002','2026SP','01',10),
  ('2026SP-212002-02','212002','2026SP','02',10),
  ('2026SP-211001-01','211001','2026SP','01',10),
  ('2026SP-211002-01','211002','2026SP','01',10),
  ('2026SP-941015-01','941015','2026SP','01',10),
  ('2026SP-213001-01','213001','2026SP','01',10),
  ('2026SP-931102-01','931102','2026SP','01',10),
  ('2026SP-LD2001-01','LD2001','2026SP','01',10),
  ('2026FA-212003-01','212003','2026FA','01',10),
  ('2026FA-212003-02','212003','2026FA','02',10),
  ('2026FA-212003-03','212003','2026FA','03',10),
  ('2026FA-211003-01','211003','2026FA','01',10),
  ('2026FA-211003-02','211003','2026FA','02',10),
  ('2026FA-211004-01','211004','2026FA','01',10),
  ('2026FA-211004-02','211004','2026FA','02',10),
  ('2026FA-211011-01','211011','2026FA','01',10),
  ('2026FA-211011-02','211011','2026FA','02',10),
  ('2026FA-211012-01','211012','2026FA','01',10),
  ('2026FA-211012-02','211012','2026FA','02',10),
  ('2026FA-213002-01','213002','2026FA','01',10),
  ('2026FA-931103-01','931103','2026FA','01',10)
ON DUPLICATE KEY UPDATE offering_id=offering_id;

INSERT INTO offering_meeting (offering_id,weekday,start_period,end_period,building,room_number)
SELECT data.offering_id,data.weekday,data.start_period,data.end_period,'信息楼',data.room_number
FROM (
  SELECT '2026SP-212002-01' AS offering_id,1 AS weekday,1 AS start_period,2 AS end_period,'201' AS room_number UNION ALL
  SELECT '2026SP-212002-02',1,5,6,'206' UNION ALL
  SELECT '2026SP-211001-01',2,1,2,'202' UNION ALL
  SELECT '2026SP-211002-01',3,1,2,'203' UNION ALL
  SELECT '2026SP-941015-01',4,1,2,'204' UNION ALL
  SELECT '2026SP-213001-01',5,1,2,'205' UNION ALL
  SELECT '2026SP-931102-01',4,3,4,'207' UNION ALL
  SELECT '2026SP-LD2001-01',5,3,4,'208' UNION ALL
  SELECT '2026FA-212003-01',2,1,2,'311' UNION ALL
  SELECT '2026FA-212003-02',2,5,6,'312' UNION ALL
  SELECT '2026FA-212003-03',5,1,2,'313' UNION ALL
  SELECT '2026FA-211003-01',1,1,2,'301' UNION ALL
  SELECT '2026FA-211003-02',1,5,6,'302' UNION ALL
  SELECT '2026FA-211004-01',2,3,4,'303' UNION ALL
  SELECT '2026FA-211004-02',1,5,6,'304' UNION ALL
  SELECT '2026FA-211011-01',3,5,6,'305' UNION ALL
  SELECT '2026FA-211011-02',3,7,8,'306' UNION ALL
  SELECT '2026FA-211012-01',4,7,8,'307' UNION ALL
  SELECT '2026FA-211012-02',4,9,10,'308' UNION ALL
  SELECT '2026FA-213002-01',4,1,2,'309' UNION ALL
  SELECT '2026FA-931103-01',5,3,4,'310'
) AS data
WHERE NOT EXISTS (
  SELECT 1 FROM offering_meeting m WHERE m.offering_id=data.offering_id
);

COMMIT;

-- 仅核对计划课程；业务记录和旧目录由后续受控重建步骤清理。
SELECT o.term_code,c.course_id,c.title,COUNT(*) AS sections
FROM course_offering o JOIN course c ON c.course_id=o.course_id
WHERE o.course_id IN ('212002','211001','211002','941015','213001','931102','LD2001',
                      '212003','211003','211004','211011','211012','213002','931103')
  AND o.term_code IN ('2026SP','2026FA')
GROUP BY o.term_code,c.course_id,c.title ORDER BY o.term_code,c.course_id;
