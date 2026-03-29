import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # 数据库
    DATABASE_PATH = os.getenv('DATABASE_PATH', 'fund_analysis.db')

    # AI API 配置（兼容 OpenAI 协议）
    AI_API_KEY = os.getenv('AI_API_KEY', '')
    AI_API_BASE = os.getenv('AI_API_BASE', 'https://api.openai.com/v1')
    AI_MODEL = os.getenv('AI_MODEL', 'gpt-3.5-turbo')

    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'fund-analysis-dev-key')
    DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'

    # 数据拉取
    FUND_HISTORY_DAYS = int(os.getenv('FUND_HISTORY_DAYS', '365'))
    REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '30'))
    NEWS_FETCH_COUNT = 50


config = Config()
