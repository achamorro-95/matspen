from flask import Flask, render_template, request, redirect, session, url_for, flash
from werkzeug.security import check_password_hash
from database import get_db_connection
import  math
from datetime import datetime
import os 
from dotenv import load_dotenv
import logging
from flask_wtf.csrf import CSRFProtect
import traceback
from flask import jsonify, request

load_dotenv()   
app = Flask(__name__)
app.secret_key = "secret_key_segura"
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY","dev-only-change-me")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
if app.config.get("ENV") == "production":
    app.config["SESSION_COOKIE_SECURE"] = False
logging.basicConfig(filename="app.log", level=logging.INFO)
secret = os.environ.get("SECRET_KEY")
if not secret or len(secret) < 32:
    raise RuntimeError("❌ SECRET_KEY no está configurada o es muy corta.")
app.config["SECRET_KEY"] = secret
csrf = CSRFProtect(app)
app.config["ENV"] = "production"
app.config["DEBUG"] = False
csrf = CSRFProtect(app)
# =====================================================
# LOGIN
# =====================================================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))

        return "Credenciales inválidas", 401

    return render_template("login.html")


# =====================================================
# DASHBOARD
# =====================================================
@app.route("/dashboard")
def dashboard():
    conn = get_db_connection()

    # 1) Tabla principal (lo que usa el dashboard)
    ventas_detalle = conn.execute("""
    SELECT
        fecha_entrega AS fecha,
        nombre_vendedor AS vendedor,
        tipo_de_impresion AS tipo_impresion,
        costo_total AS monto
    FROM producciones
    ORDER BY id DESC
""").fetchall()

    # 2) Lista de vendedores para el filtro
    vendedores = conn.execute("""
        SELECT DISTINCT nombre_vendedor AS vendedor
        FROM producciones
        WHERE nombre_vendedor IS NOT NULL AND TRIM(nombre_vendedor) <> ''
        ORDER BY nombre_vendedor
    """).fetchall()

    conn.close()
    return render_template(
        "dashboard.html",
        ventas_detalle=ventas_detalle,
        vendedores=vendedores
    )


# producciones 
@app.route("/producciones/")
def produccion(): 
    if "user_id" not in session: 
        return redirect(url_for("login"))
    conn = get_db_connection()
    ventas = conn.execute("SELECT * FROM ventas ORDER BY id DESC").fetchall()
    vendedores = conn.execute("SELECT id, nombre FROM vendedores ORDER BY nombre").fetchall()
    clientes   = conn.execute("SELECT id, nombre FROM clientes ORDER BY nombre").fetchall()
    q = request.args.get("q", "").strip()

    if q:
        ventas = conn.execute("""
            SELECT * FROM ventas
            WHERE cliente LIKE ?
               OR vendedor LIKE ?
               OR cotizacion LIKE ?
            ORDER BY id DESC
        """, (f"%{q}%", f"%{q}%", f"%{q}%")).fetchall()
    else:
        ventas = conn.execute(
            "SELECT * FROM ventas ORDER BY id DESC"
        ).fetchall()


    conn.close()


    return render_template("producciones.html",ventas=ventas,vendedores=vendedores,clientes=clientes)

@app.route("/ventas/monitoreo")
def ventas_monitoreo():
    if "user_id" not in session :
        return redirect(url_for("login"))
    conn = get_db_connection()

    rows = conn.execute("""
        SELECT
          v.id,
          v.cliente,
          v.vendedor,
          v.fecha,
          (SELECT COUNT(*) FROM produccion_lineas pl
            WHERE pl.venta_id = v.id AND pl.estado = 'listo') AS lineas_listas,
          (SELECT COUNT(*) FROM produccion_lineas pl
            WHERE pl.venta_id = v.id) AS total_lineas
        FROM ventas v
        ORDER BY v.id DESC
    """).fetchall()

    conn.close()
    return render_template("monitoreo.html", ventas=rows) 
@app.route("/ventas/<int:venta_id>/produccion")
def ventas_produccion(venta_id):
    if "user_id" not in session: 
        return redirect(url_for("login"))
    
    conn = get_db_connection()
    venta = conn.execute("SELECT * FROM ventas WHERE id =? ",(venta_id,)).fetchone()
    if not venta: 
        conn.close()
        flash("Venta no encontrada","danger")
        return redirect(url_for("ventas_monitoreo"))
    #catalogo de estaciones 
    estaciones = conn.execute(""" SELECT * FROM estaciones ORDER BY orden ASC """).fetchall()
    #lineas de produccion 
    lineas = conn.execute("""
        SELECT pl.*, e.nombre AS estacion_nombre
        FROM produccion_lineas pl
        JOIN estaciones e ON e.id = pl.estacion_id
        WHERE pl.venta_id = ?
        ORDER BY pl.orden ASC, pl.id ASC
    """, (venta_id,)).fetchall()

    conn.close()
    return render_template(
        "ventas_produccion.html",
        venta=venta,
        estaciones=estaciones,
        lineas=lineas
    )

@app.route("/ventas/<int:venta_id>/produccion/agregar_estacion", methods=["POST"])
def agregar_estacion_a_venta(venta_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    estacion_id = request.form.get("estacion_id")
    if not estacion_id:
        flash("Selecciona una estación", "danger")
        return redirect(url_for("ventas_produccion", venta_id=venta_id))

    conn = get_db_connection()

    # siguiente orden dentro de esa venta
    row = conn.execute("""
        SELECT COALESCE(MAX(orden), 0) AS max_orden
        FROM produccion_lineas
        WHERE venta_id = ?
    """, (venta_id,)).fetchone()

    next_orden = (row["max_orden"] if row and row["max_orden"] is not None else 0) + 1

    conn.execute("""
        INSERT INTO produccion_lineas (venta_id, estacion_id, orden, estado)
        VALUES (?, ?, ?, 'pendiente')
    """, (venta_id, int(estacion_id), next_orden))

    conn.commit()
    conn.close()

    return redirect(url_for("ventas_produccion", venta_id=venta_id))


@app.route("/ventas/<int:venta_id>/produccion/linea/<int:linea_id>/estado", methods=["POST"])
def actualizar_estado_linea(venta_id, linea_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    nuevo_estado = request.form.get("estado")
    if nuevo_estado not in ("pendiente", "en_proceso", "listo"):
        flash("Estado inválido", "danger")
        return redirect(url_for("ventas_produccion", venta_id=venta_id))

    conn = get_db_connection()
    conn.execute("""
        UPDATE produccion_lineas
        SET estado = ?
        WHERE id = ? AND venta_id = ?
    """, (nuevo_estado, linea_id, venta_id))
    conn.commit()

    # opcional: actualizar estado general de la venta
    total = conn.execute("SELECT COUNT(*) AS c FROM produccion_lineas WHERE venta_id = ?", (venta_id,)).fetchone()["c"]
    listas = conn.execute("SELECT COUNT(*) AS c FROM produccion_lineas WHERE venta_id = ? AND estado='listo'", (venta_id,)).fetchone()["c"]
    en_proceso = conn.execute("SELECT COUNT(*) AS c FROM produccion_lineas WHERE venta_id = ? AND estado='en_proceso'", (venta_id,)).fetchone()["c"]

    if total == 0:
        estado_general = "aprobada"
    elif listas == total:
        estado_general = "finalizada"
    elif en_proceso > 0:
        estado_general = "en_proceso"
    else:
        estado_general = "aprobada"

    conn.execute("UPDATE ventas SET estado = ? WHERE id = ?", (estado_general, venta_id))
    conn.commit()

    conn.close()

    return redirect(url_for("ventas_produccion", venta_id=venta_id))


@app.route("/ventas/<int:venta_id>/produccion/linea/<int:linea_id>/eliminar", methods=["POST"])
def eliminar_linea_produccion(venta_id, linea_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    conn.execute("DELETE FROM produccion_lineas WHERE id = ? AND venta_id = ?", (linea_id, venta_id))
    conn.commit()
    conn.close()

    return redirect(url_for("ventas_produccion", venta_id=venta_id))


@app.route("/ventasnuevas", methods = ["GET","POST"])
def ventas_nuevas(): 
    if "user_id" not in session: 
        return redirect(url_for("login"))
    if request.method == "POST": 
        conn = get_db_connection()
        conn.execute(""" INSERT INTO ventas(fecha,vendedor,cliente,cotizacion,mont) VALUES(?,?,?,?,?)""",(
            request.form["fecha"],
            request.form["vendedor"],
            request.form["clientes"],
            request.form["cotizacion"],
            request.form["mont"]
        ))
        conn.commit()
        conn.close()
        return redirect(url_for("produccion"))

    vendedores= conn.execute("SELECT id, nombre FROM vendedores").fetchall()
    clientes = conn.execute("SELECT id,nombre FROM clientes").fetchall()
    return render_template("ventas_nuevas.html",vendedores=vendedores,clientes=clientes)
@app.route("/producciones/<int:ventas_id>/eliminar", methods= ["POST"])
def eliminar_venta(ventas_id):
    if "user_id" not in session: 
        return redirect(url_for("login"))
    
    conn= get_db_connection()
    try: 
        cur = conn.execute("DELETE FROM ventas WHERE id =? ",(ventas_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print("❌ ERROR ELIMINANDO:", repr(e))  # DEBUG
        flash(f"❌ Error eliminando: {e}", "danger")

    finally:
        conn.close()

    return redirect(url_for("produccion"))
# =====================================================
# COSTOS
# =====================================================
@app.route("/costos")
def costos(): 
    if "user_id" not in session:
        return redirect(url_for("login"))
    conn = get_db_connection()
    costos = conn.execute("SELECT * FROM costos ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("costos.html", costos=costos)


@app.route("/costos/agregar", methods=["GET", "POST"])
def agregar_costo():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if request.method == "POST":
        material = request.form["material"]
        proveedores = request.form["proveedor"]
        factura = request.form["factura"]
        monto = request.form["monto"]
        fecha = request.form["fecha"]
        conn = get_db_connection()
        conn.execute("INSERT INTO costos (material, proveedor, factura, monto, fecha) VALUES (?, ?, ?, ?, ?)",
                     (material, proveedores, factura, monto, fecha))
        conn.commit()
        conn.close()
        return redirect(url_for("costos"))
    return render_template("nuevo_costo.html")


@app.route("/costos/nuevo", methods=["GET", "POST"])
def nuevo_costo():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    # datos para los selects (SIEMPRE)
    materiales = conn.execute("SELECT * FROM materiales WHERE activo = 1").fetchall()
    vendedores = conn.execute("SELECT * FROM vendedores WHERE activo = 1").fetchall()
    clientes   = conn.execute("SELECT * FROM clientes WHERE activo = 1").fetchall()
  
    accion = request.form.get("accion")
    resumen = None

    # historial de tabla (para GET y POST)
    costos_calculados = session.get("costos_calculados", [])
    editando = session.get("editando_costeo")

    if request.method == "POST" and accion == "calcular":

        # ================= DATOS DEL FORM =================
        tipo_nombre = request.form["tipo_impresion"]  # "Offset" o "Digital"
        material_id = int(request.form["material"])
        artes = int(request.form.get("artes", 0) or 0)
        vendedor_id = int(request.form["vendedor"])
        cliente_id = int(request.form["cliente"])
        ancho_arte = float(request.form.get("ancho_arte", 0) or 0)
        alto_arte  = float(request.form.get("alto_arte", 0) or 0)
        imp_total  = int(request.form.get("imp_total", 0) or 0)
        troquel    = float(request.form.get("troquel", 0) or 0)
        barniz     = request.form.get("barniz") == "si"
        material = conn.execute("SELECT * FROM materiales WHERE id = ?", (material_id,)).fetchone()


        
   
        # ================= MATERIAL SELECCIONADO =================
    

        if not material:
            conn.close()
            return render_template(
                "costeo.html",
                resultado=None,
                materiales=materiales,
                vendedores=vendedores,
                clientes=clientes,
                costos_calculados=costos_calculados
            )

        costo_resmas = float(material["costo_resma"])
        ancho_resmas = float(material["ancho_pl"])
        alto_resmas  = float(material["altos_pl"])
        pliegos_por_resmas = float(material["pliegos_por_resma"])

        # ================= IMPOSICIÓN =================
        entran_h1 = math.floor(ancho_resmas / ancho_arte) 
        entran_v1 = math.floor(alto_resmas / alto_arte) 
        entran_h2 = math.floor(ancho_resmas / alto_arte) 
        entran_v2 = math.floor(alto_resmas / ancho_arte) 

        alcanzan_medio_pliego = max(
            entran_h1 * entran_v1,
            entran_h2 * entran_v2
        )

       

        # ================= COSTOS =================
        cantidad_resmas = (imp_total / (alcanzan_medio_pliego*2)) / pliegos_por_resmas +1 
        

        costo_total_material = cantidad_resmas * costo_resmas

        costo_barniz = (((190 / 11000) / alcanzan_medio_pliego) * imp_total) if barniz else 0
        costo_tinta  = ((70 / 11000) / alcanzan_medio_pliego) * imp_total

        costo_plancha = 28
        cantidad_plancha = math.ceil(artes / alcanzan_medio_pliego) if artes > 0 else 0
        costo_total_plancha = cantidad_plancha * costo_plancha

        costo_total_produccion = (
            costo_total_material +
            costo_barniz +
            costo_tinta +
            costo_total_plancha +
            troquel
        ) / 0.95

        # ================= NOMBRES =================
        cliente_nombre = conn.execute(
            "SELECT nombre FROM clientes WHERE id = ?",
            (cliente_id,)
        ).fetchone()["nombre"]

        vendedor_nombre = conn.execute(
            "SELECT nombre FROM vendedores WHERE id = ?",
            (vendedor_id,)
        ).fetchone()["nombre"]

        # ================= RESUMEN =================
        resumen = {
            "tipo_de_impresion": tipo_nombre,
            "material_nombre": material["nombre"],
            "cantidad": imp_total,
            "artes": artes,
            "resmas": cantidad_resmas,
            "costo_material": round(costo_total_material, 2),
            "costo_barniz": round(costo_barniz, 2),
            "costo_tinta": round(costo_tinta, 2),
            "costo_plancha": round(costo_total_plancha, 2),
            "costo_total": round(costo_total_produccion, 2),
            "vendedor_nombre": vendedor_nombre,
            "cliente_nombre": cliente_nombre,
        }

        session["resultado_costeo"] = resumen

        # ================= TABLA =================
        fila = {
    "id": int(time.time()*1000),

    # ids para poder preseleccionar en selects
    "tipo_de_impresion": tipo_nombre,
    "material_id": material_id,
    "vendedor_id": vendedor_id,
    "cliente_id": cliente_id,

    # valores para rellenar inputs
    "ancho_arte": ancho_arte,
    "alto_arte": alto_arte,
    "artes": artes,
    "cantidad": imp_total,
    "troquel": troquel,
    "barniz": "Si" if barniz else "No",

    # texto para tabla
    "cliente": cliente_nombre,
    "vendedor": vendedor_nombre,
    "material": material["nombre"],


    "resmas": cantidad_resmas,
    "costo_total": round(costo_total_produccion, 2),
}


        costos_calculados.insert(0, fila)
        
        session["costos_calculados"] = costos_calculados
        

    conn.close()

    return render_template(
        "costeo.html",
        resultado=resumen,
        materiales=materiales,
        vendedores=vendedores,
        clientes=clientes,
        costos_calculados=costos_calculados,
        editando=editando
    )


@app.route("/costeo/eliminar/<int:item_id>", methods=["POST"])
def eliminar_costeo(item_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    costos_calculados = session.get("costos_calculados", [])
    costos_calculados = [c for c in costos_calculados if c.get("id") != item_id]
    session["costos_calculados"] = costos_calculados

    # si estabas editando ese mismo, limpiarlo
    edit = session.get("editando_costeo")
    if edit and edit.get("id") == item_id:
        session.pop("editando_costeo", None)

    return redirect(url_for("nuevo_costo"))


@app.route("/costeo/editar/<int:item_id>", methods=["POST"])
def editar_costeo(item_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    costos_calculados = session.get("costos_calculados", [])
    item = next((c for c in costos_calculados if c.get("id") == item_id), None)
    session["editando_costeo"] = item

       
    return redirect(url_for("nuevo_costo"))
import sqlite3, time
from flask import request, redirect, session, flash
from datetime import datetime

@app.route("/costeo/guardar", methods=["POST"])
def guardar_costeo():
    conn = get_db_connection()
    costos_calculados = session.get("costos_calculados", [])
    for c in costos_calculados:
            conn.execute("""
    INSERT INTO costeo (
        nombre_vendedor, material, resmas, tipo_de_impresion,
        artes, cantidad, costo_total
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
""", (
    c["vendedor"],
    c["material"],
    c["resmas"],
    c["tipo_de_impresion"],
    c["artes"],
    c["cantidad"],
    c["costo_total"],
))
    conn.commit()
    conn.close()
    session.pop("costos_calculados", None)
    session.pop("editando_costeo", None)

    flash("✅ Costos guardados como cotizaciones.", "success")
    return redirect(url_for("cotizaciones"))
@app.route("/cotizaciones")
def cotizaciones():
    conn = get_db_connection()
    conn.execute("SELECT id, status FROM costeo ORDER BY id DESC LIMIT 5").fetchall()
    

    # Filtros (opcionales)
    q = (request.args.get("q") or "").strip()          # buscar texto
    status = (request.args.get("status") or "").strip()

    sql = "SELECT * FROM costeo WHERE 1=1"
    params = []

    if status:
        sql += " AND status = ?"
        params.append(status)

    if q:
        sql += " AND (cliente LIKE ? OR nombre_vendedor LIKE ? OR material LIKE ? OR tipo_de_impresion LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like, like])

    sql += " ORDER BY id DESC"

    cotizaciones = conn.execute(sql, params).fetchall()
    conn.close()

    return render_template("cotizaciones.html", cotizaciones=cotizaciones, q=q, status=status)
from flask import request, redirect, flash
from datetime import datetime

@app.route("/cotizacion/<int:cotizacion_id>/aprobar", methods=["POST"])
def aprobar_cotizacion(cotizacion_id):
    fecha_entrega = request.form.get("fecha_entrega")
    print(fecha_entrega)
    if not fecha_entrega:
        flash("Debes seleccionar una fecha de entrega.", "warning")
        return redirect("/cotizaciones")

    conn = get_db_connection()
    
    try:
        conn.execute("BEGIN IMMEDIATE")
        
        # 1) Leer cotización
        cot = conn.execute("SELECT * FROM costeo WHERE id = ?", (cotizacion_id,)).fetchone()
        if not cot:
            conn.rollback()
            flash("Cotización no encontrada.", "danger")
            return redirect("/cotizaciones")

        # 2) Marcar como Aprobada
        conn.execute("UPDATE costeo SET status = ? WHERE id = ?", ("Aprobada", cotizacion_id))

        # Datos que quieres copiar a producciones (foto)
        vendedor = (cot["nombre_vendedor"] or "").strip()
        tipo_imp = (cot["tipo_de_impresion"] or "").strip()
        monto = (cot["costo_total"] or 0)

        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 3) Insert/Update en producciones
        existe = conn.execute(
            "SELECT id FROM producciones WHERE cotizacion_id = ?",
            (cotizacion_id,)
        ).fetchone()

        if existe:
            conn.execute("""
                UPDATE producciones
                    nombre_vendedor = ?,
                    tipo_de_impresion = ?,  
                    costo_total = ?,
                    fecha_entrega = ?,
                    WHERE id = ?
            """, (vendedor, tipo_imp, monto, fecha_entrega, cotizacion_id))
        else:
            conn.execute("""    
                INSERT INTO producciones (
                    cotizacion_id,
                    nombre_vendedor, tipo_de_impresion,costo_total,fecha_entrega
                ) VALUES (?, ?, ?, ?,?)
            """, (cotizacion_id,vendedor, tipo_imp,monto,fecha_entrega))

        conn.commit()
        flash("✅ Aprobada y enviada a Producciones.", "success")
        return redirect("/dashboard")

    except Exception as e:
        conn.rollback()
        print("❌ ERROR APROBANDO:", repr(e))   # <--- agrega esto
        flash(f"❌ Error aprobando: {e}", "danger")
        return redirect("/cotizaciones")
    finally:
        conn.close()



@app.route("/cotizacion/<int:cot_id>/eliminar", methods=["POST"])
def eliminar_cotizacion(cot_id):
    conn = get_db_connection()
    try:
       

        cur = conn.execute("DELETE FROM costeo WHERE id = ?", (cot_id,))
        conn.commit()

        

        if cur.rowcount == 0:
            flash("⚠️ No se encontró la cotización para eliminar.", "warning")
        else:
            flash("🗑️ Cotización eliminada.", "success")

    except Exception as e:
        conn.rollback()
        flash(f"❌ Error eliminando: {e}", "danger")

    finally:
        conn.close()

    return redirect("/cotizaciones")


# =====================================================
# LOGOUT
# =====================================================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

from werkzeug.exceptions import HTTPException

@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, HTTPException):
        return e  # deja que Flask maneje 404, 403, etc.
    print("🔥 ERROR EN:", request.path)
    traceback.print_exc()
    return "Error interno (mira logs).", 500
@app.get("/__rutas")
def __rutas():
    return "<br>".join(sorted([str(r) for r in app.url_map.iter_rules()]))


if __name__ == "__main__":
    app.run(debug=True)
