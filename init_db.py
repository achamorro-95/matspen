import sqlite3
from database import get_db_connection
# ⚠️ AJUSTA ESTA RUTA SI TU DB ESTÁ EN OTRA CARPETA
DB_PATH = "database"   # <-- PON AQUÍ EL NOMBRE REAL

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def crear_tabla_producciones():
    conn = get_db_connection()

    conn.execute("""
    CREATE TABLE IF NOT EXISTS producciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cotizacion_id INTEGER NOT NULL UNIQUE,
        fecha_creada TEXT NOT NULL,
        fecha_entrega TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Pendiente',
        FOREIGN KEY (cotizacion_id) REFERENCES costeo(id)
    );
    """)

    conn.commit()
    conn.close()
    print("✅ Tabla 'producciones' creada correctamente")


if __name__ == "__main__":
    crear_tabla_producciones()