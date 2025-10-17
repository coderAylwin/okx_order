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
    'host': 'rm-t4nea067q32i31k9aro.mysql.singapore.rds.aliyuncs.com',     # 本地MySQL
    'port': 3306,
    'user': 'payment_pro',
    'password': 'nS4kO7tG1jH7cI6oR4b',           # 请修改为您的MySQL密码
    'database': 'quantify',    # 数据库名称
    'auth_plugin': '',
    'pool_name': 'okx_pool',  # 添加简短的连接池名称
    'pool_size': 10,  # 设置连接池大小
}