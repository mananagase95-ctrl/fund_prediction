"""
基金数据拉取模块
使用 akshare 拉取基金基本信息和净值历史数据
支持：开放式基金、ETF、LOF
"""
import logging
from datetime import datetime, timedelta

import akshare as ak
import pandas as pd

from database import add_fund, get_fund, save_nav_data, update_fund_info
from config import config

logger = logging.getLogger(__name__)


# ── 基金基本信息 ──────────────────────────────────────────────

def fetch_fund_info(code: str) -> dict:
    """查询基金名称和类型，失败时返回带默认值的字典。"""
    info = {'code': code, 'name': code, 'fund_type': '未知'}

    # 1) 开放式基金列表
    try:
        df = ak.fund_open_fund_daily_em()
        if df is not None and not df.empty:
            col_code = '基金代码' if '基金代码' in df.columns else df.columns[0]
            col_name = '基金简称' if '基金简称' in df.columns else df.columns[1]
            match = df[df[col_code].astype(str) == code]
            if not match.empty:
                info['name'] = str(match.iloc[0][col_name])
                info['fund_type'] = '开放式基金'
                return info
    except Exception as e:
        logger.debug(f"开放式基金查询失败 {code}: {e}")

    # 2) ETF 列表
    try:
        df = ak.fund_etf_spot_em()
        if df is not None and not df.empty:
            col_code = '代码' if '代码' in df.columns else df.columns[0]
            col_name = '名称' if '名称' in df.columns else df.columns[1]
            match = df[df[col_code].astype(str) == code]
            if not match.empty:
                info['name'] = str(match.iloc[0][col_name])
                info['fund_type'] = 'ETF基金'
                return info
    except Exception as e:
        logger.debug(f"ETF 查询失败 {code}: {e}")

    # 3) LOF 列表
    try:
        df = ak.fund_lof_spot_em()
        if df is not None and not df.empty:
            col_code = '代码' if '代码' in df.columns else df.columns[0]
            col_name = '名称' if '名称' in df.columns else df.columns[1]
            match = df[df[col_code].astype(str) == code]
            if not match.empty:
                info['name'] = str(match.iloc[0][col_name])
                info['fund_type'] = 'LOF基金'
                return info
    except Exception as e:
        logger.debug(f"LOF 查询失败 {code}: {e}")

    return info


# ── 净值历史 ──────────────────────────────────────────────────

def _parse_date(val) -> str:
    """将各种日期格式统一成 YYYY-MM-DD 字符串。"""
    if isinstance(val, pd.Timestamp):
        return val.strftime('%Y-%m-%d')
    s = str(val)
    # 处理 "2024-01-01" 或 "20240101" 格式
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s[:10]


def _resolve_open_fund_period(days: int) -> str:
    """将天数映射为 akshare 开放式基金接口支持的 period。"""
    if days <= 31:
        return "1月"
    if days <= 93:
        return "3月"
    if days <= 186:
        return "6月"
    if days <= 366:
        return "1年"
    if days <= 365 * 3:
        return "3年"
    if days <= 365 * 5:
        return "5年"
    return "成立来"


def fetch_open_fund_nav(code: str, days: int) -> list:
    """拉取开放式基金净值历史（东方财富）。"""
    records = []
    try:
        period = _resolve_open_fund_period(days)
        df_unit = ak.fund_open_fund_info_em(
            symbol=code,
            indicator="单位净值走势",
            period=period,
        )
        if df_unit is None or df_unit.empty:
            return []

        # 尝试获取累计净值
        acc_map = {}
        try:
            df_acc = ak.fund_open_fund_info_em(
                symbol=code,
                indicator="累计净值走势",
                period=period,
            )
            if df_acc is not None and not df_acc.empty:
                for _, row in df_acc.iterrows():
                    d = _parse_date(row.iloc[0])
                    v = float(row.iloc[1]) if pd.notna(row.iloc[1]) else 0
                    acc_map[d] = v
        except Exception:
            pass

        for _, row in df_unit.iterrows():
            d = _parse_date(row.iloc[0])
            nav = float(row.iloc[1]) if pd.notna(row.iloc[1]) else 0
            daily_ret = float(row.iloc[2]) if len(row) > 2 and pd.notna(row.iloc[2]) else 0
            acc = acc_map.get(d, nav)
            if nav > 0:
                records.append((d, nav, acc, daily_ret))

        # 按日期升序返回
        records.sort(key=lambda x: x[0])
        return records
    except Exception as e:
        logger.warning(f"开放式基金净值拉取失败 {code}: {e}")
        return []


def fetch_etf_nav(code: str, days: int) -> list:
    """拉取 ETF/LOF 净值历史（东方财富行情）。"""
    end_date = datetime.now().strftime('%Y%m%d')
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
    records = []

    for fetch_fn in [ak.fund_etf_hist_em, ak.fund_lof_hist_em]:
        try:
            df = fetch_fn(
                symbol=code, period='daily',
                start_date=start_date, end_date=end_date, adjust=''
            )
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    d = _parse_date(row['日期'])
                    nav = float(row['收盘']) if pd.notna(row['收盘']) else 0
                    daily_ret = 0
                    if '涨跌幅' in row and pd.notna(row['涨跌幅']):
                        daily_ret = float(row['涨跌幅'])
                    if nav > 0:
                        records.append((d, nav, nav, daily_ret))
                records.sort(key=lambda x: x[0])
                return records
        except Exception as e:
            logger.debug(f"{fetch_fn.__name__} 失败 {code}: {e}")

    return records


def fetch_fund_nav_history(code: str, days: int = None) -> list:
    """
    优先尝试开放式基金接口，失败则尝试 ETF/LOF 接口。
    返回列表：[(date_str, nav, acc_nav, daily_return), ...]，按日期升序。
    """
    if days is None:
        days = config.FUND_HISTORY_DAYS

    records = fetch_open_fund_nav(code, days)
    if not records:
        records = fetch_etf_nav(code, days)
    return records


# ── 主更新入口 ────────────────────────────────────────────────

def update_fund_data(code: str) -> tuple:
    """
    更新指定基金的基本信息和净值历史。
    返回 (success: bool, message: str)
    """
    code = code.strip()
    try:
        # 若数据库中没有该基金，先插入占位
        if not get_fund(code):
            add_fund(code, name=code, fund_type='')

        # 拉取基本信息
        info = fetch_fund_info(code)
        update_fund_info(code, info['name'], info['fund_type'])

        # 拉取净值历史
        records = fetch_fund_nav_history(code)
        if not records:
            return False, "未能获取到净值数据，请核实基金代码是否正确（支持：开放式基金、ETF、LOF）"

        save_nav_data(code, records)
        latest_nav = records[-1][1]
        return True, (
            f"更新成功：共 {len(records)} 条净值记录，"
            f"最新净值 {latest_nav:.4f}（{records[-1][0]}）"
        )

    except Exception as e:
        logger.error(f"更新基金 {code} 失败: {e}", exc_info=True)
        return False, f"更新失败：{e}"
