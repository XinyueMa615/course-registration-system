# 数据库建立指南

旧数据库丢失后，不需要再寻找旧文件。当前目录已经包含一套可以重新建立数据库的脚本。

## 准备软件

在本机安装并启动 MySQL 8.0 或更高版本。建议同时安装 MySQL Workbench，这样可以通过图形界面执行 SQL，不必记命令。

## 使用 MySQL Workbench 建库

1. 打开 MySQL Workbench，连接本机 MySQL，通常地址是 `127.0.0.1:3306`。
2. 打开 `database/schema.sql`，点击闪电按钮执行。它会创建数据库、表、视图和容量控制触发器。
3. 打开 `database/seed.sql`，再次点击闪电按钮执行。它会加入少量演示课程和账号。
4. 复制 `database/create_app_user.sql.example`，命名为 `create_app_user.sql`。
5. 在复制出的文件中设置一个新的数据库密码，然后执行该文件。
6. 复制项目根目录 `.env.example`，命名为 `.env`，将相同密码填入 `DB_PASSWORD`。

`create_app_user.sql` 和 `.env` 都已被 Git 忽略，不能上传到仓库。

## 使用终端建库

如果已经可以使用 `mysql` 命令，也可以在项目根目录执行：

```bash
mysql -u root -p < database/schema.sql
mysql -u root -p < database/seed.sql
mysql -u root -p < database/create_app_user.sql
```

每次命令都会要求输入本机 MySQL 管理员密码。

## 验证是否成功

在 Workbench 中执行：

```sql
USE school_db;
SHOW TABLES;
SELECT username, role FROM users;
SELECT course_id, title FROM course;
```

应该能看到学生、教师、课程、教学班、4+2 志愿、计费任务和操作日志等表。

## 本地演示账号

演示数据提供以下账号，初始密码统一为 `DevOnly_2026!`：

- 管理员：`admin`
- 教师：`teacher_zhang`
- 学生：`student_zhang`

这些账号只用于本机首次联调。现有程序仍使用旧式明文密码校验，完成数据库恢复后应尽快改为密码哈希和登录会话，不能将演示密码用于正式部署。

## 两个脚本分别做什么

- `schema.sql`：数据库结构，可以提交到 Git，是六名组员统一数据库版本的依据。
- `seed.sql`：不含真实个人信息的演示数据，方便每名组员得到相同的测试环境。

以后不能再由组员各自运行零散的“加字段”“修数据”脚本。数据库结构变更应新增带编号的迁移文件，经代码评审后合并。
