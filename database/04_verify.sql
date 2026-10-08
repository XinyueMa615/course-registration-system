-- Workbench 中执行：应显示 5 张目录表、14 张业务表、1 个视图。
SELECT table_schema,table_name,table_type
FROM information_schema.tables
WHERE table_schema IN ('course_catalog_demo','course_registration_v2')
ORDER BY table_schema,table_name;

-- S001 应是 DRAFT，主选4、备选2；草稿不占容量。
SELECT s.student_id,s.term_code,s.status,
 SUM(c.choice_type='PRIMARY') AS primary_count,
 SUM(c.choice_type='ALTERNATE') AS alternate_count
FROM course_registration_v2.student_schedule s
JOIN course_registration_v2.schedule_choice c ON c.schedule_id=s.schedule_id
GROUP BY s.schedule_id,s.student_id,s.term_code,s.status;

SELECT offering_id,capacity,enrolled_count,status
FROM course_registration_v2.offering_registration_state ORDER BY offering_id;

-- 以下两条查询都应返回 0 行。
SELECT r.offering_id
FROM course_registration_v2.offering_registration_state r
LEFT JOIN course_catalog_demo.course_offering c ON c.offering_id=r.offering_id
WHERE c.offering_id IS NULL OR c.term_code<>r.term_code OR c.capacity<>r.capacity;

SELECT r.offering_id,r.enrolled_count,COUNT(e.enrollment_id) AS actual_count
FROM course_registration_v2.offering_registration_state r
LEFT JOIN course_registration_v2.enrollment e
 ON e.offering_id=r.offering_id AND e.status IN ('ENROLLED','COMMITTED','COMPLETED')
GROUP BY r.offering_id,r.enrolled_count
HAVING r.enrolled_count<>actual_count;
