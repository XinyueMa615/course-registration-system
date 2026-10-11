-- 只用于第六版隔离测试目录；不会修改 2026FA 的课程或教学班。
-- 为“关闭选课 -> 确认教学结束 -> 教师录分”准备 2026SU 的 6 个演示教学班。
SET NAMES utf8mb4;
USE course_catalog_v6_test;

START TRANSACTION;

INSERT INTO course_offering (offering_id,course_id,term_code,section_code,capacity)
SELECT REPLACE(o.offering_id,'2026FA-','2026SU-'),o.course_id,'2026SU',o.section_code,o.capacity
FROM course_offering AS o
WHERE o.offering_id IN (
  '2026FA-CS101-01','2026FA-CS302-01','2026FA-MA101-01',
  '2026FA-AR101-01','2026FA-CS201-01','2026FA-AR102-01'
)
AND NOT EXISTS (
  SELECT 1 FROM course_offering AS existing
  WHERE existing.course_id=o.course_id AND existing.term_code='2026SU'
    AND existing.section_code=o.section_code
);

INSERT INTO offering_meeting
  (offering_id,weekday,start_period,end_period,building,room_number)
SELECT REPLACE(m.offering_id,'2026FA-','2026SU-'),
       m.weekday,m.start_period,m.end_period,m.building,m.room_number
FROM offering_meeting AS m
WHERE m.offering_id IN (
  '2026FA-CS101-01','2026FA-CS302-01','2026FA-MA101-01',
  '2026FA-AR101-01','2026FA-CS201-01','2026FA-AR102-01'
)
AND NOT EXISTS (
  SELECT 1 FROM offering_meeting AS existing
  WHERE existing.offering_id=REPLACE(m.offering_id,'2026FA-','2026SU-')
    AND existing.weekday=m.weekday AND existing.start_period=m.start_period
    AND existing.end_period=m.end_period
);

COMMIT;

SELECT o.offering_id,o.course_id,COUNT(m.meeting_id) AS weekly_meetings
FROM course_offering AS o
LEFT JOIN offering_meeting AS m ON m.offering_id=o.offering_id
WHERE o.term_code='2026SU'
GROUP BY o.offering_id,o.course_id
ORDER BY o.offering_id;
