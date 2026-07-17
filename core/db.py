import sqlite3
import os
from datetime import datetime

# Database file location
DB_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DB_PATH = os.path.join(DB_DIR, "reelsbot.db")

def init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                tier TEXT DEFAULT 'free',
                processed_reels INTEGER DEFAULT 0,
                total_allowed_reels INTEGER DEFAULT 50,
                processed_asks INTEGER DEFAULT 0,
                total_allowed_asks INTEGER DEFAULT 10,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Dynamic schema migration for existing databases
        for col_name, col_type, default_val in [
            ("processed_asks", "INTEGER", 0),
            ("total_allowed_asks", "INTEGER", 10)
        ]:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type} DEFAULT {default_val}")
            except sqlite3.OperationalError:
                pass # Already exists
                
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                amount_usd REAL,
                credits_added INTEGER,
                asks_added INTEGER,
                tier_assigned TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (telegram_id) REFERENCES users (telegram_id)
            )
        ''')
        # Dynamic schema migration for transactions table
        for col_name, col_type, default_val in [
            ("asks_added", "INTEGER", 0),
            ("tier_assigned", "TEXT", "NULL")
        ]:
            try:
                cursor.execute(f"ALTER TABLE transactions ADD COLUMN {col_name} {col_type} DEFAULT {default_val}")
            except sqlite3.OperationalError:
                pass
                
        conn.commit()

def get_or_create_user(telegram_id: int) -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        user = cursor.fetchone()
        
        if not user:
            cursor.execute('''
                INSERT INTO users (telegram_id, total_allowed_reels, total_allowed_asks) 
                VALUES (?, 50, 10)
            ''', (telegram_id,))
            conn.commit()
            cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            user = cursor.fetchone()
            
        return dict(user)

def increment_processed(telegram_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET processed_reels = processed_reels + 1 
            WHERE telegram_id = ?
        ''', (telegram_id,))
        conn.commit()

def increment_asks(telegram_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET processed_asks = processed_asks + 1 
            WHERE telegram_id = ?
        ''', (telegram_id,))
        conn.commit()

def add_credits(telegram_id: int, amount_reels: int, amount_usd: float = 0.0, amount_asks: int = 10, tier_name: str = 'premium'):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET total_allowed_reels = total_allowed_reels + ?, 
                total_allowed_asks = total_allowed_asks + ?,
                tier = ?
            WHERE telegram_id = ?
        ''', (amount_reels, amount_asks, tier_name, telegram_id))
        
        cursor.execute('''
            INSERT INTO transactions (telegram_id, amount_usd, credits_added, asks_added, tier_assigned)
            VALUES (?, ?, ?, ?, ?)
        ''', (telegram_id, amount_usd, amount_reels, amount_asks, tier_name))
        conn.commit()

def has_quota(telegram_id: int) -> bool:
    user = get_or_create_user(telegram_id)
    return user['processed_reels'] < user['total_allowed_reels']

def has_ask_quota(telegram_id: int) -> bool:
    user = get_or_create_user(telegram_id)
    return user['processed_asks'] < user['total_allowed_asks']

# Initialize tables when the module is imported
init_db()
