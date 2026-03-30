import os
from pathlib import Path
import yaml
from dotenv import load_dotenv

load_dotenv()


def _load_api_config() -> dict:
    """读取 api_config.yaml，读不到则返回空 dict，由调用方回退到环境变量。"""
    path = Path(__file__).parent / 'api_config.yaml'
    try:
        with open(path, encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"[config] 读取 api_config.yaml 失败: {e}")
        return {}


_api = _load_api_config()


def _api_get(key: str, env_fallback: str, default: str = '') -> str:
    """优先取配置文件，再取环境变量，最后用 default。"""
    return _api.get(key) or os.getenv(env_fallback) or default


class Config:
    # 数据库
    DATABASE_PATH = os.getenv('DATABASE_PATH', 'fund_analysis.db')

    # AI API 配置：api_config.json → 系统环境变量 → 内置默认值
    AI_API_KEY  = _api_get('AI_API_KEY',  'ANTHROPIC_API_KEY')
    AI_API_BASE = _api_get('AI_API_BASE', 'ANTHROPIC_BASE_URL',  'https://api.openai.com/v1')
    AI_MODEL    = _api_get('AI_MODEL',    'ANTHROPIC_DEFAULT_HAIKU_MODEL', 'gpt-3.5-turbo')

    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'fund-analysis-dev-key')
    DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'

    # 数据拉取
    FUND_HISTORY_DAYS = int(os.getenv('FUND_HISTORY_DAYS', '365'))
    REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '30'))
    NEWS_FETCH_COUNT = 50


config = Config()
