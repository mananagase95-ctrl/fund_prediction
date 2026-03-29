"""
数据库操作模块 — SQLite + 简洁的 CRUD 封装
"""
import sqlite3
from config import config


def get_db():
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS funds (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                code        TEXT    UNIQUE NOT NULL,
                name        TEXT    DEFAULT '',
                fund_type   TEXT    DEFAULT '',
                added_at    TEXT    DEFAULT (datetime('now','localtime')),
                last_updated TEXT
            );

            CREATE TABLE IF NOT EXISTS fund_nav (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                fund_code   TEXT    NOT NULL,
                nav_date    TEXT    NOT NULL,
                nav         REAL,
                acc_nav     REAL,
                daily_return REAL,
                UNIQUE(fund_code, nav_date)
            );
            CREATE INDEX IF NOT EXISTS idx_fund_nav
                ON fund_nav(fund_code, nav_date DESC);

            CREATE TABLE IF NOT EXISTS news (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                title        TEXT    NOT NULL,
                content      TEXT    DEFAULT '',
                source       TEXT    DEFAULT '',
                url          TEXT    DEFAULT '',
                published_at TEXT,
                fetched_at   TEXT    DEFAULT (datetime('now','localtime')),
                sentiment    REAL    DEFAULT 0,
                keywords     TEXT    DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_news_date
                ON news(published_at DESC);

            CREATE TABLE IF NOT EXISTS analysis (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                fund_code        TEXT NOT NULL,
                recommendation   TEXT,
                technical_score  REAL,
                sentiment_score  REAL,
                full_analysis    TEXT,
                created_at       TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE INDEX IF NOT EXISTS idx_analysis
                ON analysis(fund_code, created_at DESC);
        """)


# ── Fund ────────────────────────────────────────────────────

def get_all_funds():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM funds ORDER BY added_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_fund(code):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM funds WHERE code = ?", (code,)
        ).fetchone()
        return dict(row) if row else None


def add_fund(code, name='', fund_type=''):
    with get_db() as conn:
        try:
            conn.execute(
                "INSERT INTO funds (code, name, fund_type) VALUES (?, ?, ?)",
                (code, name, fund_type)
            )
            return True
        except sqlite3.IntegrityError:
            return False  # already exists


def delete_fund(code):
    with get_db() as conn:
        conn.execute("DELETE FROM funds WHERE code = ?", (code,))
        conn.execute("DELETE FROM fund_nav WHERE fund_code = ?", (code,))
        conn.execute("DELETE FROM analysis WHERE fund_code = ?", (code,))


def update_fund_info(code, name, fund_type):
    with get_db() as conn:
        conn.execute(
            """UPDATE funds
               SET name = ?, fund_type = ?,
                   last_updated = datetime('now','localtime')
               WHERE code = ?""",
            (name, fund_type, code)
        )


# ── NAV ─────────────────────────────────────────────────────

def save_nav_data(fund_code, records):
    """records: list of (nav_date, nav, acc_nav, daily_return)"""
    with get_db() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO fund_nav
               (fund_code, nav_date, nav, acc_nav, daily_return)
               VALUES (?, ?, ?, ?, ?)""",
            [(fund_code, r[0], r[1], r[2], r[3]) for r in records]
        )


def get_nav_data(fund_code, limit=500):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT nav_date, nav, acc_nav, daily_return
               FROM fund_nav
               WHERE fund_code = ?
               ORDER BY nav_date DESC LIMIT ?""",
            (fund_code, limit)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]


def get_latest_nav(fund_code):
    with get_db() as conn:
        row = conn.execute(
            """SELECT nav_date, nav, acc_nav, daily_return
               FROM fund_nav WHERE fund_code = ?
               ORDER BY nav_date DESC LIMIT 1""",
            (fund_code,)
        ).fetchone()
        return dict(row) if row else {}


# ── News ────────────────────────────────────────────────────

def save_news(news_list):
    """news_list: list of (title, content, source, url, published_at, sentiment, keywords)"""
    saved = 0
    with get_db() as conn:
        for item in news_list:
            try:
                conn.execute(
                    """INSERT INTO news
                       (title, content, source, url, published_at, sentiment, keywords)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    item
                )
                saved += 1
            except sqlite3.IntegrityError:
                pass  # duplicate URL
    return saved


def get_news(limit=60, source=None):
    with get_db() as conn:
        if source:
            rows = conn.execute(
                "SELECT * FROM news WHERE source = ? ORDER BY published_at DESC LIMIT ?",
                (source, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM news ORDER BY published_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


def get_recent_news_sentiment(hours=48):
    """Return average sentiment of news in the last N hours."""
    with get_db() as conn:
        row = conn.execute(
            """SELECT AVG(sentiment) as avg_sentiment, COUNT(*) as cnt
               FROM news
               WHERE published_at >= datetime('now', ?, 'localtime')""",
            (f'-{hours} hours',)
        ).fetchone()
        if row and row['cnt'] > 0:
            return row['avg_sentiment'] or 0.0, row['cnt']
        return 0.0, 0


# ── Analysis ────────────────────────────────────────────────

def save_analysis(fund_code, recommendation, technical_score, sentiment_score, full_analysis):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO analysis
               (fund_code, recommendation, technical_score, sentiment_score, full_analysis)
               VALUES (?, ?, ?, ?, ?)""",
            (fund_code, recommendation, technical_score, sentiment_score, full_analysis)
        )


def get_latest_analysis(fund_code):
    with get_db() as conn:
        row = conn.execute(
            """SELECT * FROM analysis WHERE fund_code = ?
               ORDER BY created_at DESC LIMIT 1""",
            (fund_code,)
        ).fetchone()
        return dict(row) if row else None


def get_analysis_history(fund_code, limit=10):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM analysis WHERE fund_code = ?
               ORDER BY created_at DESC LIMIT ?""",
            (fund_code, limit)
        ).fetchall()
        return [dict(r) for r in rows]
