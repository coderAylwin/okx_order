#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
币安市场数据数据库服务
用于管理币安市场数据的存储和查询
包括：持仓量数据、主动买卖量数据
"""

import pymysql
from datetime import datetime
import logging
import traceback


class BinanceDatabaseService:
    """币安市场数据数据库服务类"""
    
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
            logging.debug("数据库连接已关闭")
    
    def create_tables(self):
        """创建币安市场数据表"""
        if not self.connection:
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            # 币安持仓量表
            create_oi_table = """
            CREATE TABLE IF NOT EXISTS binance_open_interest (
                id INT AUTO_INCREMENT PRIMARY KEY,
                coin VARCHAR(10) NOT NULL COMMENT '币种（BTC/ETH/SOL）',
                symbol VARCHAR(50) NOT NULL COMMENT '合约符号（如BTCUSDT）',
                ts DATETIME NOT NULL COMMENT '时间戳（UTC+8）',
                sum_open_interest DECIMAL(30, 8) NOT NULL COMMENT '总持仓量（币）',
                sum_open_interest_value DECIMAL(30, 8) NOT NULL COMMENT '总持仓量价值（USD）',
                cmc_circulating_supply DECIMAL(30, 8) DEFAULT NULL COMMENT 'CMC流通供应量',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_coin_symbol_ts (coin, symbol, ts),
                INDEX idx_coin_ts (coin, ts),
                INDEX idx_ts (ts)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='币安持仓量表';
            """
            
            # 币安主动买卖量表
            create_taker_table = """
            CREATE TABLE IF NOT EXISTS binance_taker_volume (
                id INT AUTO_INCREMENT PRIMARY KEY,
                coin VARCHAR(10) NOT NULL COMMENT '币种（BTC/ETH/SOL）',
                symbol VARCHAR(50) NOT NULL COMMENT '合约符号（如BTCUSDT）',
                ts DATETIME NOT NULL COMMENT '时间戳（UTC+8）',
                buy_vol DECIMAL(30, 8) NOT NULL COMMENT '主动买入量',
                sell_vol DECIMAL(30, 8) NOT NULL COMMENT '主动卖出量',
                buy_sell_ratio DECIMAL(10, 4) NOT NULL COMMENT '买卖比（buyVol/sellVol）',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_coin_symbol_ts (coin, symbol, ts),
                INDEX idx_coin_ts (coin, ts),
                INDEX idx_ts (ts)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='币安主动买卖量表';
            """
            
            # 币安基差表
            create_basis_table = """
            CREATE TABLE IF NOT EXISTS binance_basis (
                id INT AUTO_INCREMENT PRIMARY KEY,
                coin VARCHAR(10) NOT NULL COMMENT '币种（BTC/ETH/SOL）',
                pair VARCHAR(50) NOT NULL COMMENT '交易对（如BTCUSDT）',
                contract_type VARCHAR(20) NOT NULL COMMENT '合约类型（PERPETUAL等）',
                ts DATETIME NOT NULL COMMENT '时间戳（UTC+8）',
                index_price DECIMAL(30, 8) NOT NULL COMMENT '指数价格',
                futures_price DECIMAL(30, 8) NOT NULL COMMENT '期货价格',
                basis DECIMAL(30, 8) NOT NULL COMMENT '基差（futuresPrice - indexPrice）',
                basis_rate DECIMAL(10, 8) DEFAULT NULL COMMENT '基差率',
                annualized_basis_rate DECIMAL(10, 8) DEFAULT NULL COMMENT '年化基差率',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_coin_pair_contract_ts (coin, pair, contract_type, ts),
                INDEX idx_coin_ts (coin, ts),
                INDEX idx_ts (ts)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='币安基差表';
            """
            
            # 币安多空比表
            create_ls_table = """
            CREATE TABLE IF NOT EXISTS binance_long_short_ratio (
                id INT AUTO_INCREMENT PRIMARY KEY,
                coin VARCHAR(10) NOT NULL COMMENT '币种（BTC/ETH/SOL）',
                symbol VARCHAR(50) NOT NULL COMMENT '合约符号（如BTCUSDT）',
                ts DATETIME NOT NULL COMMENT '时间戳（UTC+8）',
                top_position_ratio DECIMAL(10, 4) DEFAULT NULL COMMENT '大户持仓量多空比（topLongShortPositionRatio）',
                top_account_ratio DECIMAL(10, 4) DEFAULT NULL COMMENT '大户账户数多空比（topLongShortAccountRatio）',
                global_account_ratio DECIMAL(10, 4) DEFAULT NULL COMMENT '多空持仓人数比（globalLongShortAccountRatio）',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_coin_symbol_ts (coin, symbol, ts),
                INDEX idx_coin_ts (coin, ts),
                INDEX idx_ts (ts)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='币安多空比表';
            """
            
            # 币安资金费率表
            create_funding_table = """
            CREATE TABLE IF NOT EXISTS binance_funding_rate (
                id INT AUTO_INCREMENT PRIMARY KEY,
                coin VARCHAR(10) NOT NULL COMMENT '币种（BTC/ETH/SOL）',
                symbol VARCHAR(50) NOT NULL COMMENT '合约符号（如BTCUSDT）',
                ts DATETIME NOT NULL COMMENT '时间戳（UTC+8）',
                funding_rate DECIMAL(10, 8) NOT NULL COMMENT '资金费率',
                funding_rate_pct DECIMAL(10, 6) DEFAULT NULL COMMENT '资金费率（百分比）',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_coin_symbol_ts (coin, symbol, ts),
                INDEX idx_coin_ts (coin, ts),
                INDEX idx_ts (ts)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='币安资金费率表';
            """
            
            # 币安爆仓数据表
            create_liquidation_table = """
            CREATE TABLE IF NOT EXISTS binance_liquidation_data (
                id INT AUTO_INCREMENT PRIMARY KEY,
                coin VARCHAR(10) NOT NULL COMMENT '币种（BTC/ETH/SOL）',
                symbol VARCHAR(50) NOT NULL COMMENT '交易对（如BTCUSDT）',
                side VARCHAR(10) DEFAULT NULL COMMENT '订单方向（BUY/SELL）',
                liquidation_type VARCHAR(10) DEFAULT NULL COMMENT '爆仓类型：LONG=多单爆仓（SELL），SHORT=空单爆仓（BUY）',
                order_type VARCHAR(20) DEFAULT NULL COMMENT '订单类型：LIMIT=限价单，MARKET=市价单，STOP=止损单，STOP_MARKET=止损市价单，TAKE_PROFIT=止盈单，TAKE_PROFIT_MARKET=止盈市价单，TRAILING_STOP_MARKET=跟踪止损市价单',
                time_in_force VARCHAR(10) DEFAULT NULL COMMENT '有效方式：GTC=一直有效直到取消，IOC=立即成交或取消，FOK=全部成交或取消，GTX=一直有效直到成交',
                quantity DECIMAL(30, 8) DEFAULT NULL COMMENT '订单数量',
                price DECIMAL(30, 8) DEFAULT NULL COMMENT '订单价格',
                avg_price DECIMAL(30, 8) DEFAULT NULL COMMENT '平均价格',
                order_status VARCHAR(20) DEFAULT NULL COMMENT '订单状态（FILLED等）',
                last_filled_qty DECIMAL(30, 8) DEFAULT NULL COMMENT '订单最近成交量',
                cumulative_filled_qty DECIMAL(30, 8) DEFAULT NULL COMMENT '订单累计成交量',
                usd_value DECIMAL(20, 2) DEFAULT NULL COMMENT 'USD价值（quantity * price）',
                ts DATETIME NOT NULL COMMENT '时间戳（UTC+8）',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                INDEX idx_coin (coin),
                INDEX idx_ts (ts),
                INDEX idx_coin_ts (coin, ts),
                INDEX idx_liquidation_type (liquidation_type)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='币安爆仓数据表';
            """
            
            cursor.execute(create_oi_table)
            cursor.execute(create_taker_table)
            cursor.execute(create_basis_table)
            cursor.execute(create_ls_table)
            cursor.execute(create_funding_table)
            cursor.execute(create_liquidation_table)
            self.connection.commit()
            logging.info("币安市场数据表创建/更新成功")
            return True
            
        except Exception as e:
            self.connection.rollback()
            logging.error(f"创建表失败: {e}")
            return False
        finally:
            cursor.close()
    
    def save_open_interest_batch(self, coin, symbol, data_to_save):
        """
        批量保存币安持仓量数据（确保按时间顺序保存，减少ID跳号）
        
        Args:
            coin: 币种（BTC/ETH/SOL）
            symbol: 合约符号（如BTCUSDT）
            data_to_save: 数据列表，每个元素为 (ts_datetime, sum_open_interest, sum_open_interest_value, cmc_circulating_supply)
        
        Returns:
            bool: 保存是否成功
        """
        if not self.connection:
            if not self.connect():
                return False
        
        # 检查连接是否有效
        try:
            self.connection.ping(reconnect=True)
        except Exception as ping_error:
            logging.warning(f"数据库连接检查失败，尝试重新连接: {ping_error}")
            if not self.connect():
                return False
        
        if not data_to_save:
            return True
        
        # 确保数据按时间顺序排序（从早到晚）
        sorted_data = sorted(data_to_save, key=lambda x: x[0])
        
        cursor = self.connection.cursor()
        try:
            # 先批量查询已存在的记录，避免不必要的自增ID消耗
            ts_list = [item[0] for item in sorted_data]
            placeholders = ','.join(['%s'] * len(ts_list))
            check_sql = f"""
            SELECT ts FROM binance_open_interest 
            WHERE coin = %s AND symbol = %s AND ts IN ({placeholders})
            """
            cursor.execute(check_sql, [coin, symbol] + ts_list)
            existing_ts_set = {row[0] for row in cursor.fetchall()}
            
            # 分离需要插入和更新的数据
            insert_values = []
            update_values = []
            
            for ts_datetime, sum_open_interest, sum_open_interest_value, cmc_circulating_supply in sorted_data:
                values = (coin, symbol, ts_datetime, sum_open_interest, sum_open_interest_value, cmc_circulating_supply)
                if ts_datetime in existing_ts_set:
                    update_values.append(values)
                else:
                    insert_values.append(values)
            
            # 批量插入新记录（避免自增ID被UPDATE消耗）
            insert_count = 0
            if insert_values:
                insert_sql = """
                INSERT INTO binance_open_interest 
                (coin, symbol, ts, sum_open_interest, sum_open_interest_value, cmc_circulating_supply)
                VALUES (%s, %s, %s, %s, %s, %s)
                """
                cursor.executemany(insert_sql, insert_values)
                insert_count = len(insert_values)
            
            # 批量更新已存在的记录
            update_count = 0
            if update_values:
                update_sql = """
                UPDATE binance_open_interest 
                SET sum_open_interest = %s,
                    sum_open_interest_value = %s,
                    cmc_circulating_supply = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE coin = %s AND symbol = %s AND ts = %s
                """
                # 调整参数顺序：先是要更新的值，然后是WHERE条件
                update_params = [(sum_open_interest, sum_open_interest_value, cmc_circulating_supply, coin, symbol, ts_datetime) 
                                for coin_val, symbol_val, ts_datetime, sum_open_interest, sum_open_interest_value, cmc_circulating_supply in update_values]
                cursor.executemany(update_sql, update_params)
                update_count = len(update_values)
            
            self.connection.commit()
            total_count = insert_count + update_count
            if total_count > 0:
                logging.info(f"币安持仓量数据保存成功: {coin} {symbol} 共 {total_count} 条（新增:{insert_count} 更新:{update_count}，按时间顺序：{sorted_data[0][0]} 到 {sorted_data[-1][0]}）")
            return total_count > 0
            
        except Exception as e:
            self.connection.rollback()
            logging.error(f"批量保存币安持仓量数据失败: {e}")
            logging.error(f"异常详情: {traceback.format_exc()}")
            return False
        finally:
            cursor.close()
    
    def save_taker_volume_batch(self, coin, symbol, data_to_save):
        """
        批量保存币安主动买卖量数据（确保按时间顺序保存，减少ID跳号）
        
        Args:
            coin: 币种（BTC/ETH/SOL）
            symbol: 合约符号（如BTCUSDT）
            data_to_save: 数据列表，每个元素为 (ts_datetime, buy_vol, sell_vol, buy_sell_ratio)
        
        Returns:
            bool: 保存是否成功
        """
        if not self.connection:
            if not self.connect():
                return False
        
        # 检查连接是否有效
        try:
            self.connection.ping(reconnect=True)
        except Exception as ping_error:
            logging.warning(f"数据库连接检查失败，尝试重新连接: {ping_error}")
            if not self.connect():
                return False
        
        if not data_to_save:
            return True
        
        # 确保数据按时间顺序排序（从早到晚）
        sorted_data = sorted(data_to_save, key=lambda x: x[0])
        
        cursor = self.connection.cursor()
        try:
            # 使用表锁确保ID连续（LOCK TABLES ... WRITE）
            # 注意：这会阻塞其他连接，但能确保ID连续
            try:
                cursor.execute("LOCK TABLES binance_taker_volume WRITE")
            except Exception as lock_error:
                # 如果表锁失败（可能是权限问题），使用行锁
                logging.debug(f"表锁失败，使用行锁: {lock_error}")
            
            # 规范化 ts 为整秒（与 DB DATETIME 一致），避免微秒导致误判“不存在”而重复插入
            def _norm_ts(dt):
                if dt is None:
                    return None
                return dt.replace(microsecond=0) if hasattr(dt, 'replace') else dt

            # 先批量查询已存在的记录，包括数据值，用于比较是否需要更新
            ts_list = [item[0] for item in sorted_data]
            placeholders = ','.join(['%s'] * len(ts_list))
            check_sql = f"""
            SELECT ts, buy_vol, sell_vol, buy_sell_ratio FROM binance_taker_volume 
            WHERE coin = %s AND symbol = %s AND ts IN ({placeholders})
            """
            cursor.execute(check_sql, [coin, symbol] + ts_list)
            existing_records = {}
            for row in cursor.fetchall():
                ts_datetime, buy_vol, sell_vol, buy_sell_ratio = row
                key = _norm_ts(ts_datetime)
                existing_records[key] = {
                    'buy_vol': float(buy_vol) if buy_vol else 0,
                    'sell_vol': float(sell_vol) if sell_vol else 0,
                    'buy_sell_ratio': float(buy_sell_ratio) if buy_sell_ratio else 0
                }
            
            # 分离需要插入和更新的数据（只有数据不一致时才更新）
            insert_values = []
            update_values = []
            
            for ts_datetime, buy_vol, sell_vol, buy_sell_ratio in sorted_data:
                values = (coin, symbol, ts_datetime, buy_vol, sell_vol, buy_sell_ratio)
                ts_key = _norm_ts(ts_datetime)
                if ts_key in existing_records:
                    # 记录已存在，比较数据是否不一致
                    existing = existing_records[ts_key]
                    # 使用小的容差值比较浮点数
                    buy_diff = abs(existing['buy_vol'] - buy_vol)
                    sell_diff = abs(existing['sell_vol'] - sell_vol)
                    ratio_diff = abs(existing['buy_sell_ratio'] - buy_sell_ratio)
                    
                    # 如果数据不一致（差值大于0.0001），才需要更新
                    if buy_diff >= 0.0001 or sell_diff >= 0.0001 or ratio_diff >= 0.0001:
                        update_values.append(values)
                    # 如果数据一致，跳过（不加入insert_values也不加入update_values）
                else:
                    # 记录不存在，需要插入
                    insert_values.append(values)
            
            # 批量插入新记录（避免自增ID被UPDATE消耗）
            # 使用逐条插入确保ID连续（虽然慢一些，但能保证ID连续）
            insert_count = 0
            if insert_values:
                insert_sql = """
                INSERT INTO binance_taker_volume 
                (coin, symbol, ts, buy_vol, sell_vol, buy_sell_ratio)
                VALUES (%s, %s, %s, %s, %s, %s)
                """
                # 逐条插入以确保ID连续（executemany可能导致ID不连续）
                for values in insert_values:
                    cursor.execute(insert_sql, values)
                    insert_count += 1
            
            # 批量更新已存在的记录
            update_count = 0
            if update_values:
                update_sql = """
                UPDATE binance_taker_volume 
                SET buy_vol = %s,
                    sell_vol = %s,
                    buy_sell_ratio = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE coin = %s AND symbol = %s AND ts = %s
                """
                # 调整参数顺序：先是要更新的值，然后是WHERE条件
                update_params = [(buy_vol, sell_vol, buy_sell_ratio, coin, symbol, ts_datetime) 
                                for coin_val, symbol_val, ts_datetime, buy_vol, sell_vol, buy_sell_ratio in update_values]
                cursor.executemany(update_sql, update_params)
                update_count = len(update_values)
            
            self.connection.commit()
            
            # 释放表锁
            try:
                cursor.execute("UNLOCK TABLES")
            except:
                pass
            
            total_count = insert_count + update_count
            if total_count > 0:
                logging.info(f"币安主动买卖量数据保存成功: {coin} {symbol} 共 {total_count} 条（新增:{insert_count} 更新:{update_count}，按时间顺序：{sorted_data[0][0]} 到 {sorted_data[-1][0]}）")
            return total_count > 0
            
        except Exception as e:
            self.connection.rollback()
            logging.error(f"批量保存币安主动买卖量数据失败: {e}")
            logging.error(f"异常详情: {traceback.format_exc()}")
            return False
        finally:
            cursor.close()
    
    def save_basis_batch(self, coin, pair, contract_type, data_to_save):
        """
        批量保存币安基差数据
        
        Args:
            coin: 币种（BTC/ETH/SOL）
            pair: 交易对（如BTCUSDT）
            contract_type: 合约类型（PERPETUAL等）
            data_to_save: 数据列表，每个元素为 (ts_datetime, index_price, futures_price, basis, basis_rate, annualized_basis_rate)
        
        Returns:
            bool: 保存是否成功
        """
        if not self.connection:
            if not self.connect():
                return False
        
        # 检查连接是否有效
        try:
            self.connection.ping(reconnect=True)
        except Exception as ping_error:
            logging.warning(f"数据库连接检查失败，尝试重新连接: {ping_error}")
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            sql = """
            INSERT INTO binance_basis 
            (coin, pair, contract_type, ts, index_price, futures_price, basis, basis_rate, annualized_basis_rate)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                index_price = VALUES(index_price),
                futures_price = VALUES(futures_price),
                basis = VALUES(basis),
                basis_rate = VALUES(basis_rate),
                annualized_basis_rate = VALUES(annualized_basis_rate),
                updated_at = CURRENT_TIMESTAMP
            """
            
            # 确保数据按时间顺序保存
            sorted_data = sorted(data_to_save, key=lambda x: x[0])
            
            saved_count = 0
            for ts_datetime, index_price, futures_price, basis, basis_rate, annualized_basis_rate in sorted_data:
                try:
                    cursor.execute(sql, (coin, pair, contract_type, ts_datetime, index_price, futures_price, basis, basis_rate, annualized_basis_rate))
                    saved_count += 1
                except Exception as e:
                    logging.warning(f"保存币安基差数据失败 (coin={coin}, pair={pair}, contract_type={contract_type}, ts={ts_datetime}): {e}")
                    continue
            
            self.connection.commit()
            if saved_count > 0:
                logging.info(f"币安基差数据保存成功: {coin} {pair} {contract_type} 共 {saved_count} 条（按时间顺序）")
            return saved_count > 0
            
        except Exception as e:
            self.connection.rollback()
            logging.error(f"批量保存币安基差数据失败: {e}")
            logging.error(f"异常详情: {traceback.format_exc()}")
            return False
        finally:
            cursor.close()
    
    def get_binance_long_short_ratio_by_ts(self, coin, symbol, ts_datetime):
        """根据coin, symbol, ts查询币安多空比数据"""
        if not self.connection:
            if not self.connect():
                return None
        
        # 检查连接是否有效
        try:
            self.connection.ping(reconnect=True)
        except Exception as ping_error:
            logging.warning(f"数据库连接检查失败，尝试重新连接: {ping_error}")
            if not self.connect():
                return None
        
        cursor = self.connection.cursor()
        try:
            sql = """
            SELECT top_position_ratio, top_account_ratio, global_account_ratio
            FROM binance_long_short_ratio 
            WHERE coin = %s AND symbol = %s AND ts = %s
            """
            cursor.execute(sql, (coin, symbol, ts_datetime))
            result = cursor.fetchone()
            if result:
                return {
                    'top_position_ratio': float(result[0]) if result[0] else None,
                    'top_account_ratio': float(result[1]) if result[1] else None,
                    'global_account_ratio': float(result[2]) if result[2] else None
                }
            return None
        except Exception as e:
            logging.warning(f"查询币安多空比数据失败: {e}")
            return None
        finally:
            cursor.close()
    
    def save_binance_long_short_ratio_partial(self, coin, symbol, ts_datetime, 
                                             top_position_ratio=None, 
                                             top_account_ratio=None, 
                                             global_account_ratio=None):
        """
        部分保存币安多空比数据（只更新传入的字段，其他字段保持不变）
        返回: 'saved'（新增）、'updated'（更新）、'skipped'（跳过，数据相同）
        """
        if not self.connection:
            if not self.connect():
                return False
        
        # 检查连接是否有效
        try:
            self.connection.ping(reconnect=True)
        except Exception as ping_error:
            logging.warning(f"数据库连接检查失败，尝试重新连接: {ping_error}")
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            # 查询现有数据
            existing = self.get_binance_long_short_ratio_by_ts(coin, symbol, ts_datetime)
            
            if existing:
                # 数据已存在，检查是否需要更新
                need_update = False
                update_fields = []
                update_values = []
                
                if top_position_ratio is not None:
                    if existing['top_position_ratio'] is None or abs(existing['top_position_ratio'] - top_position_ratio) >= 0.0001:
                        update_fields.append("top_position_ratio = %s")
                        update_values.append(top_position_ratio)
                        need_update = True
                
                if top_account_ratio is not None:
                    if existing['top_account_ratio'] is None or abs(existing['top_account_ratio'] - top_account_ratio) >= 0.0001:
                        update_fields.append("top_account_ratio = %s")
                        update_values.append(top_account_ratio)
                        need_update = True
                
                if global_account_ratio is not None:
                    if existing['global_account_ratio'] is None or abs(existing['global_account_ratio'] - global_account_ratio) >= 0.0001:
                        update_fields.append("global_account_ratio = %s")
                        update_values.append(global_account_ratio)
                        need_update = True
                
                if need_update:
                    # 需要更新
                    sql = f"""
                    UPDATE binance_long_short_ratio 
                    SET {', '.join(update_fields)}
                    WHERE coin = %s AND symbol = %s AND ts = %s
                    """
                    update_values.extend([coin, symbol, ts_datetime])
                    cursor.execute(sql, update_values)
                    self.connection.commit()
                    logging.info(f"币安多空比数据已更新: {coin} {symbol} {ts_datetime} - 更新字段: {', '.join(update_fields)}")
                    return 'updated'
                else:
                    # 数据相同，跳过
                    logging.debug(f"币安多空比数据已存在且一致，跳过: {coin} {symbol} {ts_datetime}")
                    return 'skipped'
            else:
                # 数据不存在，插入新记录
                # 构建INSERT语句，只包含传入的非None字段
                insert_fields = ['coin', 'symbol', 'ts']
                insert_values = [coin, symbol, ts_datetime]
                placeholders = ['%s', '%s', '%s']
                
                if top_position_ratio is not None:
                    insert_fields.append('top_position_ratio')
                    insert_values.append(top_position_ratio)
                    placeholders.append('%s')
                
                if top_account_ratio is not None:
                    insert_fields.append('top_account_ratio')
                    insert_values.append(top_account_ratio)
                    placeholders.append('%s')
                
                if global_account_ratio is not None:
                    insert_fields.append('global_account_ratio')
                    insert_values.append(global_account_ratio)
                    placeholders.append('%s')
                
                sql = f"""
                INSERT INTO binance_long_short_ratio ({', '.join(insert_fields)})
                VALUES ({', '.join(placeholders)})
                """
                cursor.execute(sql, insert_values)
                self.connection.commit()
                logging.info(f"币安多空比数据新增: {coin} {symbol} {ts_datetime} - 字段: {', '.join([f for f in insert_fields if f not in ['coin', 'symbol', 'ts']])}")
                return 'saved'
                
        except Exception as e:
            self.connection.rollback()
            logging.error(f"保存币安多空比数据失败: {e}")
            import traceback
            logging.error(f"异常详情: {traceback.format_exc()}")
            return False
        finally:
            cursor.close()
    
    def save_funding_rate(self, coin, symbol, ts_datetime, funding_rate, funding_rate_pct=None):
        """
        保存币安资金费率数据
        
        Args:
            coin: 币种（BTC/ETH/SOL）
            symbol: 合约符号（如BTCUSDT）
            ts_datetime: 时间戳（UTC+8）
            funding_rate: 资金费率
            funding_rate_pct: 资金费率（百分比）
        
        Returns:
            bool: 保存是否成功
        """
        if not self.connection:
            if not self.connect():
                return False
        
        # 检查连接是否有效
        try:
            self.connection.ping(reconnect=True)
        except Exception as ping_error:
            logging.warning(f"数据库连接检查失败，尝试重新连接: {ping_error}")
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            sql = """
            INSERT INTO binance_funding_rate 
            (coin, symbol, ts, funding_rate, funding_rate_pct)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                funding_rate = VALUES(funding_rate),
                funding_rate_pct = VALUES(funding_rate_pct),
                updated_at = CURRENT_TIMESTAMP
            """
            cursor.execute(sql, (coin, symbol, ts_datetime, funding_rate, funding_rate_pct))
            self.connection.commit()
            logging.debug(f"币安资金费率数据保存成功: {coin} {symbol} {ts_datetime} rate={funding_rate}")
            return True
        except Exception as e:
            self.connection.rollback()
            logging.error(f"保存币安资金费率数据失败: {e}")
            import traceback
            logging.error(f"异常详情: {traceback.format_exc()}")
            return False
        finally:
            cursor.close()
    
    def save_liquidation(self, coin, symbol, ts_datetime, side=None, liquidation_type=None,
                         order_type=None, time_in_force=None, quantity=None, price=None, avg_price=None,
                         order_status=None, last_filled_qty=None, cumulative_filled_qty=None,
                         usd_value=None):
        """
        保存币安爆仓数据
        
        Args:
            coin: 币种（BTC/ETH/SOL）
            symbol: 交易对（如BTCUSDT）
            ts_datetime: 时间戳（UTC+8）
            side: 订单方向（BUY/SELL）
            liquidation_type: 爆仓类型（LONG=多单爆仓，SHORT=空单爆仓）
            order_type: 订单类型（LIMIT=限价单，MARKET=市价单，STOP=止损单等）
            time_in_force: 有效方式（GTC=一直有效，IOC=立即成交或取消，FOK=全部成交或取消等）
            quantity: 订单数量
            price: 订单价格
            avg_price: 平均价格
            order_status: 订单状态（FILLED等）
            last_filled_qty: 订单最近成交量
            cumulative_filled_qty: 订单累计成交量
            usd_value: USD价值（quantity * price）
        
        Returns:
            bool: 保存是否成功
        """
        if not self.connection:
            if not self.connect():
                return False
        
        # 检查连接是否有效
        try:
            self.connection.ping(reconnect=True)
        except Exception as ping_error:
            logging.warning(f"数据库连接检查失败，尝试重新连接: {ping_error}")
            if not self.connect():
                return False
        
        cursor = self.connection.cursor()
        try:
            # 如果表结构需要更新，先尝试添加liquidation_type字段
            try:
                cursor.execute("ALTER TABLE binance_liquidation_data ADD COLUMN liquidation_type VARCHAR(10) DEFAULT NULL COMMENT '爆仓类型：LONG=多单爆仓（SELL），SHORT=空单爆仓（BUY）' AFTER side")
                self.connection.commit()
                logging.info("币安爆仓数据表已添加liquidation_type字段")
            except Exception as alter_error:
                # 字段可能已存在，忽略错误
                if "Duplicate column name" not in str(alter_error):
                    logging.debug(f"检查liquidation_type字段时: {alter_error}")
                self.connection.rollback()
            
            sql = """
            INSERT INTO binance_liquidation_data 
            (coin, symbol, ts, side, liquidation_type, order_type, time_in_force, quantity, price, 
             avg_price, order_status, last_filled_qty, cumulative_filled_qty, usd_value)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (
                coin, symbol, ts_datetime, side, liquidation_type, order_type, time_in_force,
                quantity, price, avg_price, order_status, last_filled_qty,
                cumulative_filled_qty, usd_value
            ))
            self.connection.commit()
            logging.debug(f"币安爆仓数据保存成功: {coin} {symbol} {ts_datetime} side={side} liquidation_type={liquidation_type} quantity={quantity} price={price} usd_value={usd_value}")
            return True
        except Exception as e:
            self.connection.rollback()
            logging.error(f"保存币安爆仓数据失败: {e}")
            import traceback
            logging.error(f"异常详情: {traceback.format_exc()}")
            return False
        finally:
            cursor.close()

