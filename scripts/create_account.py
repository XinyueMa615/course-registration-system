"""为演示数据建立登录账号；密码交互输入，绝不写入脚本或命令行历史。"""
import argparse
from getpass import getpass

from app.db import transaction
from app.security import hash_password


def main():
    parser = argparse.ArgumentParser(description="绑定已有学生或教师档案的登录账号")
    parser.add_argument("username")
    parser.add_argument("role", choices=["STUDENT", "PROFESSOR", "REGISTRAR"])
    parser.add_argument("--person-id", help="学生填 S001，教师填 P001；教务账号不用填")
    args = parser.parse_args()
    if (args.role == "REGISTRAR") != (args.person_id is None):
        parser.error("学生/教师必须提供 --person-id，教务账号不能提供")
    password = getpass("设置密码（至少 10 个字符）：")
    if password != getpass("再次输入密码："):
        parser.error("两次密码不一致")
    digest = hash_password(password)
    with transaction() as connection, connection.cursor() as cursor:
        if args.person_id:
            table = "student_profile" if args.role == "STUDENT" else "professor_profile"
            key = "student_id" if args.role == "STUDENT" else "professor_id"
            cursor.execute(f"SELECT user_id FROM {table} WHERE {key}=%s FOR UPDATE", (args.person_id,))
            person = cursor.fetchone()
            if not person:
                parser.error("档案不存在；请先执行演示数据脚本或由教务创建档案")
            if person["user_id"] is not None:
                parser.error("该档案已经绑定账号")
        cursor.execute(
            "INSERT INTO user_account (username,password_hash,role) VALUES (%s,%s,%s)",
            (args.username, digest, args.role),
        )
        user_id = cursor.lastrowid
        if args.person_id:
            cursor.execute(
                f"UPDATE {table} SET user_id=%s WHERE {key}=%s",
                (user_id, args.person_id),
            )
    print(f"已创建 {args.role} 账号 {args.username}。")


if __name__ == "__main__":
    main()
