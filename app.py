"""
Flask 主应用
路由说明：
  GET  /                     首页（持仓看板）
  POST /fund/add             添加基金
  POST /fund/<code>/delete   删除基金
  POST /fund/<code>/update   手动更新净值数据
  GET  /fund/<code>          基金详情页
  POST /fund/<code>/analyze  执行 AI 分析
  GET  /news                 新闻列表
  POST /news/fetch           手动抓取最新新闻
  GET  /api/fund/<code>/data 图表数据（JSON）
"""
import json
import logging
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, jsonify
)

from config import config
from database import (
    init_db, get_all_funds, get_fund, add_fund,
    delete_fund, get_nav_data, get_latest_nav,
    get_news, get_latest_analysis, get_analysis_history
)
from data_fetcher import update_fund_data
from news_fetcher import fetch_all_news
from analyzer import calc_indicators, run_analysis

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# 初始化数据库
with app.app_context():
    init_db()


# ── 辅助 ──────────────────────────────────────────────────────

def _flash_redirect(msg, category, endpoint, **kw):
    flash(msg, category)
    return redirect(url_for(endpoint, **kw))


# ── 首页 ──────────────────────────────────────────────────────

@app.route('/')
def index():
    funds = get_all_funds()
    # 为每只基金附加最新净值和最新建议
    fund_cards = []
    for f in funds:
        nav  = get_latest_nav(f['code'])
        ana  = get_latest_analysis(f['code'])
        fund_cards.append({**f, 'latest_nav': nav, 'latest_analysis': ana})
    return render_template('index.html', fund_cards=fund_cards)


# ── 基金管理 ──────────────────────────────────────────────────

@app.route('/fund/add', methods=['POST'])
def fund_add():
    code = request.form.get('code', '').strip()
    if not code:
        return _flash_redirect('请输入基金代码', 'danger', 'index')

    # 先在数据库中占位
    add_fund(code)

    # 立即拉取数据
    success, msg = update_fund_data(code)
    category = 'success' if success else 'warning'
    flash(f"{'添加成功' if success else '添加成功（数据获取失败）'}：{msg}", category)
    return redirect(url_for('fund_detail', code=code))


@app.route('/fund/<code>/delete', methods=['POST'])
def fund_delete(code):
    delete_fund(code)
    flash(f'已删除基金 {code}', 'info')
    return redirect(url_for('index'))


@app.route('/fund/<code>/update', methods=['POST'])
def fund_update(code):
    success, msg = update_fund_data(code)
    flash(msg, 'success' if success else 'danger')
    return redirect(url_for('fund_detail', code=code))


# ── 基金详情 ──────────────────────────────────────────────────

@app.route('/fund/<code>')
def fund_detail(code):
    fund = get_fund(code)
    if not fund:
        flash('基金不存在，请先添加', 'warning')
        return redirect(url_for('index'))

    nav_data    = get_nav_data(code, limit=365)
    latest_nav  = get_latest_nav(code)
    analysis    = get_latest_analysis(code)
    history     = get_analysis_history(code, limit=5)
    has_data    = len(nav_data) >= 5

    return render_template(
        'fund_detail.html',
        fund=fund,
        nav_data=nav_data,
        latest_nav=latest_nav,
        analysis=analysis,
        history=history,
        has_data=has_data,
        ai_enabled=bool(config.AI_API_KEY),
    )


@app.route('/fund/<code>/analyze', methods=['POST'])
def fund_analyze(code):
    success, msg, _ = run_analysis(code)
    flash(msg, 'success' if success else 'danger')
    return redirect(url_for('fund_detail', code=code))


# ── 新闻 ──────────────────────────────────────────────────────

@app.route('/news')
def news():
    source  = request.args.get('source', '')
    news_items = get_news(limit=60, source=source or None)
    # 收集所有来源
    all_news = get_news(limit=500)
    sources = sorted({n['source'] for n in all_news if n['source']})
    return render_template('news.html',
                           news_items=news_items,
                           sources=sources,
                           current_source=source)


@app.route('/news/fetch', methods=['POST'])
def news_fetch():
    success, msg = fetch_all_news()
    flash(msg, 'success' if success else 'danger')
    return redirect(url_for('news'))


# ── API：图表数据 ─────────────────────────────────────────────

@app.route('/api/fund/<code>/data')
def api_fund_data(code):
    days  = int(request.args.get('days', 365))
    nav_data = get_nav_data(code, limit=days)
    if not nav_data:
        return jsonify({'error': '暂无数据'}), 404

    indicators = calc_indicators(nav_data)
    if not indicators:
        return jsonify({'error': '数据不足，无法计算指标'}), 400

    return jsonify(indicators)


@app.route('/api/fund/<code>/summary')
def api_fund_summary(code):
    fund = get_fund(code)
    if not fund:
        return jsonify({'error': '基金不存在'}), 404
    nav  = get_latest_nav(code)
    ana  = get_latest_analysis(code)
    return jsonify({'fund': fund, 'latest_nav': nav, 'latest_analysis': ana})


# ── 错误页 ────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(e):
    logger.error(f"500 error: {e}")
    return render_template('500.html'), 500


if __name__ == '__main__':
    app.run(debug=config.DEBUG, host='0.0.0.0', port=5000)
