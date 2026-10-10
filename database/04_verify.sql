-- Workbench 中执行：应显示 5 张目录表、15 张业务表、1 个视图。
SET NAMES utf8mb4;
SELECT table_schema,table_name,table_type
FROM information_schema.tables
WHERE table_schema IN ('course_catalog_demo','course_registration_v2')
ORDER BY table_schema,table_name;

-- 以下是安全的业务内容总览：不查询密码哈希和 SSN 密文。
SELECT u.username,u.role,u.is_active,u.must_change_password,u.created_at
FROM course_registration_v2.user_account u
ORDER BY u.created_at,u.username;

SELECT s.student_id,s.full_name,s.date_of_birth,s.status,s.graduation_date,u.username
FROM course_registration_v2.student_profile s
LEFT JOIN course_registration_v2.user_account u ON u.user_id=s.user_id
ORDER BY s.student_id;

SELECT p.professor_id,p.full_name,p.date_of_birth,p.department_id,p.status,u.username
FROM course_registration_v2.professor_profile p
LEFT JOIN course_registration_v2.user_account u ON u.user_id=p.user_id
ORDER BY p.professor_id;

SELECT term_code,year,semester,status,registration_opens_at,registration_closes_at,completed_at
FROM course_registration_v2.academic_term
ORDER BY year,semester;

SELECT course_id,title,department_id,credits,is_active
FROM course_catalog_demo.course
ORDER BY course_id;

SELECT offering_id,course_id,term_code,section_code,capacity
FROM course_catalog_demo.course_offering
ORDER BY term_code,course_id,section_code;

SELECT s.schedule_id,s.student_id,s.term_code,s.status,
 c.offering_id,c.choice_type,c.priority,c.status AS choice_status
FROM course_registration_v2.student_schedule s
LEFT JOIN course_registration_v2.schedule_choice c ON c.schedule_id=s.schedule_id
ORDER BY s.schedule_id,c.choice_type,c.priority;

SELECT a.offering_id,a.professor_id,p.full_name,a.assigned_at
FROM course_registration_v2.teaching_assignment a
JOIN course_registration_v2.professor_profile p ON p.professor_id=a.professor_id
ORDER BY a.offering_id;

SELECT term_code,status,COUNT(*) AS bill_count,SUM(amount) AS total_amount
FROM course_registration_v2.billing_outbox
GROUP BY term_code,status
ORDER BY term_code,status;

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
