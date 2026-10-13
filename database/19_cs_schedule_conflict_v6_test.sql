-- 本机第六/七版本测试目录库：为学生/教师演示制造一个真实时间冲突。
-- 离散数学Ⅱ 02 班现为周一 5–6 节；把计算机组成原理 02 班
-- 从原来的周二 7–8 节调整为周一 5–6 节。只匹配原始时间，可重复执行。
-- 全新安装的 17_cs_curriculum_demo.sql 已包含新时间，不需执行本脚本。
USE course_catalog_v6_test;

START TRANSACTION;
UPDATE offering_meeting
SET weekday=1,start_period=5,end_period=6
WHERE offering_id='2026FA-211004-02'
  AND weekday=2 AND start_period=7 AND end_period=8;
COMMIT;

SELECT offering_id,weekday,start_period,end_period
FROM offering_meeting
WHERE offering_id IN ('2026FA-211003-02','2026FA-211004-02')
ORDER BY offering_id;

-- 如需撤销演示修改，可在确认无相关课表/认领后，将 211004-02 改回周二 7–8 节。
