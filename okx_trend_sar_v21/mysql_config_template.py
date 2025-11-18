#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MySQL数据库配置文件
请根据你的实际MySQL配置修改以下参数
"""

# MySQL数据库配置
LOCAL_DATABASE_CONFIG = {
    'host': 'localhost',      # MySQL服务器地址
    'port': 3306,             # MySQL端口
    'user': 'root',           # MySQL用户名
    'password': '',           # MySQL密码（请填写你的密码）
    'database': 'quantify', # 数据库名（就是你创建表的那个数据库）
    'charset': 'utf8mb4'      # 字符集
}

# 使用说明：
# 1. 复制这个文件为 database_config.py
# 2. 修改上面的配置信息（主要是password和database）
# 3. 运行测试: python3 test_mysql_connection.py

