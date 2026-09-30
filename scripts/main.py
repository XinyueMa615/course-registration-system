from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
import pymysql
from typing import Optional, List

try:
    from .config import ALLOWED_ORIGINS, DATABASE, PROJECT_ROOT
except ImportError:
    from config import ALLOWED_ORIGINS, DATABASE, PROJECT_ROOT

# 1. 初始化后台程序
app = FastAPI(
    title="课程注册系统后台",
    description="包含学生、教师和教务管理员业务的课程注册系统 API",
)


def 读取页面(相对路径: str) -> HTMLResponse:
    页面路径 = PROJECT_ROOT / 相对路径
    content = 页面路径.read_text(encoding="utf-8")
    return HTMLResponse(content=content, media_type="text/html")

# 提供HTML页面的路由
@app.get("/")
async def get_index():
    return 读取页面("shared/index.html")

@app.get("/index.html")
async def get_index_html():
    return 读取页面("shared/index.html")

@app.get("/login.html")
async def get_login():
    return 读取页面("student_portal/login.html")

@app.get("/teacher_login.html")
async def get_teacher_login():
    return 读取页面("teacher_portal/teacher_login.html")

@app.get("/admin_login.html")
async def get_admin_login():
    return 读取页面("admin_portal/admin_login.html")

@app.get("/admin_portal.html")
async def get_admin_portal():
    return 读取页面("admin_portal/admin_portal.html")

@app.get("/teacher_portal.html")
async def get_teacher_portal():
    return 读取页面("teacher_portal/teacher_portal.html")

@app.get("/student_portal.html")
async def get_student_portal():
    return 读取页面("student_portal/student_portal.html")

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health", tags=["系统"])
def 健康检查():
    return {"状态": "正常", "服务": "课程注册系统后台"}

# 2. 定义数据模型
class 登录信息(BaseModel):
    用户名: str = Field(..., example="stu_xiaoming", description="你的账号，例如 stu_xiaoming")
    密码: str = Field(..., example="123", description="你的密码")

class 密码重置信息(BaseModel):
    旧密码: str = Field(..., description="当前密码")
    新密码: str = Field(..., description="新密码")

class 联系方式更新(BaseModel):
    手机号: Optional[str] = Field(None, description="手机号码")
    邮箱: Optional[str] = Field(None, description="电子邮箱")

class 学生信息(BaseModel):
    学号: str = Field(..., description="学生学号")
    姓名: str = Field(..., description="学生姓名")
    院系: str = Field(..., description="所属院系")
    已修学分: Optional[float] = Field(0.0, description="已修学分")
    入学年份: int = Field(..., description="入学年份")
    电话: Optional[str] = Field(None, description="手机号码")
    邮箱: Optional[str] = Field(None, description="电子邮箱")

class 教师信息(BaseModel):
    教师ID: str = Field(..., description="教师ID")
    姓名: str = Field(..., description="教师姓名")
    院系: str = Field(..., description="所属院系")
    电话: Optional[str] = Field(None, description="手机号码")
    邮箱: Optional[str] = Field(None, description="电子邮箱")

class 选课信息(BaseModel):
    课程编号: str = Field(..., description="课程ID")
    班级编号: str = Field(..., description="班级ID")
    学期: str = Field(..., description="学期")
    学年: int = Field(..., description="学年")

# 教师端数据模型
class 成绩录入信息(BaseModel):
    学生学号: str = Field(..., description="学生学号")
    课程编号: str = Field(..., description="课程ID")
    班级编号: str = Field(..., description="班级ID")
    学期: str = Field(..., description="学期")
    学年: int = Field(..., description="学年")
    平时分: Optional[float] = Field(None, description="平时成绩")
    期末分: Optional[float] = Field(None, description="期末成绩")
    权重平时: Optional[int] = Field(3, description="平时成绩权重")
    权重期末: Optional[int] = Field(7, description="期末成绩权重")
    最终成绩: Optional[float] = Field(None, description="最终成绩")

class 教学任务筛选(BaseModel):
    学期: Optional[str] = Field(None, description="学期")
    学年: Optional[int] = Field(None, description="学年")

# 3. 专门用来连接数据库的工具
def 连接数据库():
    return pymysql.connect(
        host=DATABASE.host,
        port=DATABASE.port,
        user=DATABASE.user,
        password=DATABASE.password,
        db=DATABASE.database,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

# 辅助函数：根据用户名获取学生ID
def 获取学生ID(用户名: str):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 先查询users表获取user_id
        SQL语句 = "SELECT user_id FROM users WHERE username = %s AND role = 'student'"
        游标.execute(SQL语句, (用户名,))
        用户信息 = 游标.fetchone()
        
        if 用户信息:
            # 再查询student表获取学生ID
            SQL语句 = "SELECT ID FROM student WHERE user_id = %s"
            游标.execute(SQL语句, (用户信息['user_id'],))
            学生信息 = 游标.fetchone()
            
            if 学生信息:
                return 学生信息['ID']
        
        return None
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"数据库查询失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

def 获取教师ID(用户名: str):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 先查询users表获取user_id
        SQL语句 = "SELECT user_id FROM users WHERE username = %s AND role = 'teacher'"
        游标.execute(SQL语句, (用户名,))
        用户信息 = 游标.fetchone()
        
        if 用户信息:
            # 再查询instructor表获取教师ID
            SQL语句 = "SELECT ID FROM instructor WHERE user_id = %s"
            游标.execute(SQL语句, (用户信息['user_id'],))
            教师信息 = 游标.fetchone()
            
            if 教师信息:
                return 教师信息['ID']
        
        return None
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"数据库查询失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 4. 【核心】只有这一个登录接口！
@app.post("/login", summary="处理账号密码登录", tags=["登录模块"])
def 处理登录(表单: 登录信息):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 去 users 表里核对账号密码
        SQL语句 = "SELECT user_id, username, role FROM users WHERE username = %s AND password = %s"
        游标.execute(SQL语句, (表单.用户名, 表单.密码))
        
        # 拿回比对结果
        查询到的用户 = 游标.fetchone()
        
        if 查询到的用户:
            return {
                "状态": "成功",
                "提示": "密码正确，允许登录！",
                "用户信息": 查询到的用户
            }
        else:
            raise HTTPException(status_code=401, detail="账号或密码写错啦，请重试！")
            
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"数据库没连上: {str(报错信息)}")
    finally:
        # 查完一定要关门
        if 连接:
            连接.close()

# ===========================================
# 8. 教师端功能接口
# ===========================================

# 8.1 获取教师档案
@app.get("/teacher/profile/{username}", summary="获取教师档案", tags=["教师模块"])
def 获取教师档案(username: str):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 获取教师详细信息
        SQL语句 = """
            SELECT i.ID, i.name, i.dept_name, i.phone, i.email, 
                   d.building, d.budget, u.username
            FROM instructor i 
            LEFT JOIN department d ON i.dept_name = d.dept_name
            LEFT JOIN users u ON i.user_id = u.user_id
            WHERE u.username = %s
        """
        游标.execute(SQL语句, (username,))
        教师档案 = 游标.fetchone()
        
        if not 教师档案:
            raise HTTPException(status_code=404, detail="教师信息不存在")
        
        return {
            "状态": "成功",
            "教师档案": 教师档案
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 8.2 更新教师联系方式
@app.put("/teacher/contact/{username}", summary="更新教师联系方式", tags=["教师模块"])
def 更新教师联系方式(username: str, 表单: 联系方式更新):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 获取教师ID
        教师ID = 获取教师ID(username)
        if not 教师ID:
            raise HTTPException(status_code=404, detail="教师信息不存在")
        
        # 构建更新语句
        更新字段 = []
        更新值 = []
        
        if 表单.手机号 is not None:
            更新字段.append("phone = %s")
            更新值.append(表单.手机号)
        
        if 表单.邮箱 is not None:
            更新字段.append("email = %s")
            更新值.append(表单.邮箱)
        
        if not 更新字段:
            raise HTTPException(status_code=400, detail="没有提供要更新的信息")
        
        # 执行更新
        更新值.append(教师ID)
        SQL语句 = f"UPDATE instructor SET {', '.join(更新字段)} WHERE ID = %s"
        游标.execute(SQL语句, 更新值)
        连接.commit()
        
        return {
            "状态": "成功",
            "提示": "联系方式更新成功"
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"更新失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 8.3 获取教学任务列表
@app.get("/teacher/courses/{username}", summary="获取教学任务列表", tags=["教师模块"])
def 获取教学任务列表(username: str, 学期: Optional[str] = None, 学年: Optional[int] = None):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 获取教师ID
        教师ID = 获取教师ID(username)
        if not 教师ID:
            raise HTTPException(status_code=404, detail="教师信息不存在")
        
        # 构建查询条件
        查询条件 = "WHERE t.teacher_id = %s"
        查询参数 = [教师ID]
        
        if 学期:
            查询条件 += " AND t.semester = %s"
            查询参数.append(学期)
        
        if 学年:
            查询条件 += " AND t.year = %s"
            查询参数.append(学年)
        
        # 获取教学任务列表
        SQL语句 = f"""
            SELECT t.course_id, t.sec_id, t.semester, t.year, 
                   c.title as course_name, c.credits, c.is_elective,
                   s.building, s.room_number, s.capacity,
                   s.day_of_week, s.start_period, s.end_period,
                   COUNT(tk.ID) as enrolled_count
            FROM teaches t
            JOIN course c ON t.course_id = c.course_id
            JOIN section s ON t.course_id = s.course_id AND t.sec_id = s.sec_id 
                         AND t.semester = s.semester AND t.year = s.year
            LEFT JOIN takes tk ON t.course_id = tk.course_id AND t.sec_id = tk.sec_id 
                             AND t.semester = tk.semester AND t.year = tk.year
            {查询条件}
            GROUP BY t.course_id, t.sec_id, t.semester, t.year
            ORDER BY t.year DESC, t.semester, t.course_id
        """
        
        游标.execute(SQL语句, 查询参数)
        教学任务 = 游标.fetchall()
        
        return {
            "状态": "成功",
            "教学任务数量": len(教学任务),
            "教学任务": 教学任务
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 8.4 获取班级学生名单
@app.get("/teacher/class/{username}/{course_id}/{sec_id}/{semester}/{year}", summary="获取班级学生名单", tags=["教师模块"])
def 获取班级学生名单(username: str, course_id: str, sec_id: str, semester: str, year: int):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 验证教师是否有权限访问该班级
        教师ID = 获取教师ID(username)
        if not 教师ID:
            raise HTTPException(status_code=404, detail="教师信息不存在")
        
        游标.execute("""
            SELECT 1 FROM teaches 
            WHERE teacher_id = %s AND course_id = %s AND sec_id = %s AND semester = %s AND year = %s
        """, (教师ID, course_id, sec_id, semester, year))
        
        if not 游标.fetchone():
            raise HTTPException(status_code=403, detail="无权访问该班级")
        
        # 获取学生名单
        SQL语句 = """
            SELECT s.ID, s.name, s.dept_name, tk.score, tk.regular_score, tk.final_score
            FROM takes tk
            JOIN student s ON tk.ID = s.ID
            WHERE tk.course_id = %s AND tk.sec_id = %s AND tk.semester = %s AND tk.year = %s
            ORDER BY s.ID
        """
        游标.execute(SQL语句, (course_id, sec_id, semester, year))
        学生名单 = 游标.fetchall()
        
        # 转换数据格式
        学生名单列表 = []
        for 学生 in 学生名单:
            学生信息 = {
                "ID": 学生['ID'],
                "name": 学生['name'],
                "dept_name": 学生['dept_name'],
                "score": float(学生['score']) if 学生['score'] else None,
                "regular_score": float(学生['regular_score']) if 学生['regular_score'] else None,
                "final_score": float(学生['final_score']) if 学生['final_score'] else None
            }
            学生名单列表.append(学生信息)
        
        return {
            "状态": "成功",
            "课程信息": {
                "course_id": course_id,
                "sec_id": sec_id,
                "semester": semester,
                "year": year
            },
            "学生数量": len(学生名单列表),
            "学生名单": 学生名单列表
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 8.5 录入/修改学生成绩
@app.put("/teacher/grade/{username}", summary="录入/修改学生成绩", tags=["教师模块"])
def 录入学生成绩(username: str, 成绩信息: 成绩录入信息):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 验证教师是否有权限
        教师ID = 获取教师ID(username)
        if not 教师ID:
            raise HTTPException(status_code=404, detail="教师信息不存在")
        
        游标.execute("""
            SELECT 1 FROM teaches 
            WHERE teacher_id = %s AND course_id = %s AND sec_id = %s AND semester = %s AND year = %s
        """, (教师ID, 成绩信息.课程编号, 成绩信息.班级编号, 成绩信息.学期, 成绩信息.学年))
        
        if not 游标.fetchone():
            raise HTTPException(status_code=403, detail="无权录入该班级成绩")
        
        # 验证学生是否在该班级
        游标.execute("""
            SELECT 1 FROM takes 
            WHERE ID = %s AND course_id = %s AND sec_id = %s AND semester = %s AND year = %s
        """, (成绩信息.学生学号, 成绩信息.课程编号, 成绩信息.班级编号, 成绩信息.学期, 成绩信息.学年))
        
        if not 游标.fetchone():
            raise HTTPException(status_code=404, detail="学生不在该班级中")
        
        # 计算最终成绩
        权重平时 = 成绩信息.权重平时 if 成绩信息.权重平时 else 3
        权重期末 = 成绩信息.权重期末 if 成绩信息.权重期末 else 7
        平时分 = 成绩信息.平时分 if 成绩信息.平时分 is not None else 0
        期末分 = 成绩信息.期末分 if 成绩信息.期末分 is not None else 0
        
        总权重 = 权重平时 + 权重期末
        最终成绩 = (平时分 * 权重平时 / 总权重) + (期末分 * 权重期末 / 总权重)
        
        # 录入成绩到数据库
        SQL语句 = """
            UPDATE takes 
            SET regular_score = %s, 
                final_score = %s, 
                score = %s
            WHERE ID = %s AND course_id = %s AND sec_id = %s AND semester = %s AND year = %s
        """
        游标.execute(SQL语句, (平时分, 期末分, 最终成绩, 
                            成绩信息.学生学号, 成绩信息.课程编号, 
                            成绩信息.班级编号, 成绩信息.学期, 成绩信息.学年))
        连接.commit()
        
        return {
            "状态": "成功",
            "提示": "成绩录入成功",
            "成绩信息": {
                "学生学号": 成绩信息.学生学号,
                "课程编号": 成绩信息.课程编号,
                "平时分": 平时分,
                "期末分": 期末分,
                "权重平时": 权重平时,
                "权重期末": 权重期末,
                "最终成绩": round(最终成绩, 2)
            }
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"成绩录入失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 8.6 获取班级学情统计
@app.get("/teacher/statistics/{username}/{course_id}/{sec_id}/{semester}/{year}", summary="获取班级学情统计", tags=["教师模块"])
def 获取班级学情统计(username: str, course_id: str, sec_id: str, semester: str, year: int):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 验证教师权限
        教师ID = 获取教师ID(username)
        if not 教师ID:
            raise HTTPException(status_code=404, detail="教师信息不存在")
        
        游标.execute("""
            SELECT 1 FROM teaches 
            WHERE teacher_id = %s AND course_id = %s AND sec_id = %s AND semester = %s AND year = %s
        """, (教师ID, course_id, sec_id, semester, year))
        
        if not 游标.fetchone():
            raise HTTPException(status_code=403, detail="无权查看该班级统计")
        
        # 获取学情统计
        SQL语句 = """
            SELECT 
                COUNT(*) as 总人数,
                COUNT(CASE WHEN score IS NOT NULL THEN 1 END) as 已录入人数,
                MAX(CAST(score AS DECIMAL(5,2))) as 最高分,
                MIN(CAST(score AS DECIMAL(5,2))) as 最低分,
                AVG(CAST(score AS DECIMAL(5,2))) as 平均分,
                COUNT(CASE WHEN CAST(score AS DECIMAL(5,2)) >= 60 THEN 1 END) as 及格人数,
                (COUNT(CASE WHEN CAST(score AS DECIMAL(5,2)) >= 60 THEN 1 END) / COUNT(*)) * 100 as 及格率,
                COUNT(CASE WHEN CAST(score AS DECIMAL(5,2)) < 60 THEN 1 END) as `60分以下`,
                COUNT(CASE WHEN CAST(score AS DECIMAL(5,2)) >= 60 AND CAST(score AS DECIMAL(5,2)) < 70 THEN 1 END) as `60-70`,
                COUNT(CASE WHEN CAST(score AS DECIMAL(5,2)) >= 70 AND CAST(score AS DECIMAL(5,2)) < 80 THEN 1 END) as `70-80`,
                COUNT(CASE WHEN CAST(score AS DECIMAL(5,2)) >= 80 AND CAST(score AS DECIMAL(5,2)) < 90 THEN 1 END) as `80-90`,
                COUNT(CASE WHEN CAST(score AS DECIMAL(5,2)) >= 90 THEN 1 END) as `90-100`
            FROM takes 
            WHERE course_id = %s AND sec_id = %s AND semester = %s AND year = %s
        """
        游标.execute(SQL语句, (course_id, sec_id, semester, year))
        统计信息 = 游标.fetchone()
        
        return {
            "状态": "成功",
            "课程信息": {
                "course_id": course_id,
                "sec_id": sec_id,
                "semester": semester,
                "year": year
            },
            "学情统计": 统计信息
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"统计查询失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# ===========================================
# 9. 管理员端功能接口
# ===========================================

# 9.1 获取所有课程列表
@app.get("/admin/courses", summary="获取所有课程列表", tags=["管理员模块"])
def 获取所有课程列表(页码: int = 1, 每页数量: int = 10, 搜索关键词: str = None, 院系: str = None):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 构建查询条件
        查询条件 = ""
        查询参数 = []
        
        if 院系:
            查询条件 = "WHERE dept_name = %s"
            查询参数 = [院系]
        
        if 搜索关键词:
            if 查询条件:
                查询条件 += " AND (course_id LIKE %s OR title LIKE %s)"
            else:
                查询条件 = "WHERE course_id LIKE %s OR title LIKE %s"
            查询参数.extend([f"%{搜索关键词}%", f"%{搜索关键词}%"])
        
        # 获取总数
        SQL语句 = f"SELECT COUNT(*) as 总数 FROM course {查询条件}"
        游标.execute(SQL语句, 查询参数)
        总数 = 游标.fetchone()['总数']
        
        # 计算分页
        偏移量 = (页码 - 1) * 每页数量
        
        # 获取课程列表
        SQL语句 = f"""
            SELECT course_id, title, dept_name, credits, target_grade, target_semester, is_elective
            FROM course {查询条件}
            ORDER BY course_id
            LIMIT %s OFFSET %s
        """
        查询参数.extend([每页数量, 偏移量])
        游标.execute(SQL语句, 查询参数)
        课程列表 = 游标.fetchall()
        
        return {
            "状态": "成功",
            "总数": 总数,
            "页码": 页码,
            "每页数量": 每页数量,
            "课程列表": 课程列表
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 9.2 添加新课程
@app.post("/admin/courses", summary="添加新课程", tags=["管理员模块"])
def 添加新课程(课程信息: dict):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 检查课程是否已存在
        游标.execute("SELECT 1 FROM course WHERE course_id = %s", (课程信息['course_id'],))
        if 游标.fetchone():
            raise HTTPException(status_code=400, detail="课程ID已存在")
        
        # 插入新课程
        SQL语句 = """
            INSERT INTO course (course_id, title, dept_name, credits, target_grade, target_semester, is_elective)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        游标.execute(SQL语句, (
            课程信息['course_id'],
            课程信息['title'],
            课程信息['dept_name'],
            课程信息['credits'],
            课程信息.get('target_grade'),
            课程信息.get('target_semester'),
            课程信息.get('is_elective', 0)
        ))
        连接.commit()
        
        return {
            "状态": "成功",
            "提示": "课程添加成功",
            "课程信息": 课程信息
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"添加失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 9.3 修改课程信息
@app.put("/admin/courses/{course_id}", summary="修改课程信息", tags=["管理员模块"])
def 修改课程信息(course_id: str, 课程信息: dict):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 检查课程是否存在
        游标.execute("SELECT 1 FROM course WHERE course_id = %s", (course_id,))
        if not 游标.fetchone():
            raise HTTPException(status_code=404, detail="课程不存在")
        
        # 更新课程信息
        SQL语句 = """
            UPDATE course 
            SET title = %s, dept_name = %s, credits = %s, target_grade = %s, target_semester = %s, is_elective = %s
            WHERE course_id = %s
        """
        游标.execute(SQL语句, (
            课程信息['title'],
            课程信息['dept_name'],
            课程信息['credits'],
            课程信息.get('target_grade'),
            课程信息.get('target_semester'),
            课程信息.get('is_elective', 0),
            course_id
        ))
        连接.commit()
        
        return {
            "状态": "成功",
            "提示": "课程信息修改成功",
            "课程信息": 课程信息
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"修改失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 9.4 删除课程
@app.delete("/admin/courses/{course_id}", summary="删除课程", tags=["管理员模块"])
def 删除课程(course_id: str):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 检查课程是否存在
        游标.execute("SELECT 1 FROM course WHERE course_id = %s", (course_id,))
        if not 游标.fetchone():
            raise HTTPException(status_code=404, detail="课程不存在")
        
        # 尝试删除课程（会受到外键约束保护）
        SQL语句 = "DELETE FROM course WHERE course_id = %s"
        游标.execute(SQL语句, (course_id,))
        连接.commit()
        
        return {
            "状态": "成功",
            "提示": "课程删除成功"
        }
        
    except pymysql.MySQLError as 报错信息:
        # 外键约束错误处理
        if "foreign key constraint" in str(报错信息).lower():
            raise HTTPException(status_code=400, detail="该课程已有开课记录或选课记录，无法删除")
        raise HTTPException(status_code=500, detail=f"删除失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 9.5 获取排课列表
@app.get("/admin/sections", summary="获取排课列表", tags=["管理员模块"])
def 获取排课列表(学期: str = None, 学年: int = None):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 构建查询条件
        查询条件 = ""
        查询参数 = []
        
        if 学期 and 学年:
            查询条件 = "WHERE s.semester = %s AND s.year = %s"
            查询参数 = [学期, 学年]
        elif 学期:
            查询条件 = "WHERE s.semester = %s"
            查询参数 = [学期]
        elif 学年:
            查询条件 = "WHERE s.year = %s"
            查询参数 = [学年]
        
        # 获取排课列表
        SQL语句 = f"""
            SELECT s.course_id, s.sec_id, s.semester, s.year, s.capacity, 
                   s.building, s.room_number, s.schedule,
                   s.day_of_week, s.start_period, s.end_period,
                   c.title as course_name, c.credits,
                   i.name as teacher_name, i.ID as teacher_id
            FROM section s
            JOIN course c ON s.course_id = c.course_id
            LEFT JOIN teaches t ON s.course_id = t.course_id AND s.sec_id = t.sec_id 
                             AND s.semester = t.semester AND s.year = t.year
            LEFT JOIN instructor i ON t.teacher_id = i.ID
            {查询条件}
            ORDER BY s.year DESC, s.semester, s.course_id, s.sec_id
        """
        游标.execute(SQL语句, 查询参数)
        排课列表 = 游标.fetchall()
        
        return {
            "状态": "成功",
            "排课列表": 排课列表
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 9.6 添加排课
@app.post("/admin/sections", summary="添加排课", tags=["管理员模块"])
def 添加排课(排课信息: dict):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 检查课程是否存在
        游标.execute("SELECT 1 FROM course WHERE course_id = %s", (排课信息['course_id'],))
        if not 游标.fetchone():
            raise HTTPException(status_code=404, detail="课程不存在")
        
        # 检查排课是否已存在
        游标.execute("""
            SELECT 1 FROM section 
            WHERE course_id = %s AND sec_id = %s AND semester = %s AND year = %s
        """, (排课信息['course_id'], 排课信息['sec_id'], 排课信息['semester'], 排课信息['year']))
        
        if 游标.fetchone():
            raise HTTPException(status_code=400, detail="该排课已存在")
        
        # 检查时间冲突（同一教室在同一时间是否已有课程）
        if 排课信息.get('day_of_week') and 排课信息.get('start_period') and 排课信息.get('end_period'):
            # 检查数据库中已有排课的时间字段是否完整，如果不完整，先更新它们
            游标.execute("""
                SELECT course_id, sec_id, semester, year, building, room_number, 
                       day_of_week, start_period, end_period, schedule
                FROM section 
                WHERE building = %s AND room_number = %s 
                AND semester = %s AND year = %s
                AND day_of_week IS NOT NULL AND start_period IS NOT NULL AND end_period IS NOT NULL
                AND day_of_week = %s 
                AND (
                    (start_period <= %s AND end_period >= %s) OR  -- 新课程开始时间在已有课程时间内
                    (start_period <= %s AND end_period >= %s) OR  -- 新课程结束时间在已有课程时间内
                    (start_period >= %s AND end_period <= %s)     -- 新课程完全在已有课程时间内
                )
            """, (
                排课信息['building'], 排课信息['room_number'],
                排课信息['semester'], 排课信息['year'],
                排课信息['day_of_week'],
                排课信息['start_period'], 排课信息['start_period'],
                排课信息['end_period'], 排课信息['end_period'],
                排课信息['start_period'], 排课信息['end_period']
            ))
            
            if 游标.fetchone():
                raise HTTPException(status_code=400, detail="该教室在该时间段已有课程安排，请选择其他时间或教室")
        else:
            # 如果新排课没有设置时间，但数据库中已有排课设置了时间，也检查冲突
            游标.execute("""
                SELECT 1 FROM section 
                WHERE building = %s AND room_number = %s 
                AND semester = %s AND year = %s
                AND day_of_week IS NOT NULL AND start_period IS NOT NULL AND end_period IS NOT NULL
            """, (
                排课信息['building'], 排课信息['room_number'],
                排课信息['semester'], 排课信息['year']
            ))
            
            if 游标.fetchone():
                raise HTTPException(status_code=400, detail="该教室在该学期已有时间安排，请为新排课设置具体时间")
        
        # 插入排课信息
        SQL语句 = """
            INSERT INTO section (course_id, sec_id, semester, year, capacity, building, room_number, 
                               day_of_week, start_period, end_period, schedule)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        游标.execute(SQL语句, (
            排课信息['course_id'],
            排课信息['sec_id'],
            排课信息['semester'],
            排课信息['year'],
            排课信息['capacity'],
            排课信息['building'],
            排课信息['room_number'],
            排课信息.get('day_of_week'),
            排课信息.get('start_period'),
            排课信息.get('end_period'),
            排课信息.get('schedule', '')
        ))
        
        # 如果指定了教师，添加授课关系
        if 排课信息.get('teacher_id'):
            SQL语句 = """
                INSERT INTO teaches (teacher_id, course_id, sec_id, semester, year)
                VALUES (%s, %s, %s, %s, %s)
            """
            游标.execute(SQL语句, (
                排课信息['teacher_id'],
                排课信息['course_id'],
                排课信息['sec_id'],
                排课信息['semester'],
                排课信息['year']
            ))
        
        连接.commit()
        
        return {
            "状态": "成功",
            "提示": "排课添加成功",
            "排课信息": 排课信息
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"添加失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 9.7 删除排课
@app.delete("/admin/sections/{course_id}/{sec_id}/{semester}/{year}", summary="删除排课", tags=["管理员模块"])
def 删除排课(course_id: str, sec_id: str, semester: str, year: int):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 检查排课是否存在
        游标.execute("""
            SELECT 1 FROM section 
            WHERE course_id = %s AND sec_id = %s AND semester = %s AND year = %s
        """, (course_id, sec_id, semester, year))
        
        if not 游标.fetchone():
            raise HTTPException(status_code=404, detail="排课不存在")
        
        # 检查是否有学生选课记录
        游标.execute("""
            SELECT 1 FROM takes 
            WHERE course_id = %s AND sec_id = %s AND semester = %s AND year = %s
        """, (course_id, sec_id, semester, year))
        
        if 游标.fetchone():
            raise HTTPException(status_code=400, detail="该排课已有学生选课记录，无法删除")
        
        # 删除授课关系
        游标.execute("""
            DELETE FROM teaches 
            WHERE course_id = %s AND sec_id = %s AND semester = %s AND year = %s
        """, (course_id, sec_id, semester, year))
        
        # 删除排课记录
        SQL语句 = """
            DELETE FROM section 
            WHERE course_id = %s AND sec_id = %s AND semester = %s AND year = %s
        """
        游标.execute(SQL语句, (course_id, sec_id, semester, year))
        
        连接.commit()
        
        return {
            "状态": "成功",
            "提示": "排课删除成功"
        }
        
    except pymysql.MySQLError as 报错信息:
        # 外键约束错误处理
        if "foreign key constraint" in str(报错信息).lower():
            raise HTTPException(status_code=400, detail="该排课已有相关记录，无法删除")
        raise HTTPException(status_code=500, detail=f"删除失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 9.8 获取教师列表
@app.get("/admin/teachers", summary="获取教师列表", tags=["管理员模块"])
def 获取教师列表(搜索关键词: str = ""):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 构建SQL查询
        SQL语句 = """
            SELECT i.ID, i.name, i.dept_name, i.phone, i.email, d.building
            FROM instructor i
            LEFT JOIN department d ON i.dept_name = d.dept_name
            WHERE 1=1
        """
        参数 = []
        
        if 搜索关键词:
            SQL语句 += " AND (i.ID LIKE %s OR i.name LIKE %s)"
            参数.extend([f'%{搜索关键词}%', f'%{搜索关键词}%'])
        
        SQL语句 += " ORDER BY i.ID"
        
        游标.execute(SQL语句, 参数)
        教师列表 = 游标.fetchall()
        
        return {
            "状态": "成功",
            "教师列表": 教师列表
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 9.9 获取学生列表
@app.get("/admin/students", summary="获取学生列表", tags=["管理员模块"])
def 获取学生列表(搜索关键词: str = ""):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 构建SQL查询
        SQL语句 = """
            SELECT ID, name, dept_name, tot_cred, entrance_year, phone, email
            FROM student
            WHERE 1=1
        """
        参数 = []
        
        if 搜索关键词:
            SQL语句 += " AND (ID LIKE %s OR name LIKE %s)"
            参数.extend([f'%{搜索关键词}%', f'%{搜索关键词}%'])
        
        SQL语句 += " ORDER BY ID"
        
        游标.execute(SQL语句, 参数)
        学生列表 = 游标.fetchall()
        
        return {
            "状态": "成功",
            "学生列表": 学生列表
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 9.8 管理员修改密码
@app.post("/admin/reset-password", summary="管理员修改密码", tags=["管理员模块"])
def 管理员修改密码(用户名: str, 表单: dict):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 验证管理员身份
        游标.execute("SELECT user_id FROM users WHERE username = %s AND role = 'admin' AND password = %s", 
                    (用户名, 表单['旧密码']))
        用户信息 = 游标.fetchone()
        
        if not 用户信息:
            raise HTTPException(status_code=401, detail="旧密码错误或权限不足")
        
        # 更新密码
        SQL语句 = "UPDATE users SET password = %s WHERE username = %s"
        游标.execute(SQL语句, (表单['新密码'], 用户名))
        连接.commit()
        
        return {
            "状态": "成功",
            "提示": "密码修改成功"
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"密码修改失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# ===========================================
# 10. 管理员添加学生和教师接口

# 10.1 添加学生
@app.post("/admin/add-student", summary="添加学生", tags=["管理员模块"])
def 添加学生(表单: 学生信息):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 检查学生是否已存在
        游标.execute("SELECT ID FROM student WHERE ID = %s", (表单.学号,))
        if 游标.fetchone():
            raise HTTPException(status_code=400, detail="学号已存在")
        
        # 检查院系是否存在
        游标.execute("SELECT dept_name FROM department WHERE dept_name = %s", (表单.院系,))
        if not 游标.fetchone():
            raise HTTPException(status_code=400, detail="院系不存在")
        
        # 自动生成账号：stu_ + 姓氏拼音（使用姓名拼音首字母）
        姓氏拼音 = 表单.姓名[0].lower()
        自动生成账号 = f'stu_{姓氏拼音}'
        
        # 检查账号是否已存在，如果存在则添加数字后缀
        原始账号 = 自动生成账号
        序号 = 1
        while True:
            游标.execute("SELECT COUNT(*) as count FROM users WHERE username = %s", ( 自动生成账号,))
            if 游标.fetchone()['count'] == 0:
                break
            自动生成账号 = f'{原始账号}{序号}'
            序号 += 1
        
        # 自动生成密码：123456
        自动生成密码 = '123456'
        
        # 插入用户记录（user_id 自增，不需要指定）
        SQL语句 = "INSERT INTO users (username, password, role) VALUES (%s, %s, 'student')"
        游标.execute(SQL语句, ( 自动生成账号, 自动生成密码))
        
        # 获取 user_id
        游标.execute("SELECT user_id FROM users WHERE username = %s", ( 自动生成账号,))
        用户ID = 游标.fetchone()['user_id']
        
        # 插入学生记录
        SQL语句 = """
            INSERT INTO student (ID, name, dept_name, tot_cred, entrance_year, phone, email, user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        游标.execute(SQL语句, (
            表单.学号,
            表单.姓名,
            表单.院系,
            表单.已修学分,
            表单.入学年份,
            表单.电话,
            表单.邮箱,
            用户ID
        ))
        
        连接.commit()
        
        return {
            "状态": "成功",
            "提示": "学生添加成功"
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"添加失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 10.2 添加教师
@app.post("/admin/add-teacher", summary="添加教师", tags=["管理员模块"])
def 添加教师(表单: 教师信息):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 检查教师是否已存在
        游标.execute("SELECT ID FROM instructor WHERE ID = %s", (表单.教师ID,))
        if 游标.fetchone():
            raise HTTPException(status_code=400, detail="教师ID已存在")
        
        # 检查院系是否存在
        游标.execute("SELECT dept_name FROM department WHERE dept_name = %s", (表单.院系,))
        if not 游标.fetchone():
            raise HTTPException(status_code=400, detail="院系不存在")
        
        # 自动生成账号：tea_ + 姓氏拼音（使用姓名拼音首字母）
        姓氏拼音 = 表单.姓名[0].lower()
        自动生成账号 = f'tea_{姓氏拼音}'
        
        # 检查账号是否已存在，如果存在则添加数字后缀
        原始账号 = 自动生成账号
        序号 = 1
        while True:
            游标.execute("SELECT COUNT(*) as count FROM users WHERE username = %s", ( 自动生成账号,))
            if 游标.fetchone()['count'] == 0:
                break
            自动生成账号 = f'{原始账号}{序号}'
            序号 += 1
        
        # 自动生成密码：123456
        自动生成密码 = '123456'
        
        # 插入用户记录（user_id 自增，不需要指定）
        SQL语句 = "INSERT INTO users (username, password, role) VALUES (%s, %s, 'teacher')"
        游标.execute(SQL语句, ( 自动生成账号, 自动生成密码))
        
        # 获取 user_id
        游标.execute("SELECT user_id FROM users WHERE username = %s", ( 自动生成账号,))
        用户ID = 游标.fetchone()['user_id']
        
        # 插入教师记录
        SQL语句 = """
            INSERT INTO instructor (ID, name, dept_name, phone, email, user_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        游标.execute(SQL语句, (
            表单.教师ID,
            表单.姓名,
            表单.院系,
            表单.电话,
            表单.邮箱,
            用户ID
        ))
        
        连接.commit()
        
        return {
            "状态": "成功",
            "提示": "教师添加成功"
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"添加失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 10.3 删除学生
@app.delete("/admin/student/{student_id}", summary="删除学生", tags=["管理员模块"])
def 删除学生(student_id: str):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 检查学生是否存在
        游标.execute("SELECT user_id FROM student WHERE ID = %s", (student_id,))
        学生信息 = 游标.fetchone()
        
        if not 学生信息:
            raise HTTPException(status_code=404, detail="学生不存在")
        
        # 删除学生记录
        SQL语句 = "DELETE FROM student WHERE ID = %s"
        游标.execute(SQL语句, (student_id,))
        
        # 删除用户记录
        SQL语句 = "DELETE FROM users WHERE user_id = %s"
        游标.execute(SQL语句, (学生信息['user_id'],))
        
        连接.commit()
        
        return {
            "状态": "成功",
            "提示": "学生删除成功"
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"删除失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 10.4 删除教师
@app.delete("/admin/teacher/{teacher_id}", summary="删除教师", tags=["管理员模块"])
def 删除教师(teacher_id: str):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 检查教师是否存在
        游标.execute("SELECT user_id FROM instructor WHERE ID = %s", (teacher_id,))
        教师信息 = 游标.fetchone()
        
        if not 教师信息:
            raise HTTPException(status_code=404, detail="教师不存在")
        
        # 删除教师记录
        SQL语句 = "DELETE FROM instructor WHERE ID = %s"
        游标.execute(SQL语句, (teacher_id,))
        
        # 删除用户记录
        SQL语句 = "DELETE FROM users WHERE user_id = %s"
        游标.execute(SQL语句, (教师信息['user_id'],))
        
        连接.commit()
        
        return {
            "状态": "成功",
            "提示": "教师删除成功"
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"删除失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# ===========================================
# 5. 学生端功能接口

# 5.1 密码重置
@app.post("/student/reset-password", summary="重置密码", tags=["学生模块"])
def 重置密码(用户名: str, 表单: 密码重置信息):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 验证旧密码
        SQL语句 = "SELECT user_id FROM users WHERE username = %s AND password = %s AND role = 'student'"
        游标.execute(SQL语句, (用户名, 表单.旧密码))
        用户信息 = 游标.fetchone()
        
        if not 用户信息:
            raise HTTPException(status_code=401, detail="旧密码错误")
        
        # 更新密码
        SQL语句 = "UPDATE users SET password = %s WHERE username = %s"
        游标.execute(SQL语句, (表单.新密码, 用户名))
        连接.commit()
        
        return {
            "状态": "成功",
            "提示": "密码重置成功"
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"密码重置失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 5.2 获取学生档案
@app.get("/student/profile/{username}", summary="获取学生档案", tags=["学生模块"])
def 获取学生档案(username: str):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 获取学生详细信息
        SQL语句 = """
            SELECT s.ID, s.name, s.dept_name, s.tot_cred, s.entrance_year, s.phone, s.email, 
                   d.building, d.budget, u.username
            FROM student s 
            LEFT JOIN department d ON s.dept_name = d.dept_name
            LEFT JOIN users u ON s.user_id = u.user_id
            WHERE u.username = %s
        """
        游标.execute(SQL语句, (username,))
        学生档案 = 游标.fetchone()
        
        if not 学生档案:
            raise HTTPException(status_code=404, detail="学生信息不存在")
        
        return {
            "状态": "成功",
            "学生档案": 学生档案
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 5.3 更新联系方式
@app.put("/student/contact/{username}", summary="更新联系方式", tags=["学生模块"])
def 更新联系方式(username: str, 表单: 联系方式更新):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 获取学生ID
        学生ID = 获取学生ID(username)
        if not 学生ID:
            raise HTTPException(status_code=404, detail="学生信息不存在")
        
        # 构建更新语句
        更新字段 = []
        参数列表 = []
        
        if 表单.手机号 is not None:
            更新字段.append("phone = %s")
            参数列表.append(表单.手机号)
        
        if 表单.邮箱 is not None:
            更新字段.append("email = %s")
            参数列表.append(表单.邮箱)
        
        if not 更新字段:
            raise HTTPException(status_code=400, detail="没有提供要更新的字段")
        
        参数列表.append(学生ID)
        SQL语句 = f"UPDATE student SET {', '.join(更新字段)} WHERE ID = %s"
        游标.execute(SQL语句, 参数列表)
        连接.commit()
        
        return {
            "状态": "成功",
            "提示": "联系方式更新成功"
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"更新失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 5.4 获取全校课程列表
@app.get("/student/courses", summary="获取全校课程列表", tags=["学生模块"])
def 获取全校课程列表(学期: str = None, 学年: int = None, 学生用户名: str = None):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 如果没有指定学期和学年，根据当前时间自动确定
        if 学期 is None or 学年 is None:
            游标.execute("SELECT MONTH(NOW()) AS month, YEAR(NOW()) AS year")
            时间信息 = 游标.fetchone()
            月份 = 时间信息['month']
            年份 = 时间信息['year']
            if 月份 >= 7:
                学期 = "Fall"
                学年 = 年份
            else:
                学期 = "Spring"
                学年 = 年份
        
        # 如果提供了学生用户名，获取学生的院系和入学年份
        学生院系 = None
        入学年份 = None
        if 学生用户名:
            游标.execute("SELECT dept_name, entrance_year FROM student WHERE user_id = (SELECT user_id FROM users WHERE username = %s)", (学生用户名,))
            学生信息 = 游标.fetchone()
            if 学生信息:
                学生院系 = 学生信息['dept_name']
                入学年份 = 学生信息['entrance_year']
        
        # 计算学生年级
        年级 = None
        if 入学年份 is not None:
            游标.execute("SELECT MONTH(NOW()) AS month, YEAR(NOW()) AS year")
            时间信息 = 游标.fetchone()
            月份 = 时间信息['month']
            年份 = 时间信息['year']
            if 月份 >= 7:
                年级 = 年份 - 入学年份 + 1
            else:
                年级 = 年份 - 入学年份
        
        # 获取当前学期的所有课程
        if 学生院系 and 年级 is not None:
            SQL语句 = """
                SELECT s.course_id, c.title, s.sec_id, s.semester, s.year, 
                       s.building, s.room_number, 
                       s.day_of_week, s.start_period, s.end_period,
                       s.capacity,
                       i.name as instructor_name,
                       c.is_elective,
                       (SELECT COUNT(*) FROM takes t 
                        WHERE t.course_id = s.course_id AND t.sec_id = s.sec_id 
                        AND t.semester = s.semester AND t.year = s.year 
                        AND t.status = 'selected') as enrolled_count
                FROM section s
                JOIN course c ON s.course_id = c.course_id
                LEFT JOIN teaches te ON s.course_id = te.course_id AND s.sec_id = te.sec_id 
                    AND s.semester = te.semester AND s.year = te.year
                LEFT JOIN instructor i ON te.teacher_id = i.ID
                WHERE s.semester = %s AND s.year = %s
                AND (
                    c.is_elective = 1
                    OR c.dept_name = %s
                )
                AND (
                    c.target_grade IS NULL
                    OR c.target_grade = 0
                    OR c.target_grade = %s
                )
                ORDER BY c.title, s.sec_id
            """
            游标.execute(SQL语句, (学期, 学年, 学生院系, 年级))
        else:
            SQL语句 = """
                SELECT s.course_id, c.title, s.sec_id, s.semester, s.year, 
                       s.building, s.room_number, 
                       s.day_of_week, s.start_period, s.end_period,
                       s.capacity,
                       i.name as instructor_name,
                       c.is_elective,
                       (SELECT COUNT(*) FROM takes t 
                        WHERE t.course_id = s.course_id AND t.sec_id = s.sec_id 
                        AND t.semester = s.semester AND t.year = s.year 
                        AND t.status = 'selected') as enrolled_count
                FROM section s
                JOIN course c ON s.course_id = c.course_id
                LEFT JOIN teaches te ON s.course_id = te.course_id AND s.sec_id = te.sec_id 
                    AND s.semester = te.semester AND s.year = te.year
                LEFT JOIN instructor i ON te.teacher_id = i.ID
                WHERE s.semester = %s AND s.year = %s
                ORDER BY c.title, s.sec_id
            """
            游标.execute(SQL语句, (学期, 学年))
        课程列表 = 游标.fetchall()
        
        return {
            "状态": "成功",
            "学期": 学期,
            "学年": 学年,
            "课程数量": len(课程列表),
            "课程列表": 课程列表
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 5.5 选课
@app.post("/student/select-course/{username}", summary="选课", tags=["学生模块"])
def 选课(username: str, 表单: 选课信息):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 获取学生ID
        学生ID = 获取学生ID(username)
        if not 学生ID:
            raise HTTPException(status_code=404, detail="学生信息不存在")
        
        # 检查是否已经选过该课程
        SQL语句 = """
            SELECT * FROM takes 
            WHERE ID = %s AND course_id = %s AND sec_id = %s 
            AND semester = %s AND year = %s
        """
        游标.execute(SQL语句, (学生ID, 表单.课程编号, 表单.班级编号, 表单.学期, 表单.学年))
        已选课程 = 游标.fetchone()
        
        if 已选课程:
            raise HTTPException(status_code=400, detail="已经选过该课程")
        
        # 检查课程是否是公选课
        游标.execute("SELECT is_elective FROM course WHERE course_id = %s", (表单.课程编号,))
        课程信息 = 游标.fetchone()
        是公选课 = 课程信息 and 课程信息.get('is_elective') == 1
        
        # 检查学生已选的课程（包括公选课）
        游标.execute("""
            SELECT s.course_id, c.title, s.day_of_week, s.start_period, s.end_period,
                   s.building, s.room_number
            FROM takes t
            JOIN section s ON t.course_id = s.course_id 
                AND t.sec_id = s.sec_id AND t.semester = s.semester AND t.year = s.year
            JOIN course c ON s.course_id = c.course_id
            WHERE t.ID = %s AND t.status = 'selected'
            AND s.semester = %s AND s.year = %s
        """, (学生ID, 表单.学期, 表单.学年))
        已选课程列表 = 游标.fetchall()
        
        # 检查是否有时间冲突（包括公选课）
        游标.execute("""
            SELECT day_of_week, start_period, end_period
            FROM section
            WHERE course_id = %s AND sec_id = %s
            AND semester = %s AND year = %s
        """, (表单.课程编号, 表单.班级编号, 表单.学期, 表单.学年))
        新课程时间 = 游标.fetchone()
        
        if 新课程时间:
            新课程星期 = 新课程时间['day_of_week']
            新课程开始节 = 新课程时间['start_period']
            新课程结束节 = 新课程时间['end_period']
            
            for 已选课程 in 已选课程列表:
                已选课程星期 = 已选课程['day_of_week']
                已选课程开始节 = 已选课程['start_period']
                已选课程结束节 = 已选课程['end_period']
                
                # 检查时间是否冲突（同一天且时间段重叠）
                if 新课程星期 == 已选课程星期:
                    if not (新课程结束节 < 已选课程开始节 or 新课程开始节 > 已选课程结束节):
                        raise HTTPException(
                            status_code=400, 
                            detail=f"您选修的课程与已选课程{已选课程['title']}({已选课程['course_id']})时间冲突，请调整选课"
                        )
        
        # 如果不是公选课，检查先修课
        if not 是公选课:
            # 查询该课程的先修课
            游标.execute("SELECT prereq_id FROM prereq WHERE course_id = %s", (表单.课程编号,))
            先修课列表 = 游标.fetchall()
            
            if 先修课列表:
                # 查询学生已修且及格的先修课
                先修课ID列表 = [先修['prereq_id'] for 先修 in 先修课列表]
                先修课ID元组 = tuple(先修课ID列表)
                
                # 统一使用 IN 语法处理一个或多个先修课
                if len(先修课ID元组) == 1:
                    SQL语句 = f"""
                        SELECT COUNT(*) as count FROM takes 
                        WHERE ID = %s AND course_id = '{先修课ID元组[0]}' AND score >= 60
                    """
                else:
                    先修课ID字符串 = ','.join([f"'{id}'" for id in 先修课ID元组])
                    SQL语句 = f"""
                        SELECT COUNT(*) as count FROM takes 
                        WHERE ID = %s AND course_id IN ({先修课ID字符串}) AND score >= 60
                    """
                游标.execute(SQL语句, (学生ID,))
                
                已修先修课数量 = 游标.fetchone()['count']
                
                if 已修先修课数量 < len(先修课列表):
                    # 找出未修的先修课
                    未修先修课 = []
                    for 先修 in 先修课列表:
                        先修课ID = 先修['prereq_id']
                        游标.execute("SELECT title FROM course WHERE course_id = %s", (先修课ID,))
                        先修课信息 = 游标.fetchone()
                        游标.execute("SELECT * FROM takes WHERE ID = %s AND course_id = %s", (学生ID, 先修课ID))
                        已选先修 = 游标.fetchone()
                        
                        先修课成绩 = 已选先修['score'] if 已选先修 and 'score' in 已选先修 and 已选先修['score'] is not None else 0
                        if not 已选先修 or 先修课成绩 < 60:
                            未修先修课.append(先修课信息['title'] if 先修课信息 else 先修课ID)
                    
                    raise HTTPException(status_code=400, detail=f"您未修完以下先修课：{', '.join(未修先修课)}")
                else:
                    # 已修完所有先修课，检查是否有时间冲突
                    游标.execute("""
                        SELECT s.course_id, c.title, s.day_of_week, s.start_period, s.end_period,
                               s.building, s.room_number
                        FROM section s
                        JOIN course c ON s.course_id = c.course_id
                        WHERE s.course_id IN (SELECT prereq_id FROM prereq WHERE course_id = %s)
                        AND s.semester = %s AND s.year = %s
                    """, (表单.课程编号, 表单.学期, 表单.学年))
                    本学期先修课 = 游标.fetchall()
                    
                    if 本学期先修课:
                        先修课名称列表 = [f'{课["title"]}({课["course_id"]})' for 课 in 本学期先修课]
                        raise HTTPException(status_code=400, detail=f"您选修的课程与先修课{', '.join(先修课名称列表)}时间冲突，请先修完先修课")
        
        # 插入选课记录
        SQL语句 = """
            INSERT INTO takes (ID, course_id, sec_id, semester, year, status, select_time)
            VALUES (%s, %s, %s, %s, %s, 'selected', NOW())
        """
        游标.execute(SQL语句, (学生ID, 表单.课程编号, 表单.班级编号, 表单.学期, 表单.学年))
        连接.commit()
        
        return {
            "状态": "成功",
            "提示": "选课成功"
        }
        
    except pymysql.MySQLError as 报错信息:
        # 如果是触发器抛出的容量限制错误
        if "capacity" in str(报错信息).lower():
            raise HTTPException(status_code=400, detail="课程容量已满，无法选课")
        raise HTTPException(status_code=500, detail=f"选课失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 5.6 退课
@app.delete("/student/drop-course/{username}", summary="退课", tags=["学生模块"])
def 退课(username: str, 课程编号: str, 班级编号: str, 学期: str, 学年: int):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 获取学生ID
        学生ID = 获取学生ID(username)
        if not 学生ID:
            raise HTTPException(status_code=404, detail="学生信息不存在")
        
        # 检查是否已有成绩
        SQL语句 = """
            SELECT score FROM takes 
            WHERE ID = %s AND course_id = %s AND sec_id = %s 
            AND semester = %s AND year = %s
        """
        游标.execute(SQL语句, (学生ID, 课程编号, 班级编号, 学期, 学年))
        选课记录 = 游标.fetchone()
        
        if not 选课记录:
            raise HTTPException(status_code=404, detail="未找到选课记录")
        
        if 选课记录['score'] is not None:
            raise HTTPException(status_code=400, detail="该课程已有成绩，无法退课")
        
        # 删除选课记录
        SQL语句 = """
            DELETE FROM takes 
            WHERE ID = %s AND course_id = %s AND sec_id = %s 
            AND semester = %s AND year = %s
        """
        游标.execute(SQL语句, (学生ID, 课程编号, 班级编号, 学期, 学年))
        
        连接.commit()
        
        return {
            "状态": "成功",
            "提示": "退课成功"
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"退课失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 5.7 获取个人课表
@app.get("/student/schedule/{username}", summary="获取个人课表", tags=["学生模块"])
def 获取个人课表(username: str, 学期: str = "Fall", 学年: int = 2024):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 获取学生ID
        学生ID = 获取学生ID(username)
        if not 学生ID:
            raise HTTPException(status_code=404, detail="学生信息不存在")
        
        # 使用视图获取课表
        SQL语句 = """
            SELECT * FROM v_student_schedule 
            WHERE student_id = %s AND semester = %s AND year = %s
            ORDER BY class_time
        """
        游标.execute(SQL语句, (学生ID, 学期, 学年))
        课表 = 游标.fetchall()
        
        return {
            "状态": "成功",
            "学期": 学期,
            "学年": 学年,
            "课程数量": len(课表),
            "课表": 课表
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 5.8 获取成绩单
@app.get("/student/transcript/{username}", summary="获取成绩单", tags=["学生模块"])
def 获取成绩单(username: str):
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 获取学生ID
        学生ID = 获取学生ID(username)
        if not 学生ID:
            raise HTTPException(status_code=404, detail="学生信息不存在")
        
        # 使用视图获取成绩单
        SQL语句 = "SELECT * FROM v_student_transcript WHERE student_id = %s ORDER BY year DESC, semester"
        游标.execute(SQL语句, (学生ID,))
        成绩单 = 游标.fetchall()
        
        # 计算总学分（只计算已修且及格的课程）和加权平均分（包括所有课程）
        总学分 = 0
        总加权分 = 0
        总学分计数 = 0
        
        for 成绩 in 成绩单:
            if 成绩['grade'] is not None:
                总加权分 += float(成绩['grade']) * float(成绩['course_credits'])
                总学分计数 += float(成绩['course_credits'])
                if float(成绩['grade']) >= 60:
                    总学分 += float(成绩['course_credits'])
        
        加权平均分 = 总加权分 / 总学分计数 if 总学分计数 > 0 else 0
        
        return {
            "状态": "成功",
            "课程数量": len(成绩单),
            "总学分": 总学分,
            "加权平均分": round(加权平均分, 2),
            "成绩单": 成绩单
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 6. API 服务信息
@app.get("/api", summary="API 服务信息", tags=["系统"])
def API服务信息():
    return {
        "状态": "成功",
        "提示": "教务系统后端API服务已启动",
        "API文档": "http://127.0.0.1:8000/docs",
        "系统信息": {
            "系统名称": "教务系统学生端",
            "版本": "1.0.0",
            "开发语言": "Python + FastAPI",
            "数据库": "MySQL"
        }
    }

# 7. 查询数据库表结构
@app.get("/tables", summary="查询数据库中的表", tags=["数据库管理"])
def 查询数据库表():
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        # 查询数据库中的所有表
        SQL语句 = "SHOW TABLES"
        游标.execute(SQL语句)
        
        # 获取所有表名
        表列表 = 游标.fetchall()
        
        # 提取表名并返回
        表名列表 = [list(表.values())[0] for 表 in 表列表]
        
        return {
            "状态": "成功",
            "数据库": "school_db",
            "表数量": len(表名列表),
            "表列表": 表名列表
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"数据库查询失败: {str(报错信息)}")
    finally:
        # 查完一定要关门
        if 连接:
            连接.close()

# 9.11 获取院系列表
@app.get("/departments", summary="获取院系列表", tags=["通用模块"])
def 获取院系列表():
    连接 = None
    try:
        连接 = 连接数据库()
        游标 = 连接.cursor()
        
        SQL语句 = "SELECT dept_name FROM department ORDER BY dept_name"
        游标.execute(SQL语句)
        院系列表 = 游标.fetchall()
        
        return {
            "状态": "成功",
            "院系列表": 院系列表
        }
        
    except pymysql.MySQLError as 报错信息:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(报错信息)}")
    finally:
        if 连接:
            连接.close()

# 8. 启动服务器
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
