import sqlite3
import os 
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30)  # espera hasta 30s
    conn.row_factory = sqlite3.Row

    # Hace que SQLite espere si está ocupado (mejor mensaje y menos locks)
    conn.execute("PRAGMA busy_timeout = 5000;")   # 5 segundos
    conn.execute("PRAGMA journal_mode = WAL;")    # mejora concurrencia
    conn.execute("PRAGMA foreign_keys = ON;")

    return conn
