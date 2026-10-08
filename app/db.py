"""MySQL 连接。每个请求独立连接；写入操作显式提交或回滚。"""
from contextlib import contextmanager
import pymysql
from pymysql.cursors import DictCursor

from .config import settings


def connect():
    return pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
        connect_timeout=5,
        read_timeout=10,
        write_timeout=10,
    )


@contextmanager
def transaction():
    connection = connect()
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


@contextmanager
def read_connection():
    connection = connect()
    try:
        yield connection
    finally:
        connection.close()
