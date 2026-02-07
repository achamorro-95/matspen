import sqlite3
from werkzeug.security import generate_password_hash

DB_FILE = "database.db"  # cambia si tu db se llama distinto
NEW_PASSWORD = "AndresChamorro95"

conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row

# verifica columnas reales
cols = [c[1] for c in conn.execute("PRAGMA table_info(users);").fetchall()]
has_must = "must_change_password" in cols

new_hash = generate_password_hash(NEW_PASSWORD)

if has_must:
    conn.execute("""
        UPDATE users
        SET password = ?, must_change_password = 1
        WHERE username = 'admin'
    """, (new_hash,))
else:
    conn.execute("""
        UPDATE users
        SET password = ?
        WHERE username = 'admin'
    """, (new_hash,))

conn.commit()
conn.close()
print("✅ Admin reseteado. Password =", NEW_PASSWORD, "| must_change_password =", 1 if has_must else "N/A")
