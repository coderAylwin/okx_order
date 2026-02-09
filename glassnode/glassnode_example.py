import requests
import time

# 1. 请将 'YOUR_API_KEY' 替换为真实API密钥,记得带英文双引号
API_KEY = "myapi_sk_12b8288f106c4e779565c76c44433a25"
BASE_URL = "https://api.alphanode.work"
headers = {
    "x-key": API_KEY
}

try:
    # 查询用量
    resp = requests.get(f"{BASE_URL}/usage/me", headers=headers)
    resp.raise_for_status()
    print("API Usage:", resp.json())


    # 示例1: 24h内BTC收盘价
    # resp = requests.get(f"{BASE_URL}/v1/metrics/market/price_usd_close", headers=headers, params={'a': 'BTC', 'i': '24h'})
    # resp.raise_for_status()
    # print("\nBTC Price (last 3):", resp.json()[-3:])


    # 示例2: ETH活跃地址
    # resp = requests.get(f"{BASE_URL}/v1/metrics/addresses/active_count", headers=headers, params={'a': 'ETH'})
    # resp.raise_for_status()
    # print("\nETH Active Addresses (last 3):", resp.json()[-3:])


    # 示例3: BTC 2022年1月OHLC
    # params_ohlc = {
    # 'a': 'BTC', 
    # 's': '1641013200', 
    # 'u': '1643605200'
    # }
    # resp = requests.get(f"{BASE_URL}/v1/metrics/market/price_usd_ohlc", headers=headers, params=params_ohlc)
    # resp.raise_for_status()
    # print("\nBTC Jan 2022 OHLC:", resp.json())


    # 示例4: BTC MVRV Z-Score
    # resp = requests.get(f"{BASE_URL}/v1/metrics/market/mvrv_z_score", headers=headers, params={'a': 'BTC'})
    # resp.raise_for_status()
    # print("\nBTC MVRV Z-Score (last 3):", resp.json()[-3:])


    # 示例5: BTC: Altcoin Cycle Signal
    # 绝大部分T2,T3数据都可以使用。若显示，Please reach out to our sales team to gain access to this metric
    # 则无法调用api。此api需单独购买。
    # 无法使用的api返回值为：{"type":"metric","requiredPlan":"professional_ml"}
    # params = {
    # 'a': 'BTC',
    # 's': '1641013200',
    # 'u': '1643605200'
    # }
    # resp = requests.get(f"{BASE_URL}/v1/metrics/signals/altcoin_index", headers=headers, params=params)
    # print("\nBTC Altcoin Cycle Signal:", resp.json())

    # 示例6: BTC多端点，多参数调用，其他asset请参考api docs
    # 注意：请只调用希望调用的指标，全部去掉注释将产生大量api调用。
    # 市场指标 (market metrics)
    endpoints_to_call = [
        
        # ------------ 现货 (spot) ------------------------ #
        # - 价格 (price)
        "/v1/metrics/market/price_usd_close",
        # "/v1/metrics/institutions/us_spot_etf_flows_all",
        # "/v1/metrics/market/emea_30d_price_change",
        # "/v1/metrics/market/apac_30d_price_change",
        # "/v1/metrics/market/price_drawdown_relative",
        # "/v1/metrics/market/amer_30d_price_change",
        # "/v1/metrics/market/price_usd_ohlc",

        # # - 市值 (market_cap)
        # "/v1/metrics/market/marketcap_usd",

        # # - 波动率 (volatility)
        # "/v1/metrics/market/realized_volatility_3_months",
        # "/v1/metrics/market/realized_volatility_1_month",
        # "/v1/metrics/market/realized_volatility_all",
        # "/v1/metrics/market/realized_volatility_6_months",
        # "/v1/metrics/market/realized_volatility_1_year",
        # "/v1/metrics/market/realized_volatility_2_weeks",
        # "/v1/metrics/market/realized_volatility_1_week",

        # # - 期货 (futures)
        # # -- 持仓量 (open_interest)
        # "/v1/metrics/derivatives/futures_estimated_leverage_ratio",
        # "/v1/metrics/derivatives/futures_open_interest_sum",
        # "/v1/metrics/derivatives/futures_open_interest_perpetual_sum",
        
        # # -- 成交量 (volume)
        # "/v1/metrics/derivatives/futures_volume_daily_sum",
        # "/v1/metrics/derivatives/futures_volume_daily_perpetual_sum",
        
        # # -- 清算 (liquidations)
        # "/v1/metrics/derivatives/futures_liquidated_volume_long_relative",
        # "/v1/metrics/derivatives/futures_liquidated_volume_short_sum",
        # "/v1/metrics/derivatives/futures_liquidated_volume_long_sum",

        # # - 期权 (option)
        # # -- 期权持仓量 (options_open_interest)
        # "/v1/metrics/derivatives/options_open_interest_sum",
        
        # # -- 成交量 (volume)
        # "/v1/metrics/derivatives/options_volume_daily_sum",
        
        # # -- 隐含波动率 (implied_volatility)
        # "/v1/metrics/derivatives/options_atm_implied_volatility_all",
        # "/v1/metrics/derivatives/options_atm_implied_volatility_1_week",
        # "/v1/metrics/derivatives/options_atm_implied_volatility_1_month",
        # "/v1/metrics/derivatives/options_atm_implied_volatility_3_months",
        # "/v1/metrics/derivatives/options_atm_implied_volatility_6_months",
        # "/v1/metrics/derivatives/dvol_ohlc",
        
        # # -- 看跌/看涨比率 (put/call ratio)
        # "/v1/metrics/derivatives/options_open_interest_put_call_ratio",
        # "/v1/metrics/derivatives/options_volume_put_call_ratio",
        
        # # -- 25 Delta 偏斜 (25_delta_skew)
        # "/v1/metrics/derivatives/options_25delta_skew_all",
        # "/v1/metrics/derivatives/options_25delta_skew_1_week",
        # "/v1/metrics/derivatives/options_25delta_skew_1_month",
        # "/v1/metrics/derivatives/options_25delta_skew_3_months",
        # "/v1/metrics/derivatives/options_25delta_skew_6_months",
        
        # # -- 溢价 (premiums)
        # "/v1/metrics/options/options_premiums",
        # "/v1/metrics/options/bull_bear_index",
        # "/v1/metrics/options/premium_weighted_median_strike",

        # # - ETF (exchange_traded_funds)
        # "/v1/metrics/institutions/us_spot_etf_balances_all",
        # "/v1/metrics/institutions/us_spot_etf_balances_latest",
        # "/v1/metrics/institutions/us_spot_etf_flows_all",
        # "/v1/metrics/institutions/us_spot_etf_flows_net",
        
        # # -- 链上余额 (on-chain_balances)
        # "/v1/metrics/distribution/balance_vaneck",
        # "/v1/metrics/distribution/balance_wisdomtree",
        # "/v1/metrics/distribution/balance_franklin_templeton",
        # "/v1/metrics/distribution/balance_blackrock",
        # "/v1/metrics/distribution/balance_grayscale_trust",
        # "/v1/metrics/distribution/balance_bitwise",
        
        # # -- 加拿大 ETF (canadian-etf)
        # "/v1/metrics/institutions/purpose_etf_holdings_sum",
        # "/v1/metrics/institutions/purpose_etf_flows_sum",
        # "/v1/metrics/institutions/purpose_etf_aum_sum",



        # # --------- 链上指标 (On-Chain Metrics) ------------- #
        # # - 地址 (addresses)
        # # -- 活跃地址 (active_addresses)
        # "/v1/metrics/addresses/active_count",
        # "/v1/metrics/addresses/sending_count",
        # "/v1/metrics/addresses/receiving_count",
        
        # # -- 地址增长 (address_growth)
        # "/v1/metrics/addresses/new_non_zero_count",
        # "/v1/metrics/addresses/count",
        
        # # -- 按余额分的地址 (USD) (address_by_balance(USD))
        # "/v1/metrics/addresses/min_1_usd_count",
        # "/v1/metrics/addresses/min_10_usd_count",
        # "/v1/metrics/addresses/min_100_usd_count",
        # "/v1/metrics/addresses/min_1k_usd_count",
        # "/v1/metrics/addresses/min_10k_usd_count",
        # "/v1/metrics/addresses/min_100k_usd_count",
        # "/v1/metrics/addresses/min_1m_usd_count",
        
        # # -- 按余额分的地址 (原生) (address_by_balance(Native))
        # "/v1/metrics/addresses/non_zero_count",
        # "/v1/metrics/addresses/min_point_zero_1_count",
        # "/v1/metrics/addresses/min_point_1_count",
        # "/v1/metrics/addresses/min_1_count",
        # "/v1/metrics/addresses/min_10_count",
        # "/v1/metrics/addresses/min_100_count",
        # "/v1/metrics/addresses/min_1k_count",
        # "/v1/metrics/addresses/min_10k_count",
        
        # # -- 地址供应频段 (address_supply_bands)
        # "/v1/metrics/addresses/supply_distribution_relative",
        # "/v1/metrics/addresses/supply_balance_less_0001",
        # "/v1/metrics/addresses/supply_balance_0001_001",
        # "/v1/metrics/addresses/supply_balance_001_01",
        # "/v1/metrics/addresses/supply_balance_01_1",
        # "/v1/metrics/addresses/supply_balance_1_10",
        # "/v1/metrics/addresses/supply_balance_10_100",
        # "/v1/metrics/addresses/supply_balance_100_1k",
        # "/v1/metrics/addresses/supply_balance_1k_10k",
        # "/v1/metrics/addresses/supply_balance_10k_100k",
        # "/v1/metrics/addresses/supply_balance_more_100k",
        
        # # -- 累积地址 (accumulation_addresses)
        # "/v1/metrics/addresses/accumulation_count",
        # "/v1/metrics/addresses/accumulation_balance",
        
        # # -- 持有 (retention)
        # "/v1/metrics/addresses/activity_retention",
        # "/v1/metrics/addresses/holder_retention",
        # "/v1/metrics/addresses/holder_retention_rate",
        # "/v1/metrics/addresses/holder_accumulation_ratio",
        # "/v1/metrics/addresses/activity_retention_rate",



        # # - 分类 (breakdowns)
        # # -- 市值 (market_cap)
        # "/v1/metrics/breakdowns/marketcap_usd_by_age",
        # "/v1/metrics/breakdowns/marketcap_usd_by_wallet_size",
        # "/v1/metrics/breakdowns/marketcap_usd_by_pnl",
        
        # # -- 供应 (supply)
        # "/v1/metrics/breakdowns/supply_by_age",
        # "/v1/metrics/breakdowns/supply_by_wallet_size",
        # "/v1/metrics/supply/supply_by_date_bands",
        # "/v1/metrics/supply/supply_by_date_bands_relative",
        # "/v1/metrics/breakdowns/supply_by_pnl",
        # "/v1/metrics/breakdowns/supply_by_pnl_relative",
        
        # # -- MVRV
        # "/v1/metrics/breakdowns/mvrv_by_wallet_size",
        # "/v1/metrics/breakdowns/mvrv_by_pnl",
        
        # # -- SOFR
        # "/v1/metrics/breakdowns/sopr_by_age",
        # "/v1/metrics/breakdowns/sopr_by_lth_sth",
        # "/v1/metrics/breakdowns/sopr_by_wallet_size",
        # "/v1/metrics/breakdowns/sopr_by_pnl",
        
        # # -- 花费量 (spend_volume)
        # "/v1/metrics/breakdowns/spent_volume_loss_sum_by_age",
        # "/v1/metrics/breakdowns/spent_volume_loss_sum_by_lth_sth",
        # "/v1/metrics/breakdowns/spent_volume_loss_sum_by_wallet_size",
        # "/v1/metrics/breakdowns/spent_volume_profit_sum_by_age",
        # "/v1/metrics/breakdowns/spent_volume_profit_sum_by_lth_sth",
        # "/v1/metrics/breakdowns/spent_volume_profit_sum_by_wallet_size",
        # "/v1/metrics/breakdowns/spent_volume_sum_by_age",
        # "/v1/metrics/breakdowns/spent_volume_sum_by_lth_sth",
        # "/v1/metrics/breakdowns/spent_volume_sum_by_wallet_size",
        # "/v1/metrics/breakdowns/spent_volume_sum_by_pnl",
        
        # # -- 已实现市值 (realized_cap)
        # "/v1/metrics/breakdowns/marketcap_realized_usd_by_age",
        # "/v1/metrics/breakdowns/marketcap_realized_usd_by_wallet_size",
        # "/v1/metrics/supply/rcap_by_date_bands",
        # "/v1/metrics/supply/rcap_by_date_bands_relative",
        # "/v1/metrics/breakdowns/marketcap_realized_usd_by_pnl",
        
        # # -- 已实现价格 (realized_price)
        # "/v1/metrics/breakdowns/price_realized_usd_by_age",
        # "/v1/metrics/breakdowns/price_realized_usd_by_wallet_size",
        # "/v1/metrics/breakdowns/price_realized_usd_by_pnl",
        
        # # -- 已实现利润/亏损 (realized_profit/loss)
        # "/v1/metrics/breakdowns/realized_loss_by_age",
        # "/v1/metrics/breakdowns/realized_loss_by_lth_sth",
        # "/v1/metrics/breakdowns/realized_loss_by_wallet_size",
        # "/v1/metrics/breakdowns/realized_profit_by_age",
        # "/v1/metrics/breakdowns/realized_profit_by_lth_sth",
        # "/v1/metrics/breakdowns/realized_profit_by_wallet_size",
        # "/v1/metrics/breakdowns/realized_loss_by_pnl",
        # "/v1/metrics/breakdowns/realized_profit_by_pnl",



        # # - 实体 (entities)
        # # -- 实体活动 (entity_activity)
        # "/v1/metrics/entities/active_count",
        # "/v1/metrics/entities/sending_count",
        # "/v1/metrics/entities/receiving_count",
        
        # # -- 实体增长 (entity_growth)
        # "/v1/metrics/entities/new_count",
        # "/v1/metrics/entities/net_growth_count",
        
        # # -- 实体供应频段 (entity_supply_bands)
        # "/v1/metrics/entities/min_1k_count",
        # "/v1/metrics/entities/supply_distribution_relative",
        # "/v1/metrics/entities/supply_balance_less_0001",
        # "/v1/metrics/entities/supply_balance_0001_001",
        # "/v1/metrics/entities/supply_balance_001_01",
        # "/v1/metrics/entities/supply_balance_01_1",
        # "/v1/metrics/entities/supply_balance_1_10",
        # "/v1/metrics/entities/supply_balance_10_100",
        # "/v1/metrics/entities/supply_balance_100_1k",
        # "/v1/metrics/entities/supply_balance_1k_10k",
        # "/v1/metrics/entities/supply_balance_10k_100k",
        # "/v1/metrics/entities/supply_balance_more_100k",
        
        # # -- 政府与公司 (goverments&companies)
        # "/v1/metrics/distribution/balance_us_government",
        # "/v1/metrics/distribution/balance_uk_government",
        # "/v1/metrics/distribution/balance_german_government",
        # "/v1/metrics/distribution/balance_el_salvador",
        # "/v1/metrics/distribution/balance_bhutan_government",
        # "/v1/metrics/distribution/balance_tether_treasury",
        # "/v1/metrics/distribution/balance_paypal",
        # "/v1/metrics/distribution/balance_robinhood",
        # "/v1/metrics/distribution/balance_tesla",
        # "/v1/metrics/distribution/balance_cashapp",
        # "/v1/metrics/distribution/balance_revolut",
        # "/v1/metrics/distribution/balance_wbtc",
        # "/v1/metrics/distribution/balance_mtgox_trustee",
        # "/v1/metrics/distribution/outflows_mtgox_trustee",
        # "/v1/metrics/distribution/balance_luna_foundation_guard",
        
        # # -- OTC 柜台 (OTC_desks)
        # "/v1/metrics/transactions/transfers_volume_to_otc_desks_sum",
        # "/v1/metrics/transactions/transfers_volume_from_otc_desks_sum",
        # "/v1/metrics/transactions/transfers_to_otc_desks_count",
        # "/v1/metrics/transactions/transfers_from_otc_desks_count",



        # # - 交易所 (exchanges)
        # # -- 交易所余额 (exchange_balances)
        # "/v1/metrics/distribution/balance_exchanges",
        # "/v1/metrics/distribution/balance_exchanges_relative",
        # "/v1/metrics/distribution/balance_exchanges_all",
        # "/v1/metrics/distribution/exchange_net_position_change",
        
        # # -- 交易所流量 (exchange_flows)
        # "/v1/metrics/transactions/transfers_volume_to_exchanges_sum",
        # "/v1/metrics/transactions/transfers_volume_from_exchanges_sum",
        # "/v1/metrics/transactions/transfers_volume_exchanges_net",
        # "/v1/metrics/transactions/transfers_to_exchanges_count",
        # "/v1/metrics/transactions/transfers_from_exchanges_count",
        # "/v1/metrics/transactions/transfers_volume_to_exchanges_mean",
        # "/v1/metrics/transactions/transfers_volume_from_exchanges_mean",
        # "/v1/metrics/transactions/transfers_volume_within_exchanges_sum",
        # "/v1/metrics/transactions/transfers_between_exchanges_count",
        # "/v1/metrics/transactions/transfers_volume_between_exchanges_sum",
        # "/v1/metrics/transactions/transfers_volume_exchanges_net_by_size",
        # "/v1/metrics/distribution/exchange_reliance_ratio",
        # "/v1/metrics/distribution/exchange_reshuffling_ratio",
        # "/v1/metrics/distribution/exchange_whales_outflow",
        # "/v1/metrics/distribution/exchange_aggregated_reshuffling_ratio",
        # "/v1/metrics/distribution/exchange_aggregated_reliance_ratio",
        # "/v1/metrics/indicators/realized_profit_to_exchanges_account_based",
        # "/v1/metrics/indicators/realized_loss_to_exchanges_account_based",
        
        # # -- 交易所地址 (exchange_addresses)
        # "/v1/metrics/addresses/sending_to_exchanges_count",
        # "/v1/metrics/addresses/receiving_from_exchanges_count",
        
        # # -- 交易所费用 (exchange_fees)
        # "/v1/metrics/fees/exchanges_sum",
        # "/v1/metrics/fees/exchanges_mean",
        
        # # -- 交易所主导地位 (exchange_dominance)
        # "/v1/metrics/fees/exchanges_relative",
        
        # # -- 巨鲸流入/流出交易所 (whales_to/from_exchanges)
        # "/v1/metrics/transactions/transfers_volume_whales_to_exchanges_sum",
        # "/v1/metrics/transactions/transfers_volume_exchanges_to_whales_sum",
        # "/v1/metrics/transactions/transfers_whales_to_exchanges_count",
        # "/v1/metrics/transactions/transfers_exchanges_to_whales_count",
        
        # # -- 长期/短期持有者流入 (LTH/STH_inflows)
        # "/v1/metrics/indicators/realized_profit_lth_to_exchanges_account_based",
        # "/v1/metrics/indicators/realized_profit_sth_to_exchanges_account_based",
        # "/v1/metrics/indicators/realized_loss_lth_to_exchanges_account_based",
        # "/v1/metrics/indicators/realized_loss_sth_to_exchanges_account_based",
        # "/v1/metrics/indicators/realized_profit_loss_lth_sth_to_exchanges_relative",
        # "/v1/metrics/transactions/transfers_volume_lth_to_exchanges_sum",
        # "/v1/metrics/transactions/transfers_volume_sth_to_exchanges_sum",
        # "/v1/metrics/transactions/transfers_volume_sth_to_exchanges_profit_sum",
        # "/v1/metrics/transactions/transfers_volume_lth_to_exchanges_loss_sum",
        # "/v1/metrics/transactions/transfers_volume_sth_to_exchanges_loss_sum",
        # "/v1/metrics/transactions/transfers_volume_lth_sth_to_exchanges_profit_loss_relative",



        # # - 费用 (fees)
        # "/v1/metrics/fees/volume_sum",
        # "/v1/metrics/fees/volume_mean",
        # "/v1/metrics/fees/volume_median",
        # "/v1/metrics/fees/fee_ratio_multiple",
        # "/v1/metrics/mining/thermocap",
        # "/v1/metrics/mining/marketcap_thermocap_ratio",



        # # - 指标 (indicators)
        # "/v1/metrics/indicators/puell_multiple",
        # "/v1/metrics/indicators/cvdd",
        # "/v1/metrics/indicators/rhodl_ratio",
        # "/v1/metrics/indicators/investor_capitalization",
        # "/v1/metrics/indicators/seller_exhaustion_constant",
        # "/v1/metrics/indicators/pi_cycle_top",
        # "/v1/metrics/indicators/accumulation_trend_score",
        # "/v1/metrics/indicators/fear_greed",
        # "/v1/metrics/supply/sth_lth_realized_value_ratio",
        # "/v1/metrics/indicators/power_law",
        # "/v1/metrics/indicators/cost_basis_distribution_quantiles",
        # "/v1/metrics/indicators/spent_supply_distribution_quantiles",
        
        # # -- NVT
        # "/v1/metrics/indicators/nvt",
        # "/v1/metrics/indicators/nvts",
        # "/v1/metrics/indicators/velocity",
        # "/v1/metrics/indicators/nvt_entity_adjusted",
        
        # # -- 储备风险 (reserve_risk)
        # "/v1/metrics/indicators/reserve_risk",
        
        # # -- 稳定币供应比率 (stablecoin_supply_ratio)
        # "/v1/metrics/indicators/ssr",
        # "/v1/metrics/indicators/ssr_oscillator",
        
        # # -- 存量-流量 (stock-to-flow)
        # "/v1/metrics/indicators/stock_to_flow_ratio",
        # "/v1/metrics/indicators/stock_to_flow_deflection",



        # # - 铭文与符文 (inscription&runes)
        # # -- 铭文 (inscriptions)
        # "/v1/metrics/transactions/inscriptions_size_share",
        # "/v1/metrics/transactions/inscriptions_fee",
        # "/v1/metrics/transactions/inscriptions_fee_share",
        # "/v1/metrics/transactions/inscriptions_size_sum",
        # "/v1/metrics/transactions/inscriptions_count_sum",
        # "/v1/metrics/transactions/inscriptions_count",
        # "/v1/metrics/transactions/inscriptions_count_share",
        # # -- 符文 (runes)
        # "/v1/metrics/transactions/runes_count_share",
        # "/v1/metrics/transactions/runes_count_sum",
        # "/v1/metrics/transactions/runes_fee",
        # "/v1/metrics/transactions/runes_fee_share",



        # # - 生命周期 (lifespan)
        # # -- 币天销毁 (coin_days_destroyed)
        # "/v1/metrics/indicators/cdd_account_based",
        # "/v1/metrics/indicators/cdd",
        # "/v1/metrics/indicators/cdd_supply_adjusted",
        # "/v1/metrics/indicators/cdd_supply_adjusted_binary",
        # "/v1/metrics/indicators/cyd",
        # "/v1/metrics/indicators/cyd_supply_adjusted",
        # "/v1/metrics/indicators/cyd_account_based",
        # "/v1/metrics/indicators/cyd_account_based_supply_adjusted",
        # "/v1/metrics/indicators/cdd90_age_adjusted",
        # "/v1/metrics/indicators/cdd90_account_based_age_adjusted",
        # "/v1/metrics/indicators/cdd_lth_account_based",
        # "/v1/metrics/indicators/cdd_sth_account_based",

        # # -- 花费量生命周期 (spent_volume_lifespan)
        # "/v1/metrics/indicators/svl_entity_adjusted_1w_1m",
        # "/v1/metrics/indicators/svl_entity_adjusted_6m_12m",

        # # -- 花费输出生命周期 (spend_output_lifespan)
        # "/v1/metrics/indicators/asol_account_based",
        # "/v1/metrics/indicators/asol_account_based", # (重复)
        # "/v1/metrics/indicators/asol",
        # "/v1/metrics/indicators/msol",
        # "/v1/metrics/indicators/soab",
        # "/v1/metrics/indicators/sol_1h",
        # "/v1/metrics/indicators/sol_1h_24h",
        # "/v1/metrics/indicators/sol_1d_1w",
        # "/v1/metrics/indicators/sol_1w_1m",
        # "/v1/metrics/indicators/sol_1m_3m",
        # "/v1/metrics/indicators/sol_3m_6m",
        # "/v1/metrics/indicators/sol_6m_12m",
        # "/v1/metrics/indicators/sol_1y_2y",
        # "/v1/metrics/indicators/sol_2y_3y",
        # "/v1/metrics/indicators/sol_3y_5y",
        # "/v1/metrics/indicators/sol_5y_7y",
        # "/v1/metrics/indicators/sol_7y_10y",
        # "/v1/metrics/indicators/sol_more_10y",
        # "/v1/metrics/indicators/asol_lth_account_based",
        # "/v1/metrics/indicators/asol_sth_account_based",
        # "/v1/metrics/indicators/spent_outputs_by_date_bands",
        # "/v1/metrics/indicators/spent_outputs_by_date_bands_relative",
        
        # # -- 休眠期 (dormancy)
        # "/v1/metrics/indicators/dormancy_account_based",
        # "/v1/metrics/indicators/average_dormancy",
        # "/v1/metrics/indicators/average_dormancy_supply_adjusted",
        # "/v1/metrics/indicators/dormancy_flow",
        # "/v1/metrics/indicators/dormancy_lth_account_based",
        # "/v1/metrics/indicators/dormancy_sth_account_based",
        
        # # -- 活跃度 (liveliness)
        # "/v1/metrics/indicators/liveliness_account_based",
        # "/v1/metrics/indicators/liveliness",
        # "/v1/metrics/indicators/hodled_lost_coins",
        # "/v1/metrics/indicators/hodler_net_position_change",

        

        # # - 闪电网络 (lightning_network)
        # # -- 闪电网络容量 (lightning_capacity)
        # "/v1/metrics/lightning/network_capacity_sum",
        # "/v1/metrics/lightning/gini_capacity_distribution",
        
        # # -- 闪电网络通道 (lightning_channels)
        # "/v1/metrics/lightning/channel_size_mean",
        # "/v1/metrics/lightning/channel_size_median",
        # "/v1/metrics/lightning/channels_count",
        # "/v1/metrics/lightning/gini_channel_distribution",
        
        # # -- 闪电网络节点 (lightning_nodes)
        # "/v1/metrics/lightning/nodes_count",
        # "/v1/metrics/lightning/node_connectivity",
        
        # # -- 闪电网络费用 (lightning_fees)
        # "/v1/metrics/lightning/base_fee_median",
        # "/v1/metrics/lightning/fee_rate_median",



        # # - 长期/短期持有者指标 (long/short-term metrics)
        # # -- 供应 (supply)
        # "/v1/metrics/supply/lth_sth_profit_loss_relative",
        # "/v1/metrics/supply/lth_sum",
        # "/v1/metrics/supply/lth_net_change",
        # "/v1/metrics/supply/lth_profit_sum",
        # "/v1/metrics/supply/lth_loss_sum",
        # "/v1/metrics/supply/sth_sum",
        # "/v1/metrics/supply/sth_profit_sum",
        # "/v1/metrics/supply/sth_loss_sum",
        
        # # -- 转移量 (transfer_volume)
        # "/v1/metrics/transactions/transfers_volume_entity_adjusted_from_lth_sum",
        # "/v1/metrics/transactions/transfers_volume_entity_adjusted_from_sth_sum",
        # "/v1/metrics/transactions/transfers_volume_entity_adjusted_from_lth_profit_sum",
        # "/v1/metrics/transactions/transfers_volume_entity_adjusted_from_sth_profit_sum",
        # "/v1/metrics/transactions/transfers_volume_entity_adjusted_from_lth_loss_sum",
        # "/v1/metrics/transactions/transfers_volume_entity_adjusted_from_sth_loss_sum",
        # "/v1/metrics/transactions/transfers_volume_entity_adjusted_from_lth_sth_profit_loss_relative",
        
        # # -- 利润/亏损 (profit/loss)
        # "/v1/metrics/indicators/nupl_more_155_account_based",
        # "/v1/metrics/indicators/nupl_less_155_account_based",
        # "/v1/metrics/indicators/nupl_more_155",
        # "/v1/metrics/indicators/nupl_less_155",
        # "/v1/metrics/indicators/realized_profit_lth_account_based",
        # "/v1/metrics/indicators/realized_profit_sth_account_based",
        # "/v1/metrics/indicators/realized_loss_sth_account_based",
        # "/v1/metrics/supply/sth_profit_loss_ratio",
        # "/v1/metrics/indicators/unrealized_loss_less_155",
        # "/v1/metrics/indicators/unrealized_loss_more_155",
        # "/v1/metrics/indicators/unrealized_profit_less_155",
        # "/v1/metrics/indicators/unrealized_profit_more_155",



        # # 内存池 - (mempool)
        # "/v1/metrics/mempool/txs_count_sum",
        # "/v1/metrics/mempool/txs_count_distribution",
        # "/v1/metrics/mempool/txs_size_sum",
        # "/v1/metrics/mempool/txs_size_distribution",
        # "/v1/metrics/mempool/txs_value_distribution",
        # "/v1/metrics/mempool/fees_sum",
        # "/v1/metrics/mempool/fees_distribution",
        # "/v1/metrics/mempool/fees_average_relative",
        # "/v1/metrics/mempool/fees_median_relative",



        # # - 矿工 (miners)
        # # -- 难度与哈希率 (diffculies&hashrate)
        # "/v1/metrics/mining/difficulty_latest",
        # "/v1/metrics/mining/hash_rate_mean",
        
        # # -- 矿工收入 (miner_revenue)
        # "/v1/metrics/mining/revenue_sum",
        # "/v1/metrics/mining/revenue_from_fees",
        # "/v1/metrics/mining/volume_mined_sum",
        
        # # -- 矿工余额 (miner_balance)
        # "/v1/metrics/distribution/balance_miners_change",
        # "/v1/metrics/distribution/balance_miners_sum",
        # "/v1/metrics/distribution/balance_miners_all",
        # "/v1/metrics/mining/miners_unspent_supply",
        
        # # -- 矿工流量 (miner_flow)
        # "/v1/metrics/transactions/transfers_volume_to_miners_sum",
        # "/v1/metrics/transactions/transfers_volume_from_miners_sum",
        # "/v1/metrics/transactions/transfers_volume_miners_net",
        # "/v1/metrics/mining/miners_outflow_multiple",
        # "/v1/metrics/transactions/transfers_from_miners_count",
        # "/v1/metrics/transactions/transfers_to_miners_count",
        
        # # -- 矿工到交易所 (miner_to_exchange)
        # "/v1/metrics/transactions/transfers_volume_miners_to_exchanges_all",
        # "/v1/metrics/transactions/transfers_volume_miners_to_exchanges",
        
        # # -- 丝带 (ribbons)
        # "/v1/metrics/indicators/difficulty_ribbon",
        # "/v1/metrics/indicators/difficulty_ribbon_compression",
        # "/v1/metrics/indicators/hash_ribbon",
        
        # # -- 区块 (blocks)
        # "/v1/metrics/blockchain/block_height",
        # "/v1/metrics/blockchain/block_count",
        # "/v1/metrics/blockchain/block_interval_mean",
        # "/v1/metrics/blockchain/block_interval_median",
        # "/v1/metrics/blockchain/block_size_sum",
        # "/v1/metrics/blockchain/block_size_mean",




        # # - 成本基础与估值 (cost_basis&valuation)
        # # -- 定价模型 (pricing_model)
        # "/v1/metrics/indicators/balanced_price_usd",
        
        # # -- 已实现市值与价格 (Realized_cap&price)
        # "/v1/metrics/indicators/rcap_account_based",
        # "/v1/metrics/market/price_realized_usd",
        # "/v1/metrics/market/marketcap_realized_usd",
        # "/v1/metrics/market/deltacap_usd",
        # "/v1/metrics/market/price_realized_median_usd",
        
        # # -- MVRV
        # "/v1/metrics/indicators/mvrv_account_based",
        # "/v1/metrics/market/mvrv",
        # "/v1/metrics/market/mvrv_z_score",
        # "/v1/metrics/market/mvrv_more_155",
        # "/v1/metrics/market/mvrv_less_155",
        # "/v1/metrics/breakdowns/mvrv_by_age",
        # "/v1/metrics/market/mvrv_median",


    
        # # - 利润/亏损 (profit/loss)
        # # -- SOFR (Spent Output Profit Ratio)
        # "/v1/metrics/indicators/sopr_account_based",
        # "/v1/metrics/indicators/sopr",
        # "/v1/metrics/indicators/sopr_adjusted",
        # "/v1/metrics/indicators/sopr_more_155",
        # "/v1/metrics/indicators/sopr_less_155",
        
        # # -- 盈利/亏损中的供应 (supply_in_profit/loss)
        # "/v1/metrics/supply/profit_sum",
        # "/v1/metrics/supply/loss_sum",
        
        # # -- 未实现利润/亏损 (unrealized_profit/loss)
        # "/v1/metrics/indicators/unrealized_profit_account_based",
        # "/v1/metrics/indicators/unrealized_loss_account_based",
        # "/v1/metrics/indicators/net_unrealized_profit_loss_account_based",
        # "/v1/metrics/indicators/net_unrealized_profit_loss",
        # "/v1/metrics/indicators/unrealized_profit",
        # "/v1/metrics/indicators/unrealized_loss",
        
        # # -- 已实现利润/亏损 (realized_profit/loss)
        # "/v1/metrics/indicators/realized_profit",
        # "/v1/metrics/indicators/realized_loss",
        # "/v1/metrics/indicators/net_realized_profit_loss",
        # "/v1/metrics/indicators/realized_profit_loss_ratio",
        # "/v1/metrics/indicators/realized_profits_to_value_ratio",
        # "/v1/metrics/indicators/realized_profit_account_based",
        # "/v1/metrics/indicators/realized_loss_account_based",

        # # -- 盈利/亏损中的地址 (addresses_in_profit/loss)
        # "/v1/metrics/addresses/profit_relative",
        # "/v1/metrics/addresses/profit_count",
        # "/v1/metrics/addresses/loss_count",
        
        # # -- 盈利/亏损中的实体 (entity_in_profit/loss)
        # "/v1/metrics/entities/profit_relative",

        # # -- 盈利/亏损中的 UTXO (UTXO_in_profit/loss)
        # "/v1/metrics/blockchain/utxo_profit_relative",
        # "/v1/metrics/blockchain/utxo_profit_count",
        # "/v1/metrics/blockchain/utxo_loss_count",
        
        # # -- 盈利/亏损中的转移量 (transfer_volume_in_profit/loss)
        # "/v1/metrics/transactions/transfers_volume_profit_relative",
        # "/v1/metrics/transactions/transfers_volume_profit_sum",
        # "/v1/metrics/transactions/transfers_volume_loss_sum",



        # # - 信号 (signals)
        # "/v1/metrics/signals/btc_sharpe_signal",



        # # - UTXOs
        # # -- UTXO 交易量 (UTXO_volume)
        # "/v1/metrics/blockchain/utxo_created_value_sum",
        # "/v1/metrics/blockchain/utxo_created_value_mean",
        # "/v1/metrics/blockchain/utxo_created_value_median",
        # "/v1/metrics/blockchain/utxo_spent_value_sum",
        # "/v1/metrics/blockchain/utxo_spent_value_mean",
        # "/v1/metrics/blockchain/utxo_spent_value_median",

        # # -- UTXO 增长 (UTXO_growth)
        # "/v1/metrics/blockchain/utxo_created_count",
        # "/v1/metrics/blockchain/utxo_spent_count",
        # "/v1/metrics/blockchain/utxo_count",

        # # - 币时 (cointime)
        # "/v1/metrics/indicators/coin_blocks_created",
        # "/v1/metrics/indicators/coin_blocks_destroyed"
    ]

    common_params = {
    'a': 'BTC',  
    'i': '24h'   # 间隔: 24小时
    }

    # 循环调用您指定的新端点
    for path in endpoints_to_call:
        print(f"--- 正在查询: {path} (参数: {common_params}) ---")
        
        resp_metric = requests.get(f"{BASE_URL}{path}", headers=headers, params=common_params)
        resp_metric.raise_for_status()
        
        print(f"Data for {path}:", resp_metric.json())
        print("---" * 10)
        
        # 在两次请求之间短暂暂停，以避免触发速率限制
        time.sleep(1) 

except requests.exceptions.RequestException as e:
    print(f"\n请求出错: {e}")