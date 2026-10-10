-- 可选演示数据：为已有 2026FA 演示库追加一个未认领教学班。
-- 在 MySQL Workbench 中用有目录库写入权限的管理员账号执行；应用本身仍只读目录库。
-- 不会更改已存在的七个教学班或学生课表。
SET NAMES utf8mb4;
USE course_catalog_demo;
INSERT INTO course_offering (offering_id,course_id,term_code,section_code,capacity)
VALUES ('2026FA-CS101-02','CS101','2026FA','02',10)
ON DUPLICATE KEY UPDATE offering_id=offering_id;

INSERT INTO offering_meeting (offering_id,weekday,start_period,end_period,building,room_number)
SELECT '2026FA-CS101-02',5,3,4,'信息楼','102'
WHERE NOT EXISTS (
  SELECT 1 FROM offering_meeting WHERE offering_id='2026FA-CS101-02'
);

USE course_registration_v2;
INSERT INTO offering_registration_state (offering_id,term_code,capacity)
VALUES ('2026FA-CS101-02','2026FA',10)
ON DUPLICATE KEY UPDATE offering_id=offering_id;
