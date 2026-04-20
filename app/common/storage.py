import sqlite3
import json
import os
import logging
from typing import Optional, Dict, Any

class SQLiteStorage:
    def __init__(self, db_path: str = "./data/bilibili_bot.db"):
        self.db_path = db_path
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            logging.info(f"Created database directory: {db_dir}")
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS live_session (
                    room_id TEXT,
                    live_id TEXT,
                    title TEXT,
                    cover TEXT,
                    start_time INTEGER,
                    end_time INTEGER,
                    status TEXT,
                    retry_count INTEGER DEFAULT 0,
                    extra TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (room_id, live_id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS dynamic_session (
                    uid TEXT,
                    dynamic_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (uid, dynamic_id)
                )
            ''')
            # Attempt to add end_time column if it doesn't exist (for existing databases)
            try:
                cursor.execute('ALTER TABLE live_session ADD COLUMN end_time INTEGER')
            except sqlite3.OperationalError:
                # Column already exists
                pass
            conn.commit()
            logging.info(f"SQLite storage initialized at {self.db_path}")

    def get_dynamic(self, uid: str, dynamic_id: str) -> Optional[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT * FROM dynamic_session WHERE uid = ? AND dynamic_id = ?', 
                    (uid, dynamic_id)
                )
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logging.error(f"Error fetching dynamic for uid {uid}: {e}")
            return None

    def create_dynamic(self, uid: str, dynamic_id: str):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO dynamic_session (uid, dynamic_id)
                    VALUES (?, ?)
                ''', (uid, dynamic_id))
                conn.commit()
        except sqlite3.IntegrityError:
            pass
        except Exception as e:
            logging.error(f"Error creating dynamic record for uid {uid}: {e}")

    def get_session(self, room_id: str, live_id: str) -> Optional[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT * FROM live_session WHERE room_id = ? AND live_id = ?', 
                    (room_id, live_id)
                )
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logging.error(f"Error fetching session for room {room_id}: {e}")
            return None

    def create_session(self, room_id: str, live_id: str, title: str, cover: str, start_time: int, status: str, extra: dict):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO live_session 
                    (room_id, live_id, title, cover, start_time, status, extra)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (room_id, live_id, title, cover, start_time, status, json.dumps(extra, ensure_ascii=False)))
                conn.commit()
        except sqlite3.IntegrityError:
            # Already exists, just skip or update
            pass
        except Exception as e:
            logging.error(f"Error creating session for room {room_id}: {e}")

    def update_session_status(self, room_id: str, live_id: str, status: str):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE live_session SET status = ? WHERE room_id = ? AND live_id = ?
                ''', (status, room_id, live_id))
                conn.commit()
        except Exception as e:
            logging.error(f"Error updating status for room {room_id}: {e}")

    def mark_session_ended(self, room_id: str, end_time: int):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE live_session SET end_time = ? 
                    WHERE room_id = ? AND end_time IS NULL
                ''', (end_time, room_id))
                conn.commit()
                if cursor.rowcount > 0:
                    logging.info(f"Marked active session for room {room_id} as ended at {end_time}.")
        except Exception as e:
            logging.error(f"Error marking session ended for room {room_id}: {e}")

    def increment_retry_count(self, room_id: str, live_id: str) -> int:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE live_session SET retry_count = retry_count + 1 
                    WHERE room_id = ? AND live_id = ?
                ''', (room_id, live_id))
                conn.commit()
                
                cursor.execute('SELECT retry_count FROM live_session WHERE room_id = ? AND live_id = ?', (room_id, live_id))
                row = cursor.fetchone()
                return row[0] if row else 0
        except Exception as e:
            logging.error(f"Error incrementing retry for room {room_id}: {e}")
            return 0
