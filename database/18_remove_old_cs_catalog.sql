-- 仅在已备份、已运行 scripts.rebuild_cs_demo_v6，且确认旧教学班
-- 在业务库不再被课表或授课安排引用后，由目录库管理员执行。
-- 本机测试库名；若要用于其他环境，必须人工核对目标库和数据范围。
USE course_catalog_v6_test;

START TRANSACTION;

-- 包含指向旧课程的先修关系；保留两条新的演示先修规则。
DELETE FROM course_prerequisite
WHERE course_id IN ('CS101','CS102','CS201','CS202','CS301','CS302','CS303')
   OR prerequisite_course_id IN ('CS101','CS102','CS201','CS202','CS301','CS302','CS303')
   OR (course_id='211012' AND prerequisite_course_id='MA101');

DELETE m FROM offering_meeting AS m
JOIN course_offering AS o ON o.offering_id=m.offering_id
WHERE o.course_id IN ('CS101','CS102','CS201','CS202','CS301','CS302','CS303');

DELETE FROM course_offering
WHERE course_id IN ('CS101','CS102','CS201','CS202','CS301','CS302','CS303');

DELETE FROM course
WHERE course_id IN ('CS101','CS102','CS201','CS202','CS301','CS302','CS303');

COMMIT;

SELECT course_id,title FROM course WHERE department_id='CS' ORDER BY course_id;
