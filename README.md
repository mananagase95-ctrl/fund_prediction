# 基金分析系统

基于 Python + Flask 的一站式基金分析平台，整合基金净值数据、互联网金融/政策新闻，并通过大模型给出买卖投资建议。

---

## 功能概览

| 功能 | 说明 |
| --- | --- |
| **基金数据管理** | 支持开放式基金、ETF、LOF，输入6位代码自动拉取历史净值（akshare） |
| **手动更新数据** | 一键刷新最新净值，历史数据增量写入 SQLite |
| **技术分析图表** | MA5/10/20/60、布林带、RSI、MACD，Plotly 交互图表 |
| **新闻聚合** | 抓取新浪财经、东方财富、CCTV联播、百度财经多路来源，自动情感分析 |
| **AI 投资建议** | 调用大模型 API（支持 Anthropic Claude 及 OpenAI 兼容协议），综合技术面与新闻情绪给出买入/持有/减仓建议 |
| **规则引擎兜底** | 未配置 AI Key 时，自动切换为基于技术指标的规则引擎，仍可正常使用 |

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 AI API（可选）

复制模板文件并填入你的 API 信息：

```bash
cp api_config.example.yaml api_config.yaml
# 编辑 api_config.yaml 填入 AI_API_KEY 等配置
```

**支持的 AI 服务：**

| 服务商 | 协议 |
| --- | --- |
| Anthropic Claude | 原生 Anthropic SDK |
| OpenAI | OpenAI 兼容协议 |

> 不配置 AI Key 也可正常运行，系统会自动切换为规则引擎分析模式。

### 3. 启动服务

```bash
python app.py
```

访问 [http://127.0.0.1:5000](http://127.0.0.1:5000)

---

## 项目结构

```text
fund_prediction/
├── app.py                   # Flask 主应用 & 路由
├── config.py                # 配置加载（api_config.yaml / 环境变量）
├── database.py              # SQLite 数据库 CRUD
├── data_fetcher.py          # 基金净值数据拉取（akshare）
├── news_fetcher.py          # 新闻多源抓取 + 情感分析
├── analyzer.py              # 技术指标计算 + AI 分析
├── requirements.txt
├── api_config.example.yaml  # AI API 配置模板
├── .env.example
├── templates/
│   ├── base.html            # Bootstrap 5 暗色主题基础模板
│   ├── index.html           # 首页看板
│   ├── fund_detail.html     # 基金详情 + 图表 + AI分析
│   └── news.html            # 新闻列表
└── static/
    ├── css/style.css
    └── js/main.js
```

---

## 使用流程

1. **添加基金** → 首页点击「添加基金」，输入6位基金代码（如 `000001`、`510050`）
2. **更新数据** → 系统自动拉取净值历史；之后可随时手动点击「更新数据」
3. **查看图表** → 进入详情页，查看净值走势、MA均线、RSI、MACD 交互图表
4. **抓取新闻** → 新闻页面点击「抓取最新新闻」，自动从多个来源拉取并进行情感分析
5. **AI 分析** → 详情页点击「AI 分析」，系统将综合技术面 + 新闻情绪 → 调用大模型 → 给出买入/持有/减仓建议

---

## 技术指标说明

| 指标 | 参数 | 说明 |
| --- | --- | --- |
| MA | 5/10/20/60日 | 简单移动均线 |
| 布林带 | 20日, 2σ | 价格波动区间 |
| RSI | 14日 | 相对强弱，<30超卖，>70超买 |
| MACD | 12/26/9 | 趋势动量，金叉/死叉信号 |

---

## 免责声明

本系统仅作学习和研究用途，**不构成任何投资建议**。基金投资有风险，请结合自身情况谨慎决策。
