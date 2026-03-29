"""
新闻数据拉取模块
数据源：
  1. akshare - CCTV 联播新闻（政策/宏观）
  2. 新浪财经 滚动新闻 API
  3. 东方财富 财经新闻 API
  4. akshare - 百度财经新闻
情感分析使用 SnowNLP（支持中文）。
"""
import json
import logging
from datetime import datetime

import requests

from database import save_news
from config import config

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    )
}


# ── 情感分析 ──────────────────────────────────────────────────

def _sentiment_score(text: str) -> float:
    """
    返回 [-1, 1] 范围内的情感分值。
    正值偏利好，负值偏利空。
    依赖 SnowNLP；不可用时使用关键词规则兜底。
    """
    if not text:
        return 0.0
    try:
        from snownlp import SnowNLP
        # SnowNLP 返回 [0, 1]，转换到 [-1, 1]
        score = SnowNLP(text[:500]).sentiments
        return round(score * 2 - 1, 4)
    except Exception:
        pass

    # 关键词规则兜底
    positive = ['上涨', '增长', '利好', '突破', '强势', '回升', '走强', '盈利', '增持', '看多']
    negative = ['下跌', '下滑', '利空', '跌破', '弱势', '回落', '走弱', '亏损', '减持', '看空']
    pos = sum(1 for w in positive if w in text)
    neg = sum(1 for w in negative if w in text)
    total = pos + neg
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 4)


# ── 各数据源拉取 ──────────────────────────────────────────────

def _fetch_sina_finance() -> list:
    """新浪财经滚动新闻（财经 + 股票）"""
    results = []
    endpoints = [
        # 财经要闻
        'https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&k=&num=50&page=1',
        # 股市要闻
        'https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2514&k=&num=50&page=1',
    ]
    for url in endpoints:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=config.REQUEST_TIMEOUT)
            data = resp.json()
            items = data.get('result', {}).get('data', [])
            for item in items:
                title = item.get('title', '').strip()
                intro = item.get('intro', '').strip()
                pub_ts = item.get('mtime', item.get('ctime', ''))
                try:
                    pub_dt = datetime.fromtimestamp(int(pub_ts)).strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    pub_dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                link = item.get('url', '')
                if title:
                    sentiment = _sentiment_score(title + ' ' + intro)
                    results.append((
                        title, intro, '新浪财经', link, pub_dt, sentiment, ''
                    ))
        except Exception as e:
            logger.warning(f"新浪财经抓取失败: {e}")
    return results


def _fetch_eastmoney_news() -> list:
    """东方财富财经热闻"""
    results = []
    url = (
        'https://np-cnotice.eastmoney.com/api/public/gct'
        '?cb=&client=APP&type=1&pageSize=50&pageIndex=1'
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=config.REQUEST_TIMEOUT)
        data = resp.json()
        items = data.get('data', {}).get('list', [])
        for item in items:
            title = item.get('title', '').strip()
            content = item.get('art_code', '').strip()
            pub_str = item.get('sendTime', '')
            link = f"https://caifuhao.eastmoney.com/news/{item.get('art_code', '')}"
            if title:
                sentiment = _sentiment_score(title)
                results.append((
                    title, content, '东方财富', link, pub_str, sentiment, ''
                ))
    except Exception as e:
        logger.warning(f"东方财富抓取失败: {e}")
    return results


def _fetch_cctv_news() -> list:
    """CCTV 新闻联播文字稿（政策/宏观向）"""
    results = []
    try:
        import akshare as ak
        today = datetime.now().strftime('%Y%m%d')
        df = ak.news_cctv(date=today)
        if df is None or df.empty:
            # 尝试昨天
            from datetime import timedelta
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
            df = ak.news_cctv(date=yesterday)
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                title = str(row.get('题目', row.get('title', ''))).strip()
                content = str(row.get('内容', row.get('content', ''))).strip()
                pub_str = str(row.get('date', datetime.now().strftime('%Y-%m-%d')))
                if title:
                    sentiment = _sentiment_score(title + ' ' + content[:200])
                    results.append((
                        title, content[:1000], 'CCTV新闻联播', '', pub_str, sentiment, ''
                    ))
    except Exception as e:
        logger.warning(f"CCTV 新闻抓取失败: {e}")
    return results


def _fetch_akshare_economic_news() -> list:
    """Akshare 百度财经新闻"""
    results = []
    try:
        import akshare as ak
        df = ak.news_economic_baidu()
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                title = str(row.iloc[0]).strip() if len(row) > 0 else ''
                content = str(row.iloc[1]).strip() if len(row) > 1 else ''
                pub_str = str(row.iloc[2]).strip() if len(row) > 2 else datetime.now().strftime('%Y-%m-%d')
                if title and title != 'nan':
                    sentiment = _sentiment_score(title + ' ' + content[:200])
                    results.append((
                        title, content[:1000], '百度财经', '', pub_str, sentiment, ''
                    ))
    except Exception as e:
        logger.warning(f"百度财经新闻抓取失败: {e}")
    return results


def _fetch_akshare_stock_news() -> list:
    """Akshare 股市新闻（东财）"""
    results = []
    try:
        import akshare as ak
        df = ak.stock_news_em(symbol="000001")   # 以上证指数为锚拉取市场新闻
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                title = str(row.get('新闻标题', row.get('title', ''))).strip()
                content = str(row.get('新闻内容', row.get('content', ''))).strip()
                pub_str = str(row.get('发布时间', row.get('date', ''))).strip()
                link = str(row.get('新闻链接', '')).strip()
                if title and title != 'nan':
                    sentiment = _sentiment_score(title + ' ' + content[:200])
                    results.append((
                        title, content[:1000], '东财股市新闻', link, pub_str, sentiment, ''
                    ))
    except Exception as e:
        logger.warning(f"东财股市新闻抓取失败: {e}")
    return results


# ── 主入口 ────────────────────────────────────────────────────

def fetch_all_news() -> tuple:
    """
    从所有数据源拉取新闻并保存到数据库。
    返回 (success: bool, message: str)
    """
    all_news = []

    fetchers = [
        ('新浪财经',       _fetch_sina_finance),
        ('东方财富',       _fetch_eastmoney_news),
        ('CCTV联播',       _fetch_cctv_news),
        ('百度财经',       _fetch_akshare_economic_news),
        ('东财股市新闻',   _fetch_akshare_stock_news),
    ]

    source_counts = {}
    for name, fn in fetchers:
        try:
            items = fn()
            all_news.extend(items)
            source_counts[name] = len(items)
            logger.info(f"{name}: 获取 {len(items)} 条")
        except Exception as e:
            logger.error(f"{name} 拉取异常: {e}")
            source_counts[name] = 0

    if not all_news:
        return False, "所有新闻源均未返回数据，请检查网络连接"

    saved = save_news(all_news)
    summary = '、'.join(f"{k}:{v}条" for k, v in source_counts.items() if v > 0)
    return True, f"新增保存 {saved} 条新闻（{summary}）"
