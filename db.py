import logging
from config import settings
import sqlite3

logger = logging.getLogger(__name__)

def db_connect():
    conn = sqlite3.connect(settings.DATABASE_PATH, timeout=30, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    return conn

def init_db():
    conn = db_connect()
    try:
        conn.execute("""
        CREATE TABLE "active_users" (
	    "tg_id"	INTEGER NOT NULL UNIQUE,
	    "is_reg"	INTEGER,
    	"ttl"	INTEGER,
    	"lock"	INTEGER,
    	"task_id"	INTEGER UNIQUE,
    	PRIMARY KEY("tg_id")
                     );""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_next_run ON active_tasks(next_run_at)")
        conn.commit()
    finally:
        conn.close()

def get_user(tg_id: int):
    conn = db_connect()
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT * FROM active_users WHERE tg_id = ?",
            (tg_id,)
        )
        user = cursor.fetchone()

        if user:
            return dict(user)

        return None

    finally:
        conn.close()

def delete_user(tg_id: int):
    conn = db_connect()
    try:
        conn.execute("DELETE FROM active_users WHERE tg_id = ?",
                      (tg_id,))
        conn.commit()
    finally:
        conn.close()

def user_registration(tg_id: int) :
    conn = db_connect()
    try:
        conn.execute(
            "INSERT INTO active_users (tg_id) VALUES (?)",
            (tg_id,),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error when registering user {tg_id}: {e}")
        return False
    finally:
        conn.close()
