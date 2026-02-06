import sqlite3

def get_db_connection():
    conn = sqlite3.connect("database.db", timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000;")  # espera 30s si está bloqueada
    return conn
