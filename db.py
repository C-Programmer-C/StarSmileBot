import logging
from datetime import datetime, timezone, timedelta, time
from typing import List
from zoneinfo import ZoneInfo
from config import settings
import sqlite3

def db_connect():
    conn = sqlite3.connect(settings.DATABASE_PATH, timeout=30, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    return conn

def init_db():
    try:
        conn = db_connect()
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
    
    try:
        conn = db_connect()
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
    try:
        conn = db_connect()
        conn.execute("DELETE FROM active_users WHERE tg_id = ?",
                      (tg_id,))
        conn.commit()
    finally:
        conn.close()

def user_registration(tg_id):
    try:
        conn = db_connect()
        cursor = conn.execute(
            "UPDATE active_users SET is_reg = 1 WHERE tg_id = ?", (tg_id,))
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()