#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# 同事数据库配置
DATABASE_CONFIG = {
    'host': '192.168.5.246',
    'port': 3306,
    'user': 'root',
    'password': '',           # 请修改为您的MySQL密码
    'database': 'quantify'    # 数据库名称
}

# 自己本地数据库配置
LOCAL_DATABASE_CONFIG = {
    'host': '127.0.0.1',     # 本地MySQL
    'port': 3306,
    'user': 'root',
    'password': '',           # 请修改为您的MySQL密码
    'database': 'quantify'    # 数据库名称
}

# LOCAL_DATABASE_CONFIG = {
#     'host': 'rm-t4nea067q32i31k9aro.mysql.singapore.rds.aliyuncs.com',     # 本地MySQL
#     'port': 3306,
#     'user': 'payment_pro',
#     'password': 'nS4kO7tG1jH7cI6oR4b',           # 请修改为您的MySQL密码
#     'database': 'quantify',    # 数据库名称
#     'charset': 'utf8mb4',
# }