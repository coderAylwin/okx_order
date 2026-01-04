#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Odaily RSS 数据库服务
用于管理 Odaily 快讯数据的存储和查询
"""

import pymysql
from datetime import datetime
import logging
import html


class OdailyDatabaseService:
    """Odaily RSS 数据库服务类"""
    
    def __init__(self, host='localhost', port=3306, user='root', password='', database='quantify'):
        """
        初始化数据库连接
        
        Args:
            host: 数据库主机
            port: 数据库端口
            user: 数据库用户名
            password: 数据库密码
            database: 数据库名称
        """
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.connection = None
        
    def connect(self):
        """建立数据库连接"""
        try:
            self.connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                charset='utf8mb4'
            )
            logging.info(f"成功连接到数据库: {self.host}:{self.port}/{self.database}")
            return True
        except Exception as e:
            logging.error(f"数据库连接失败: {e}")
            return False
    
    def disconnect(self):
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()
            self.connection = None
            logging.info("数据库连接已关闭")
    
    def create_tables(self):
        """创建 Odaily 快讯数据表"""
        if not self.connection:
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            # 创建快讯数据表
            create_table = """
            CREATE TABLE IF NOT EXISTS odaily_newsflash (
                id INT AUTO_INCREMENT PRIMARY KEY,
                title VARCHAR(500) NOT NULL COMMENT '标题',
                link VARCHAR(1000) NOT NULL COMMENT '链接',
                description TEXT COMMENT '描述内容（HTML格式）',
                description_text TEXT COMMENT '描述内容（纯文本）',
                pub_date DATETIME NOT NULL COMMENT '发布时间',
                category VARCHAR(100) DEFAULT NULL COMMENT '分类',
                author VARCHAR(100) DEFAULT NULL COMMENT '作者',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_link (link),
                INDEX idx_pub_date (pub_date),
                INDEX idx_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Odaily快讯数据表';
            """
            
            cursor.execute(create_table)
            self.connection.commit()
            logging.info("Odaily快讯数据表创建/更新成功")
            return True
            
        except Exception as e:
            self.connection.rollback()
            logging.error(f"创建表失败: {e}")
            return False
        finally:
            cursor.close()
    
    def get_existing_links(self):
        """
        查询数据库中已存在的 link 列表
        
        Returns:
            set: 已存在的 link 集合
        """
        if not self.connection:
            if not self.connect():
                return set()
        
        cursor = self.connection.cursor()
        try:
            sql = "SELECT link FROM odaily_newsflash"
            cursor.execute(sql)
            results = cursor.fetchall()
            links = {row[0] for row in results}
            logging.info(f"数据库中已存在 {len(links)} 条快讯记录")
            return links
        except Exception as e:
            logging.error(f"查询已存在link失败: {e}")
            return set()
        finally:
            cursor.close()
    
    def save_newsflash(self, title, link, description, description_text, pub_date, category=None, author=None):
        """
        保存快讯数据
        
        Args:
            title: 标题
            link: 链接（唯一标识符）
            description: 描述内容（HTML格式）
            description_text: 描述内容（纯文本）
            pub_date: 发布时间（datetime对象）
            category: 分类
            author: 作者
            
        Returns:
            bool: 保存是否成功
        """
        if not self.connection:
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            sql = """
            INSERT INTO odaily_newsflash 
            (title, link, description, description_text, pub_date, category, author)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                title = VALUES(title),
                description = VALUES(description),
                description_text = VALUES(description_text),
                pub_date = VALUES(pub_date),
                category = VALUES(category),
                author = VALUES(author),
                updated_at = CURRENT_TIMESTAMP
            """
            cursor.execute(sql, (title, link, description, description_text, pub_date, category, author))
            self.connection.commit()
            logging.debug(f"快讯保存成功: {title[:50]}...")
            return True
            
        except Exception as e:
            self.connection.rollback()
            logging.error(f"保存快讯失败: {e}")
            return False
        finally:
            cursor.close()

