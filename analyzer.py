"""
分析与预测模块
1. 技术指标计算：MA、MACD、RSI、布林带
2. 技术评分
3. 调用大模型 API 生成投资建议
"""
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from database import (
    get_fund, get_nav_data, get_news,
    get_recent_news_sentiment, save_analysis
)
from config import config

logger = logging.getLogger(__name__)


# ── 技术指标计算 ──────────────────────────────────────────────

def calc_indicators(nav_list: list) -> dict:
    """
    输入 get_nav_data() 返回的列表（按日期升序）。
    返回包含各技术指标 Series 的字典，键值为多级 dict 或 ndarray。
    """
    if len(nav_list) < 5:
        return {}

    df = pd.DataFrame(nav_list)
    prices = df['nav'].astype(float)

    result = {
        'dates': df['nav_date'].tolist(),
        'nav':   prices.tolist(),
        'acc_nav': df['acc_nav'].astype(float).tolist(),
        'daily_return': df['daily_return'].astype(float).tolist(),
    }

    def _safe(v, digits=6):
        if pd.isna(v) or not np.isfinite(v):
            return None
        return round(float(v), digits)

    # ── 移动平均线
    for w in [5, 10, 20, 60]:
        key = f'ma{w}'
        ma = prices.rolling(window=w, min_periods=1).mean()
        result[key] = [_safe(v, 6) for v in ma]

    # ── EMA & MACD (12, 26, 9)
    ema12 = prices.ewm(span=12, adjust=False).mean()
    ema26 = prices.ewm(span=26, adjust=False).mean()
    dif   = ema12 - ema26
    dea   = dif.ewm(span=9, adjust=False).mean()
    macd  = (dif - dea) * 2  # 柱状图（MACD Bar）

    result['macd']     = [_safe(v, 6) for v in dif]
    result['signal']   = [_safe(v, 6) for v in dea]
    result['histogram'] = [_safe(v, 6) for v in macd]

    # ── RSI (14)
    delta = prices.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=13, adjust=False).mean()
    avg_loss = loss.ewm(com=13, adjust=False).mean()
    rs   = avg_gain / avg_loss.replace(0, np.nan)
    rsi  = 100 - (100 / (1 + rs))
    result['rsi'] = [50.0 if pd.isna(v) or not np.isfinite(v) else round(float(v), 2) for v in rsi]

    # ── 布林带 (20, 2)
    ma20 = prices.rolling(window=20, min_periods=1).mean()
    std20 = prices.rolling(window=20, min_periods=1).std()
    result['bb_upper'] = [_safe(v, 6) for v in (ma20 + 2 * std20)]
    result['bb_lower'] = [_safe(v, 6) for v in (ma20 - 2 * std20)]

    return result


def calc_technical_score(indicators: dict) -> float:
    """
    基于最新技术指标计算评分，范围 [-1, 1]。
    正值偏多（买入信号），负值偏空（卖出信号）。
    """
    if not indicators:
        return 0.0

    score = 0.0
    count = 0
    nav = indicators.get('nav', [])
    if not nav:
        return 0.0
    latest_nav = nav[-1]

    # 1) MA 多空排列
    ma5  = next((v for v in reversed(indicators.get('ma5',  [])) if v is not None), None)
    ma10 = next((v for v in reversed(indicators.get('ma10', [])) if v is not None), None)
    ma20 = next((v for v in reversed(indicators.get('ma20', [])) if v is not None), None)
    ma60 = next((v for v in reversed(indicators.get('ma60', [])) if v is not None), None)

    if ma5 and ma20:
        score += 1.0 if ma5 > ma20 else -1.0
        count += 1
    if ma5 and ma60:
        score += 0.8 if ma5 > ma60 else -0.8
        count += 1
    if ma10 and ma20:
        score += 0.6 if ma10 > ma20 else -0.6
        count += 1

    # 2) 价格与均线关系
    if ma20 and latest_nav:
        score += 0.5 if latest_nav > ma20 else -0.5
        count += 1

    # 3) RSI
    rsi_vals = [v for v in indicators.get('rsi', []) if v is not None]
    if rsi_vals:
        rsi = rsi_vals[-1]
        if rsi < 30:
            score += 1.0   # 超卖
        elif rsi < 45:
            score += 0.5
        elif rsi > 70:
            score -= 1.0   # 超买
        elif rsi > 60:
            score -= 0.5
        count += 1

    # 4) MACD 金叉/死叉
    macd_vals   = indicators.get('macd', [])
    signal_vals = indicators.get('signal', [])
    if len(macd_vals) >= 2 and len(signal_vals) >= 2:
        if macd_vals[-1] > signal_vals[-1]:
            score += 0.8
        else:
            score -= 0.8
        count += 1

    # 5) 短期涨跌动量（最近 5 日）
    daily_return = indicators.get('daily_return', [])
    if len(daily_return) >= 5:
        recent = daily_return[-5:]
        avg_ret = sum(r for r in recent if r is not None) / len(recent)
        score += min(max(avg_ret / 5.0, -1.0), 1.0)
        count += 1

    if count == 0:
        return 0.0
    return round(score / count, 4)


# ── 大模型投资分析 ────────────────────────────────────────────

def _build_prompt(fund: dict, indicators: dict, news_items: list,
                  tech_score: float, sentiment_score: float) -> str:
    """构建发送给大模型的分析提示词。"""
    nav_list = indicators.get('nav', [])
    dates    = indicators.get('dates', [])
    latest_nav  = nav_list[-1]  if nav_list  else 0
    latest_date = dates[-1]     if dates     else ''

    # 近期涨跌
    def pct_change(start_idx):
        if len(nav_list) > abs(start_idx) and nav_list[start_idx]:
            return round((latest_nav / nav_list[start_idx] - 1) * 100, 2)
        return None

    ret_5d  = pct_change(-6)
    ret_1m  = pct_change(-22)
    ret_3m  = pct_change(-66)

    # 技术指标最新值
    def last(key):
        vals = [v for v in indicators.get(key, []) if v is not None]
        return round(vals[-1], 4) if vals else 'N/A'

    tech_summary = (
        f"MA5={last('ma5')} | MA10={last('ma10')} | MA20={last('ma20')} | MA60={last('ma60')}\n"
        f"RSI={last('rsi')} | MACD={last('macd')} | Signal={last('signal')}"
    )

    # 新闻摘要（取最近 10 条标题）
    news_summary = '\n'.join(
        f"- [{item['source']}] {item['title']}"
        for item in news_items[:10]
    ) or '（暂无近期新闻）'

    score_desc = (
        "偏多（技术面较强）" if tech_score > 0.3 else
        "偏空（技术面较弱）" if tech_score < -0.3 else
        "中性"
    )
    sent_desc = (
        "市场情绪偏正面" if sentiment_score > 0.1 else
        "市场情绪偏负面" if sentiment_score < -0.1 else
        "市场情绪中性"
    )

    return f"""你是一位专业的中国公募基金分析师，请基于以下数据对该基金进行深度分析并给出明确投资建议。

## 基金基本信息
- 代码：{fund['code']}  名称：{fund.get('name', fund['code'])}  类型：{fund.get('fund_type', '未知')}
- 最新净值：{latest_nav:.4f}（{latest_date}）
- 近5日涨跌：{ret_5d}%  | 近1月：{ret_1m}%  | 近3月：{ret_3m}%

## 技术指标（最新值）
{tech_summary}

- 技术评分：{tech_score:.2f}（-1到1，正值偏多），当前：{score_desc}
- 情绪评分：{sentiment_score:.2f}（-1到1），当前：{sent_desc}

## 近期市场新闻摘要
{news_summary}

---

请按以下结构输出分析报告：

## 技术面分析
（根据均线排列、RSI、MACD、布林带等指标分析当前趋势）

## 市场情绪与宏观环境
（结合新闻事件、政策动态、市场情绪判断外部环境影响）

## 综合评判与投资建议
**建议操作**：[买入 / 持有 / 减仓 / 卖出]（只选其中一项）
**建议理由**：（2-4句核心逻辑）

## 主要风险
（列举1-3条需要关注的风险点）

## 操作策略
（具体点位建议，如止损线、加仓时机等）
"""


def _call_llm(prompt: str) -> str:
    """调用大模型 API，返回文本。API Key 未配置时返回 None。
    优先使用 Anthropic SDK（支持原生 Claude 协议），
    若 base_url 以 openai.com 结尾则回退到 OpenAI SDK。
    """
    if not config.AI_API_KEY:
        return None
    try:
        use_openai = 'openai.com' in (config.AI_API_BASE or '')
        if use_openai:
            from openai import OpenAI
            client = OpenAI(api_key=config.AI_API_KEY, base_url=config.AI_API_BASE)
            response = client.chat.completions.create(
                model=config.AI_MODEL,
                messages=[
                    {'role': 'system', 'content': '你是专业的中国公募基金投资顾问，分析准确、逻辑清晰。'},
                    {'role': 'user',   'content': prompt},
                ],
                temperature=0.3,
                max_tokens=2000,
            )
            return response.choices[0].message.content
        else:
            import anthropic
            client = anthropic.Anthropic(
                api_key=config.AI_API_KEY,
                base_url=config.AI_API_BASE,
                default_headers={'Token': config.AI_API_KEY},
            )
            response = client.messages.create(
                model=config.AI_MODEL,
                system='你是专业的中国公募基金投资顾问，分析准确、逻辑清晰。',
                messages=[{'role': 'user', 'content': prompt}],
                temperature=0.3,
                max_tokens=2000,
            )
            return response.content[0].text
    except Exception as e:
        logger.error(f"LLM API 调用失败: {e}")
        return None


def _parse_recommendation(text: str) -> str:
    """从 LLM 响应中提取操作建议标签。"""
    if not text:
        return 'HOLD'
    for keyword, label in [
        ('买入', 'BUY'), ('增持', 'BUY'),
        ('卖出', 'SELL'), ('减仓', 'SELL'),
        ('持有', 'HOLD'), ('观望', 'HOLD'),
    ]:
        if keyword in text:
            return label
    return 'HOLD'


def _rule_based_analysis(fund: dict, tech_score: float,
                          sentiment_score: float, indicators: dict) -> str:
    """当 LLM 不可用时，基于规则生成简单分析报告。"""
    nav_list = indicators.get('nav', [])
    latest_nav = nav_list[-1] if nav_list else 0
    rsi_vals = [v for v in indicators.get('rsi', []) if v is not None]
    rsi = rsi_vals[-1] if rsi_vals else 50

    def last(key):
        vals = [v for v in indicators.get(key, []) if v is not None]
        return vals[-1] if vals else None

    ma5, ma20 = last('ma5'), last('ma20')
    macd, signal = last('macd'), last('signal')

    lines = [
        f"## 技术面分析（规则引擎）",
        f"- 当前净值：{latest_nav:.4f}",
        f"- MA5={ma5:.4f}  MA20={ma20:.4f}" if ma5 and ma20 else "",
        f"- MA5 {'>' if ma5 and ma20 and ma5 > ma20 else '<'} MA20：{'均线多头排列' if ma5 and ma20 and ma5 > ma20 else '均线空头排列'}",
        f"- RSI={rsi:.1f}：{'超卖区间，关注反弹' if rsi < 30 else '超买区间，注意回调' if rsi > 70 else '正常区间'}",
        f"- MACD {'金叉' if macd and signal and macd > signal else '死叉'}",
        f"\n## 市场情绪",
        f"近期新闻情绪评分：{sentiment_score:.2f}（{'偏正面' if sentiment_score > 0.1 else '偏负面' if sentiment_score < -0.1 else '中性'}）",
        f"\n## 综合评判与投资建议",
    ]

    combined = tech_score * 0.6 + sentiment_score * 0.4
    if combined > 0.25:
        rec = "**建议操作**：买入"
        reason = "技术指标偏多，市场情绪较好，可考虑逢低布局。"
    elif combined < -0.25:
        rec = "**建议操作**：减仓 / 卖出"
        reason = "技术指标偏弱，市场情绪偏负面，建议控制仓位。"
    else:
        rec = "**建议操作**：持有"
        reason = "技术面与情绪面信号混合，建议维持现有仓位，等待更明确趋势。"

    lines += [rec, f"**建议理由**：{reason}"]
    lines += ["\n## 风险提示", "- 本分析仅供参考，不构成投资建议。", "- 基金投资有风险，需结合自身风险承受能力决策。"]
    lines += ["\n> ⚠️ 未配置 AI_API_KEY，当前为规则引擎生成的简要分析。"]

    return '\n'.join(l for l in lines if l is not None)


# ── 主分析入口 ────────────────────────────────────────────────

def run_analysis(fund_code: str) -> tuple:
    """
    执行完整分析流程并持久化结果。
    返回 (success: bool, message: str, analysis_dict: dict)
    """
    fund = get_fund(fund_code)
    if not fund:
        return False, "基金不存在，请先添加并更新数据", {}

    # 1) 拉取净值数据
    nav_data = get_nav_data(fund_code, limit=500)
    if len(nav_data) < 10:
        return False, "净值数据不足（<10条），请先更新数据", {}

    # 2) 计算技术指标
    indicators = calc_indicators(nav_data)
    tech_score = calc_technical_score(indicators)

    # 3) 获取近期新闻及情感分数
    news_items = get_news(limit=30)
    avg_sentiment, news_count = get_recent_news_sentiment(hours=72)

    # 4) 构建提示词并调用 LLM
    prompt = _build_prompt(fund, indicators, news_items, tech_score, avg_sentiment)
    llm_result = _call_llm(prompt)

    if llm_result:
        full_analysis = llm_result
        recommendation = _parse_recommendation(llm_result)
    else:
        full_analysis = _rule_based_analysis(fund, tech_score, avg_sentiment, indicators)
        recommendation_map = {
            v: k for k, v in [
                ('BUY', 0.25), ('SELL', -0.25)
            ]
        }
        combined = tech_score * 0.6 + avg_sentiment * 0.4
        if combined > 0.25:
            recommendation = 'BUY'
        elif combined < -0.25:
            recommendation = 'SELL'
        else:
            recommendation = 'HOLD'

    # 5) 持久化
    save_analysis(fund_code, recommendation, tech_score, avg_sentiment, full_analysis)

    return True, f"分析完成（技术评分：{tech_score:.2f}，新闻情绪：{avg_sentiment:.2f}）", {
        'recommendation': recommendation,
        'technical_score': tech_score,
        'sentiment_score': avg_sentiment,
        'full_analysis':   full_analysis,
    }
