from flask import Flask, render_template, request, redirect, session, url_for
from database.conexion import conectar
from urllib.parse import quote
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "clave_secreta_super_segura_para_servicios_casa"

MESES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
}

# Crear tablas necesarias y usuario por defecto si no existen
def inicializar_db():
    try:
        con = conectar()
        cursor = con.cursor()
        
        # Administradores
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS administradores (
                id INT AUTO_INCREMENT PRIMARY KEY,
                usuario VARCHAR(50) NOT NULL UNIQUE,
                password VARCHAR(255) NOT NULL
            )
        """)
        con.commit()
        
        # Asegurar usuarios marlen y demo existan
        cursor.execute("SELECT id FROM administradores WHERE usuario = 'marlen'")
        marlen_row = cursor.fetchone()
        if not marlen_row:
            hashed_pw = generate_password_hash("casa123")
            cursor.execute("INSERT INTO administradores (usuario, password) VALUES ('marlen', %s)", (hashed_pw,))
            con.commit()
            cursor.execute("SELECT id FROM administradores WHERE usuario = 'marlen'")
            marlen_row = cursor.fetchone()
        
        marlen_id = marlen_row['id'] if marlen_row else 1

        cursor.execute("SELECT id FROM administradores WHERE usuario = 'demo'")
        if not cursor.fetchone():
            hashed_pw_demo = generate_password_hash("demo123")
            cursor.execute("INSERT INTO administradores (usuario, password) VALUES ('demo', %s)", (hashed_pw_demo,))
            con.commit()

        # Asegurar usuarios casaabuela y servicioabuela
        for u_abuela in ['casaabuela', 'servicioabuela']:
            cursor.execute("SELECT id FROM administradores WHERE usuario = %s", (u_abuela,))
            row_abuela = cursor.fetchone()
            hashed_pw_abuela = generate_password_hash("casa123456")
            if not row_abuela:
                cursor.execute("INSERT INTO administradores (usuario, password) VALUES (%s, %s)", (u_abuela, hashed_pw_abuela))
                con.commit()
            else:
                cursor.execute("UPDATE administradores SET password = %s WHERE usuario = %s", (hashed_pw_abuela, u_abuela))
                con.commit()

        # Recibos Agua
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recibos_agua (
                id INT AUTO_INCREMENT PRIMARY KEY,
                fecha DATE NOT NULL,
                consumo_total INT NOT NULL,
                valor_total DECIMAL(12,2) NOT NULL,
                valor_m3 DECIMAL(12,2) NOT NULL,
                observaciones TEXT NULL,
                administrador_id INT NOT NULL
            )
        """)
        con.commit()
        
        # Lecturas Agua
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lecturas_agua (
                id INT AUTO_INCREMENT PRIMARY KEY,
                apartamento_id INT NOT NULL,
                fecha DATE NOT NULL,
                lectura_anterior INT NOT NULL DEFAULT 0,
                lectura_actual INT NOT NULL,
                consumo_mes INT NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.commit()
        
        # Cobros Agua
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cobros_agua (
                id INT AUTO_INCREMENT PRIMARY KEY,
                apartamento_id INT NOT NULL,
                recibo_id INT NOT NULL,
                consumo INT NOT NULL,
                valor_agua DECIMAL(12,2) NOT NULL,
                total DECIMAL(12,2) NOT NULL,
                fecha_generacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.commit()

        # Recibos Cabeza (Casa Abuela)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recibos_cabeza (
                id INT AUTO_INCREMENT PRIMARY KEY,
                fecha DATE NOT NULL,
                concepto VARCHAR(100) DEFAULT 'Servicios del mes',
                tipo_recibo VARCHAR(50) DEFAULT 'Todos',
                valor_luz DECIMAL(12,2) DEFAULT 0,
                valor_agua DECIMAL(12,2) DEFAULT 0,
                valor_gas DECIMAL(12,2) DEFAULT 0,
                valor_total DECIMAL(12,2) NOT NULL,
                total_personas INT NOT NULL,
                valor_por_cabeza DECIMAL(12,2) NOT NULL,
                observaciones TEXT NULL,
                administrador_id INT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.commit()

        # Cobros Cabeza (Casa Abuela)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cobros_cabeza (
                id INT AUTO_INCREMENT PRIMARY KEY,
                recibo_id INT NOT NULL,
                apartamento_id INT NOT NULL,
                personas INT NOT NULL,
                valor_luz DECIMAL(12,2) DEFAULT 0,
                valor_agua DECIMAL(12,2) DEFAULT 0,
                valor_gas DECIMAL(12,2) DEFAULT 0,
                total DECIMAL(12,2) NOT NULL,
                estado VARCHAR(20) DEFAULT 'Pendiente',
                fecha_generacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.commit()

        # Migración de columnas piso y personas en apartamentos
        cursor.execute("SHOW TABLES LIKE 'apartamentos'")
        if cursor.fetchone():
            cursor.execute("DESCRIBE apartamentos")
            columnas_apto = [col['Field'] for col in cursor.fetchall()]
            if 'personas' not in columnas_apto:
                cursor.execute("ALTER TABLE apartamentos ADD COLUMN personas INT NOT NULL DEFAULT 1")
                con.commit()
            if 'piso' not in columnas_apto:
                cursor.execute("ALTER TABLE apartamentos ADD COLUMN piso VARCHAR(50) NULL DEFAULT ''")
                con.commit()

        # Precargar los 10 inquilinos por piso para casaabuela y servicioabuela
        inquilinos_abuela = [
            {"numero": "Sótano", "nombre": "Kati navarro", "piso": "Sótano", "personas": 2, "telefono": "3005583361"},
            {"numero": "101", "nombre": "Juan", "piso": "Primer Piso", "personas": 2, "telefono": "3144147191"},
            {"numero": "102", "nombre": "Elisaul", "piso": "Primer Piso", "personas": 2, "telefono": "3217762472"},
            {"numero": "201", "nombre": "Esaul", "piso": "Segundo Piso", "personas": 3, "telefono": "3214941341"},
            {"numero": "202", "nombre": "Osiris", "piso": "Segundo Piso", "personas": 2, "telefono": "3218137405"},
            {"numero": "203", "nombre": "Rosa", "piso": "Segundo Piso", "personas": 1, "telefono": "3204273349"},
            {"numero": "301", "nombre": "Catalino", "piso": "Tercer Piso", "personas": 2, "telefono": "3229823410"},
            {"numero": "302", "nombre": "Eider", "piso": "Tercer Piso", "personas": 2, "telefono": "3185153298"},
            {"numero": "303", "nombre": "Luis sierra", "piso": "Tercer Piso", "personas": 1, "telefono": "3104703454"},
            {"numero": "401", "nombre": "Aldemas medina", "piso": "Cuarto Piso", "personas": 1, "telefono": "3209480710"},
        ]

        for u_name in ['casaabuela', 'servicioabuela']:
            cursor.execute("SELECT id FROM administradores WHERE usuario = %s", (u_name,))
            admin_row = cursor.fetchone()
            if admin_row:
                aid = admin_row["id"]
                cursor.execute("SELECT COUNT(*) as cnt FROM apartamentos WHERE administrador_id = %s", (aid,))
                cnt_row = cursor.fetchone()
                if cnt_row and cnt_row["cnt"] == 0:
                    for inq in inquilinos_abuela:
                        cursor.execute("""
                            INSERT INTO apartamentos (numero, nombre_inquilino, telefono, personas, piso, administrador_id)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (inq["numero"], inq["nombre"], inq["telefono"], inq["personas"], inq["piso"], aid))
                    con.commit()
                else:
                    # Asegurar que los apartamentos existentes tengan personas y piso cargados
                    for inq in inquilinos_abuela:
                        cursor.execute("""
                            UPDATE apartamentos 
                            SET personas = %s, piso = %s 
                            WHERE administrador_id = %s AND (nombre_inquilino LIKE %s OR numero = %s)
                        """, (inq["personas"], inq["piso"], aid, f"%{inq['nombre'][:4]}%", inq["numero"]))
                    con.commit()
        
        # Ejecutar migración de administrador_id si alguna tabla vieja no la tiene
        tablas_a_migrar = ['apartamentos', 'recibos_luz', 'recibos_gas', 'recibos_agua', 'taller_luz']
        for tabla in tablas_a_migrar:
            cursor.execute(f"SHOW TABLES LIKE '{tabla}'")
            if cursor.fetchone():
                cursor.execute(f"DESCRIBE {tabla}")
                columnas = [col['Field'] for col in cursor.fetchall()]
                if 'administrador_id' not in columnas:
                    print(f"Migrando tabla {tabla}: agregando administrador_id")
                    cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN administrador_id INT NULL")
                    con.commit()
                    cursor.execute(f"UPDATE {tabla} SET administrador_id = %s WHERE administrador_id IS NULL", (marlen_id,))
                    con.commit()
                    cursor.execute(f"ALTER TABLE {tabla} MODIFY COLUMN administrador_id INT NOT NULL")
                    con.commit()

        # Limpieza de lecturas y cobros duplicados existentes
        def limpiar_duplicados_lecturas(tabla):
            try:
                cursor.execute(f"SHOW TABLES LIKE '{tabla}'")
                if not cursor.fetchone():
                    return
                cursor.execute(f"SELECT id, apartamento_id, fecha, consumo_mes FROM {tabla} ORDER BY apartamento_id, fecha, consumo_mes DESC, id DESC")
                filas = cursor.fetchall()
                vistos = set()
                ids_a_eliminar = []
                for f in filas:
                    clave = (f['apartamento_id'], str(f['fecha']))
                    if clave in vistos:
                        ids_a_eliminar.append(f['id'])
                    else:
                        vistos.add(clave)
                if ids_a_eliminar:
                    print(f"Limpiando {len(ids_a_eliminar)} registros duplicados en {tabla}")
                    for bid in ids_a_eliminar:
                        cursor.execute(f"DELETE FROM {tabla} WHERE id = %s", (bid,))
                    con.commit()
            except Exception as ex:
                print(f"Error limpiando duplicados en {tabla}:", ex)

        def limpiar_duplicados_cobros(tabla):
            try:
                cursor.execute(f"SHOW TABLES LIKE '{tabla}'")
                if not cursor.fetchone():
                    return
                cursor.execute(f"SELECT id, apartamento_id, recibo_id, consumo FROM {tabla} ORDER BY apartamento_id, recibo_id, consumo DESC, id DESC")
                filas = cursor.fetchall()
                vistos = set()
                ids_a_eliminar = []
                for f in filas:
                    clave = (f['apartamento_id'], f['recibo_id'])
                    if clave in vistos:
                        ids_a_eliminar.append(f['id'])
                    else:
                        vistos.add(clave)
                if ids_a_eliminar:
                    print(f"Limpiando {len(ids_a_eliminar)} cobros duplicados en {tabla}")
                    for bid in ids_a_eliminar:
                        cursor.execute(f"DELETE FROM {tabla} WHERE id = %s", (bid,))
                    con.commit()
            except Exception as ex:
                print(f"Error limpiando duplicados en {tabla}:", ex)

        limpiar_duplicados_lecturas('lecturas_luz')
        limpiar_duplicados_lecturas('lecturas_gas')
        limpiar_duplicados_lecturas('lecturas_agua')

        limpiar_duplicados_cobros('cobros_luz')
        limpiar_duplicados_cobros('cobros_gas')
        limpiar_duplicados_cobros('cobros_agua')

        con.close()
    except Exception as e:
        print("Error al inicializar la base de datos:", e)

inicializar_db()

def es_admin():
    return "usuario_admin" in session and "admin_id" in session

def es_casaabuela():
    return session.get("usuario_admin") in ["casaabuela", "servicioabuela"]

@app.route("/")
def inicio():
    if not es_admin():
        return redirect("/login")
    con = conectar()
    cursor = con.cursor()
    
    es_abuela = es_casaabuela()
    if es_abuela:
        cursor.execute("SELECT * FROM apartamentos WHERE administrador_id = %s ORDER BY id", (session["admin_id"],))
        apartamentos = cursor.fetchall()
        cursor.execute("SELECT * FROM recibos_cabeza WHERE administrador_id = %s ORDER BY fecha DESC, id DESC LIMIT 1", (session["admin_id"],))
        ultimo_recibo_abuela = cursor.fetchone()
    else:
        cursor.execute("SELECT * FROM apartamentos WHERE administrador_id = %s ORDER BY numero", (session["admin_id"],))
        apartamentos = cursor.fetchall()
        ultimo_recibo_abuela = None

    con.close()
    return render_template("index.html", apartamentos=apartamentos, es_abuela=es_abuela, ultimo_recibo_abuela=ultimo_recibo_abuela)

@app.route("/recibo", methods=["GET", "POST"])
def recibo():
    if not es_admin():
        return redirect("/login")
    if request.method == "POST":
        fecha = request.form["fecha"]
        energia_facturada = request.form["energia_facturada"]
        valor_kwh = request.form["valor_kwh"]
        valor_energia = request.form["valor_energia"]
        valor_aseo = request.form["valor_aseo"]
        observaciones = request.form["observaciones"]

        con = conectar()
        cursor = con.cursor()
        sql = """INSERT INTO recibos_luz 
                 (fecha, energia_facturada, valor_kwh, valor_energia, valor_aseo, observaciones, administrador_id)
                 VALUES (%s, %s, %s, %s, %s, %s, %s)"""
        cursor.execute(sql, (fecha, energia_facturada, valor_kwh, valor_energia, valor_aseo, observaciones, session["admin_id"]))
        con.commit()
        con.close()
        return render_template("recibo.html", guardado=True)

    return render_template("recibo.html", guardado=False)

@app.route("/lecturas", methods=["GET", "POST"])
def lecturas():
    if not es_admin():
        return redirect("/login")
    con = conectar()
    cursor = con.cursor()

    cursor.execute("SELECT * FROM recibos_luz WHERE administrador_id = %s ORDER BY fecha DESC LIMIT 1", (session["admin_id"],))
    recibo = cursor.fetchone()

    cursor.execute("SELECT * FROM apartamentos WHERE administrador_id = %s ORDER BY numero", (session["admin_id"],))
    apartamentos = cursor.fetchall()

    ultimas = {}
    for a in apartamentos:
        cursor.execute("""
            SELECT lectura_actual FROM lecturas_luz 
            WHERE apartamento_id = %s 
            ORDER BY fecha DESC LIMIT 1
        """, (a["id"],))
        ultima = cursor.fetchone()
        ultimas[a["id"]] = ultima["lectura_actual"] if ultima else 0

    guardado = request.args.get("guardado") == "1"
    if request.method == "POST":
        fecha = request.form.get("fecha_lectura")
        for a in apartamentos:
            lectura_actual = int(request.form[f"lectura_{a['id']}"])

            cursor.execute("""
                SELECT id, lectura_anterior FROM lecturas_luz 
                WHERE apartamento_id = %s AND fecha = %s
            """, (a["id"], fecha))
            existente = cursor.fetchone()

            if existente:
                lectura_anterior = existente["lectura_anterior"]
                consumo = lectura_actual - lectura_anterior
                cursor.execute("""
                    UPDATE lecturas_luz 
                    SET lectura_actual = %s, consumo_mes = %s
                    WHERE id = %s
                """, (lectura_actual, consumo, existente["id"]))
            else:
                lectura_anterior = ultimas[a["id"]]
                consumo = lectura_actual - lectura_anterior
                cursor.execute("""
                    INSERT INTO lecturas_luz 
                    (apartamento_id, lectura_anterior, fecha, lectura_actual, consumo_mes)
                    VALUES (%s, %s, %s, %s, %s)
                """, (a["id"], lectura_anterior, fecha, lectura_actual, consumo))

        con.commit()
        con.close()
        return redirect(url_for("lecturas", guardado=1))

    con.close()
    return render_template("lecturas.html",
                           apartamentos=apartamentos,
                           ultimas=ultimas,
                           recibo=recibo,
                           guardado=guardado)

@app.route("/cobros")
def cobros():
    if not es_admin():
        return redirect("/login")
    con = conectar()
    cursor = con.cursor()

    cursor.execute("SELECT * FROM recibos_luz WHERE administrador_id = %s ORDER BY fecha DESC LIMIT 1", (session["admin_id"],))
    recibo = cursor.fetchone()

    if not recibo:
        con.close()
        return render_template("cobros.html", cobros=[], recibo=None)

    cursor.execute("""
        SELECT l.*, a.numero, a.nombre_inquilino, a.id as apartamento_id
        FROM lecturas_luz l
        JOIN apartamentos a ON l.apartamento_id = a.id
        WHERE l.fecha = %s AND a.administrador_id = %s
        ORDER BY a.numero
    """, (recibo["fecha"], session["admin_id"]))
    lecturas = cursor.fetchall()

    # Deduplicar lecturas por apartamento_id por seguridad
    lecturas_map = {}
    for l in lecturas:
        aid = l["apartamento_id"]
        if aid not in lecturas_map or l["consumo_mes"] > lecturas_map[aid]["consumo_mes"]:
            lecturas_map[aid] = l
    lecturas = list(lecturas_map.values())
    lecturas.sort(key=lambda x: str(x["numero"]))

    valor_aseo_por_apto = round(float(recibo["valor_aseo"]) / 8, 2)
    cobros_lista = []

    for l in lecturas:
        valor_energia = round(l["consumo_mes"] * float(recibo["valor_kwh"]), 2)
        total = round(valor_energia + valor_aseo_por_apto, 2)

        cobros_lista.append({
            "numero": l["numero"],
            "nombre": l["nombre_inquilino"],
            "consumo": l["consumo_mes"],
            "valor_energia": valor_energia,
            "valor_aseo": valor_aseo_por_apto,
            "total": total,
            "apartamento_id": l["apartamento_id"]
        })

        cursor.execute("SELECT id FROM cobros_luz WHERE apartamento_id = %s AND recibo_id = %s", (l["apartamento_id"], recibo["id"]))
        cobro_existente = cursor.fetchone()
        if cobro_existente:
            cursor.execute("""
                UPDATE cobros_luz
                SET consumo = %s, valor_energia = %s, valor_aseo = %s, total = %s
                WHERE id = %s
            """, (l["consumo_mes"], valor_energia, valor_aseo_por_apto, total, cobro_existente["id"]))
        else:
            cursor.execute("""
                INSERT INTO cobros_luz 
                (apartamento_id, recibo_id, consumo, valor_energia, valor_aseo, total)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (l["apartamento_id"], recibo["id"], l["consumo_mes"],
                  valor_energia, valor_aseo_por_apto, total))

    # Limpiar cobros sobrantes en BD para este recibo si no corresponden
    ids_validos = [l["apartamento_id"] for l in lecturas]
    if ids_validos:
        placeholders = ",".join(["%s"] * len(ids_validos))
        cursor.execute(f"DELETE FROM cobros_luz WHERE recibo_id = %s AND apartamento_id NOT IN ({placeholders})", [recibo["id"]] + ids_validos)

    con.commit()
    con.close()

    return render_template("cobros.html", cobros=cobros_lista, recibo=recibo)

@app.route("/whatsapp/<int:apartamento_id>")
def whatsapp(apartamento_id):
    recibo_id = request.args.get("recibo_id")
    con = conectar()
    cursor = con.cursor()

    cursor.execute("SELECT * FROM apartamentos WHERE id = %s", (apartamento_id,))
    apto = cursor.fetchone()

    if recibo_id:
        cursor.execute("""
            SELECT c.*, r.fecha 
            FROM cobros_luz c
            JOIN recibos_luz r ON c.recibo_id = r.id
            WHERE c.apartamento_id = %s AND r.id = %s
        """, (apartamento_id, recibo_id))
    else:
        cursor.execute("""
            SELECT c.*, r.fecha 
            FROM cobros_luz c
            JOIN recibos_luz r ON c.recibo_id = r.id
            WHERE c.apartamento_id = %s
            ORDER BY r.fecha DESC LIMIT 1
        """, (apartamento_id,))
    cobro = cursor.fetchone()
    con.close()

    if not cobro or not apto:
        return "No hay datos", 404

    nombre_mes = "mes"
    if hasattr(cobro["fecha"], "month"):
        nombre_mes = MESES.get(cobro["fecha"].month, "mes")
    elif isinstance(cobro["fecha"], str):
        try:
            from datetime import datetime
            dt = datetime.strptime(cobro["fecha"], "%Y-%m-%d")
            nombre_mes = MESES.get(dt.month, "mes")
        except Exception:
            pass

    mensaje = f"""Hola,

Apartamento {apto['numero']}

Consumo energia: {cobro['consumo']} kWh
Valor energia: ${int(cobro['valor_energia']):,}
Aseo: ${int(cobro['valor_aseo']):,}

Total a pagar: ${int(cobro['total']):,}

Por favor pagar antes del 09 de {nombre_mes}.

Gracias."""

    telefono = apto['telefono']
    print("RAW DB PHONE:", telefono)
    telefono = str(telefono).strip()
    telefono = telefono.replace(" ", "")
    telefono = telefono.replace("-", "")
    telefono = telefono.replace("+", "")
    if telefono.startswith("57"):
        telefono = telefono[2:]
    print("CLEAN PHONE:", telefono)
    if len(telefono) == 10:
        telefono = "57" + telefono
    print("FINAL PHONE:", telefono)
    url_whatsapp = f"https://wa.me/{telefono}?text={quote(mensaje)}"

    return redirect(url_whatsapp)

@app.route("/historial")
def historial():
    if not es_admin():
        return redirect("/login")
    con = conectar()
    cursor = con.cursor()

    cursor.execute("""
        SELECT r.*, 
               SUM(c.total) as total_mes,
               COUNT(c.id) as num_cobros
        FROM recibos_luz r
        LEFT JOIN cobros_luz c ON c.recibo_id = r.id
        WHERE r.administrador_id = %s
        GROUP BY r.id
        ORDER BY r.fecha DESC
    """, (session["admin_id"],))
    recibos = cursor.fetchall()
    con.close()

    return render_template("historial.html", recibos=recibos)

@app.route("/cobros/<int:recibo_id>")
def cobros_mes(recibo_id):
    if not es_admin():
        return redirect("/login")
    con = conectar()
    cursor = con.cursor()

    cursor.execute("SELECT * FROM recibos_luz WHERE id = %s AND administrador_id = %s", (recibo_id, session["admin_id"]))
    recibo = cursor.fetchone()

    if not recibo:
        con.close()
        return "Recibo no encontrado o no tienes permisos", 403

    cursor.execute("""
        SELECT c.*, a.numero, a.nombre_inquilino, a.id as apartamento_id
        FROM cobros_luz c
        JOIN apartamentos a ON c.apartamento_id = a.id
        WHERE c.recibo_id = %s AND a.administrador_id = %s
        ORDER BY a.numero
    """, (recibo_id, session["admin_id"]))
    cobros = cursor.fetchall()

    # Deduplicar por si quedaron duplicados
    cobros_map = {}
    for c in cobros:
        aid = c["apartamento_id"]
        if aid not in cobros_map or c["consumo"] > cobros_map[aid]["consumo"]:
            cobros_map[aid] = c
    cobros = list(cobros_map.values())
    cobros.sort(key=lambda x: str(x["numero"]))

    con.close()

    return render_template("cobros.html", cobros=cobros, recibo=recibo)

@app.route("/editar_lectura/<int:lectura_id>", methods=["GET", "POST"])
def editar_lectura(lectura_id):
    if not es_admin():
        return redirect("/login")
    con = conectar()
    cursor = con.cursor()

    cursor.execute("""
        SELECT l.*, a.numero FROM lecturas_luz l
        JOIN apartamentos a ON l.apartamento_id = a.id
        WHERE l.id = %s
    """, (lectura_id,))
    lectura = cursor.fetchone()

    if request.method == "POST":
        lectura_actual = int(request.form["lectura_actual"])
        lectura_anterior = int(request.form["lectura_anterior"])
        consumo = lectura_actual - lectura_anterior

        cursor.execute("""
            UPDATE lecturas_luz 
            SET lectura_anterior = %s, lectura_actual = %s, consumo_mes = %s
            WHERE id = %s
        """, (lectura_anterior, lectura_actual, consumo, lectura_id))

        # Recalcular cobro si existe
        cursor.execute("""
            SELECT c.id, r.valor_kwh, r.valor_aseo, r.id as recibo_id
            FROM cobros_luz c
            JOIN recibos_luz r ON c.recibo_id = r.id
            WHERE c.apartamento_id = %s
            ORDER BY r.fecha DESC LIMIT 1
        """, (lectura["apartamento_id"],))
        cobro = cursor.fetchone()

        if cobro:
            valor_energia = round(consumo * float(cobro["valor_kwh"]), 2)
            valor_aseo = round(float(cobro["valor_aseo"]) / 8, 2)
            total = round(valor_energia + valor_aseo, 2)

            cursor.execute("""
                UPDATE cobros_luz
                SET consumo = %s, valor_energia = %s, total = %s
                WHERE id = %s
            """, (consumo, valor_energia, total, cobro["id"]))

        con.commit()
        con.close()
        return redirect("/lecturas_ver")

    con.close()
    return render_template("editar_lectura.html", lectura=lectura)

@app.route("/admin/eliminar_lectura/<int:lectura_id>")
def eliminar_lectura(lectura_id):
    if not es_admin():
        return redirect("/login")
    con = conectar()
    cursor = con.cursor()

    cursor.execute("""
        SELECT l.*, a.administrador_id 
        FROM lecturas_luz l
        JOIN apartamentos a ON l.apartamento_id = a.id
        WHERE l.id = %s AND a.administrador_id = %s
    """, (lectura_id, session["admin_id"]))
    lectura = cursor.fetchone()

    if not lectura:
        con.close()
        return "Lectura no encontrada o no tienes permisos", 403

    # Buscar recibo de esa fecha para limpiar cobro asociado
    cursor.execute("SELECT id FROM recibos_luz WHERE fecha = %s AND administrador_id = %s", (lectura["fecha"], session["admin_id"]))
    recibo = cursor.fetchone()
    if recibo:
        cursor.execute("DELETE FROM cobros_luz WHERE apartamento_id = %s AND recibo_id = %s", (lectura["apartamento_id"], recibo["id"]))

    cursor.execute("DELETE FROM lecturas_luz WHERE id = %s", (lectura_id,))
    con.commit()
    con.close()
    return redirect("/lecturas_ver")
@app.route("/lecturas_ver")
def lecturas_ver():
    if not es_admin():
        return redirect("/login")
    con = conectar()
    cursor = con.cursor()

    cursor.execute("""
        SELECT l.*, a.numero, a.nombre_inquilino
        FROM lecturas_luz l
        JOIN apartamentos a ON l.apartamento_id = a.id
        WHERE a.administrador_id = %s
        ORDER BY l.fecha DESC, a.numero
    """, (session["admin_id"],))
    lecturas = cursor.fetchall()
    con.close()

    return render_template("lecturas_ver.html", lecturas=lecturas)

@app.route("/taller")
def taller():
    if not es_admin():
        return redirect("/login")
    con = conectar()
    cursor = con.cursor()

    # Recibo más reciente del administrador actual
    cursor.execute("SELECT * FROM recibos_luz WHERE administrador_id = %s ORDER BY fecha DESC LIMIT 1", (session["admin_id"],))
    recibo = cursor.fetchone()

    if not recibo:
        con.close()
        return render_template("taller.html", recibo=None, taller=None)

    # Sumar consumo total de apartamentos de ese mes de este administrador
    cursor.execute("""
        SELECT SUM(l.consumo_mes) as total_aptos
        FROM lecturas_luz l
        JOIN apartamentos a ON l.apartamento_id = a.id
        WHERE l.fecha = %s AND a.administrador_id = %s
    """, (recibo["fecha"], session["admin_id"]))
    resultado = cursor.fetchone()
    total_aptos = resultado["total_aptos"] or 0

    # Calcular taller
    consumo_taller = int(recibo["energia_facturada"]) - int(total_aptos)
    valor_taller = round(consumo_taller * float(recibo["valor_kwh"]), 2)

    # Verificar si ya existe registro del taller para este recibo
    cursor.execute("SELECT id FROM taller_luz WHERE recibo_id = %s LIMIT 1", (recibo["id"],))
    ya_guardado = cursor.fetchone()

    if not ya_guardado and consumo_taller > 0:
        cursor.execute("""
            INSERT INTO taller_luz 
            (recibo_id, consumo_apartamentos, consumo_recibo, consumo_taller, valor_taller, fecha, administrador_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (recibo["id"], total_aptos, recibo["energia_facturada"], 
              consumo_taller, valor_taller, recibo["fecha"], session["admin_id"]))
        con.commit()

    # Traer historial taller de este administrador
    cursor.execute("""
        SELECT t.*, r.valor_kwh 
        FROM taller_luz t
        JOIN recibos_luz r ON t.recibo_id = r.id
        WHERE t.administrador_id = %s
        ORDER BY t.fecha DESC
    """, (session["admin_id"],))
    historial_taller = cursor.fetchall()
    con.close()

    datos_taller = {
        "consumo_aptos": total_aptos,
        "consumo_recibo": recibo["energia_facturada"],
        "consumo_taller": consumo_taller,
        "valor_taller": valor_taller
    }

    return render_template("taller.html", recibo=recibo, 
                           taller=datos_taller, 
                           historial=historial_taller)
    
@app.route("/estadisticas")
def estadisticas():
    if not es_admin():
        return redirect("/login")
    con = conectar()
    cursor = con.cursor()

    cursor.execute("""
        SELECT a.numero, a.nombre_inquilino,
               AVG(l.consumo_mes) as promedio,
               MAX(l.consumo_mes) as maximo,
               MIN(l.consumo_mes) as minimo
        FROM lecturas_luz l
        JOIN apartamentos a ON l.apartamento_id = a.id
        WHERE a.administrador_id = %s
        GROUP BY a.id, a.numero, a.nombre_inquilino
        ORDER BY a.numero
    """, (session["admin_id"],))
    promedios = cursor.fetchall()

    # Consumo último mes vs anterior
    cursor.execute("""
        SELECT a.numero, a.nombre_inquilino,
               l1.consumo_mes as ultimo,
               l2.consumo_mes as anterior
        FROM apartamentos a
        JOIN lecturas_luz l1 ON l1.apartamento_id = a.id
        JOIN lecturas_luz l2 ON l2.apartamento_id = a.id
        WHERE a.administrador_id = %s
        AND l1.fecha = (SELECT MAX(fecha) FROM lecturas_luz)
        AND l2.fecha = (SELECT MAX(fecha) FROM lecturas_luz 
                        WHERE fecha < (SELECT MAX(fecha) FROM lecturas_luz))
        ORDER BY a.numero
    """, (session["admin_id"],))
    comparacion = cursor.fetchall()
    con.close()

    stats = []
    for p in promedios:
        ultimo = next((c["ultimo"] for c in comparacion if c["numero"] == p["numero"]), None)
        anterior = next((c["anterior"] for c in comparacion if c["numero"] == p["numero"]), None)
        
        if ultimo and anterior:
            diferencia = ultimo - anterior
            if diferencia > 0:
                tendencia = "subio"
            elif diferencia < 0:
                tendencia = "bajo"
            else:
                tendencia = "igual"
        else:
            diferencia = 0
            tendencia = "igual"

        stats.append({
            "numero": p["numero"],
            "nombre": p["nombre_inquilino"],
            "promedio": round(float(p["promedio"]), 1),
            "maximo": p["maximo"],
            "minimo": p["minimo"],
            "ultimo": ultimo,
            "anterior": anterior,
            "diferencia": diferencia,
            "tendencia": tendencia
        })

    return render_template("estadisticas.html", stats=stats)

@app.route("/recibo_gas", methods=["GET", "POST"])
def recibo_gas():
    if not es_admin():
        return redirect("/login")
    if request.method == "POST":
        fecha = request.form["fecha"]
        grupo = request.form["grupo"]
        referencia = request.form["referencia"]
        consumo_total = request.form["consumo_total"]
        valor_total = request.form["valor_total"]
        valor_m3 = request.form["valor_m3"]
        observaciones = request.form.get("observaciones", "")

        con = conectar()
        cursor = con.cursor()
        cursor.execute("""
            INSERT INTO recibos_gas 
            (fecha, grupo, referencia, consumo_total, valor_total, valor_m3, observaciones, administrador_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (fecha, grupo, referencia, consumo_total, valor_total, valor_m3, observaciones, session["admin_id"]))
        con.commit()
        con.close()
        return render_template("recibo_gas.html", guardado=True)

    return render_template("recibo_gas.html", guardado=False)


@app.route("/whatsapp_gas/<int:apartamento_id>")
def whatsapp_gas(apartamento_id):
    recibo_id = request.args.get("recibo_id")
    con = conectar()
    cursor = con.cursor()

    cursor.execute("SELECT * FROM apartamentos WHERE id = %s", (apartamento_id,))
    apto = cursor.fetchone()

    if recibo_id:
        cursor.execute("""
            SELECT c.*, r.fecha 
            FROM cobros_gas c
            JOIN recibos_gas r ON c.recibo_id = r.id
            WHERE c.apartamento_id = %s AND r.id = %s
        """, (apartamento_id, recibo_id))
    else:
        cursor.execute("""
            SELECT c.*, r.fecha 
            FROM cobros_gas c
            JOIN recibos_gas r ON c.recibo_id = r.id
            WHERE c.apartamento_id = %s
            ORDER BY r.fecha DESC LIMIT 1
        """, (apartamento_id,))
    cobro = cursor.fetchone()
    con.close()

    if not cobro or not apto:
        return "No hay datos", 404

    nombre_mes = "mes"
    if hasattr(cobro["fecha"], "month"):
        nombre_mes = MESES.get(cobro["fecha"].month, "mes")
    elif isinstance(cobro["fecha"], str):
        try:
            from datetime import datetime
            dt = datetime.strptime(cobro["fecha"], "%Y-%m-%d")
            nombre_mes = MESES.get(dt.month, "mes")
        except Exception:
            pass

    mensaje = f"""Hola,

Apartamento {apto['numero']}

Gas consumido: {cobro['consumo']} m3
Total a pagar: ${int(cobro['total']):,}

Por favor pagar antes del 03 de {nombre_mes}.

Gracias."""

    telefono = apto['telefono']
    print("RAW DB PHONE:", telefono)
    telefono = str(telefono).strip()
    telefono = telefono.replace(" ", "")
    telefono = telefono.replace("-", "")
    telefono = telefono.replace("+", "")
    if telefono.startswith("57"):
        telefono = telefono[2:]
    print("CLEAN PHONE:", telefono)
    if len(telefono) == 10:
        telefono = "57" + telefono
    print("FINAL PHONE:", telefono)
    url_whatsapp = f"https://wa.me/{telefono}?text={quote(mensaje)}"
    return redirect(url_whatsapp)

@app.route("/cobros_gas")
def cobros_gas():
    if not es_admin():
        return redirect("/login")
    con = conectar()
    cursor = con.cursor()

    grupo_actual = int(request.args.get("grupo", 1))

    cursor.execute("SELECT * FROM recibos_gas WHERE grupo = %s AND administrador_id = %s ORDER BY fecha DESC LIMIT 1", (grupo_actual, session["admin_id"]))
    recibo = cursor.fetchone()

    if not recibo:
        con.close()
        return render_template("cobros_gas.html", cobros=[], recibo=None, grupo_actual=grupo_actual)

    if grupo_actual == 1:
        numeros = ("101", "401", "402", "501")
    else:
        numeros = ("201", "202", "301", "302")

    placeholders = ",".join(["%s"] * len(numeros))
    cursor.execute(f"""
        SELECT l.*, a.numero, a.nombre_inquilino, a.id as apartamento_id
        FROM lecturas_gas l
        JOIN apartamentos a ON l.apartamento_id = a.id
        WHERE l.fecha = %s AND a.numero IN ({placeholders}) AND a.administrador_id = %s
        ORDER BY a.numero
    """, [recibo["fecha"]] + list(numeros) + [session["admin_id"]])
    lecturas = cursor.fetchall()
    print("RECIBO ID:", recibo["id"])
    print("LECTURAS ENCONTRADAS:", len(lecturas))

    # Deduplicar lecturas por apartamento_id por seguridad
    lecturas_map = {}
    for l in lecturas:
        aid = l["apartamento_id"]
        if aid not in lecturas_map or l["consumo_mes"] > lecturas_map[aid]["consumo_mes"]:
            lecturas_map[aid] = l
    lecturas = list(lecturas_map.values())
    lecturas.sort(key=lambda x: str(x["numero"]))

    # Paso 1: Calcular cobro base por consumo
    cobros_lista = []
    consumo_total_aptos = 0
    suma_base = 0
    for l in lecturas:
        valor_gas = round(l["consumo_mes"] * float(recibo["valor_m3"]), 2)
        consumo_total_aptos += l["consumo_mes"]
        suma_base += valor_gas
        cobros_lista.append({
                "numero": l["numero"],
                "nombre": l["nombre_inquilino"],
                "consumo": l["consumo_mes"],
                "valor_gas_base": valor_gas,
                "valor_gas": valor_gas,
                "ajuste": 0,
                "apartamento_id": l["apartamento_id"]
            })

    # Paso 2: Calcular diferencia y repartir proporcionalmente
    valor_total_recibo = float(recibo["valor_total"])
    diferencia = round(valor_total_recibo - suma_base, 2)

    if consumo_total_aptos > 0 and diferencia != 0:
        for c in cobros_lista:
            proporcion = c["consumo"] / consumo_total_aptos
            ajuste = round(diferencia * proporcion, 2)
            c["ajuste"] = ajuste
            c["valor_gas"] = round(c["valor_gas_base"] + ajuste, 2)

    # Guardar cobros en BD con upsert
    if lecturas:
        for c in cobros_lista:
            cursor.execute("SELECT id FROM cobros_gas WHERE apartamento_id = %s AND recibo_id = %s", (c["apartamento_id"], recibo["id"]))
            cobro_existente = cursor.fetchone()
            if cobro_existente:
                cursor.execute("""
                    UPDATE cobros_gas
                    SET consumo = %s, valor_gas = %s, total = %s
                    WHERE id = %s
                """, (c["consumo"], c["valor_gas"], c["valor_gas"], cobro_existente["id"]))
            else:
                cursor.execute("""
                    INSERT INTO cobros_gas
                    (apartamento_id, recibo_id, consumo, valor_gas, total)
                    VALUES (%s, %s, %s, %s, %s)
                """, (c["apartamento_id"], recibo["id"], c["consumo"],
                      c["valor_gas"], c["valor_gas"]))

        # Limpiar cobros sobrantes para este recibo si no corresponden
        ids_validos = [c["apartamento_id"] for c in cobros_lista]
        if ids_validos:
            placeholders_clean = ",".join(["%s"] * len(ids_validos))
            cursor.execute(f"DELETE FROM cobros_gas WHERE recibo_id = %s AND apartamento_id NOT IN ({placeholders_clean})", [recibo["id"]] + ids_validos)

        con.commit()
        print("COBROS GUARDADOS/ACTUALIZADOS:", len(cobros_lista))

    con.close()

    # Resumen de validación
    suma_final = sum(c["valor_gas"] for c in cobros_lista)
    resumen = {
        "valor_recibo": valor_total_recibo,
        "suma_cobros_base": suma_base,
        "diferencia": diferencia,
        "suma_final": round(suma_final, 2)
    }

    return render_template("cobros_gas.html", cobros=cobros_lista, recibo=recibo,
                           grupo_actual=grupo_actual, resumen=resumen)


@app.route("/lecturas_gas_ver")
def lecturas_gas_ver():
    if not es_admin():
        return redirect("/login")
    con = conectar()
    cursor = con.cursor()
    cursor.execute("""
        SELECT l.*, a.numero, a.nombre_inquilino
        FROM lecturas_gas l
        JOIN apartamentos a ON l.apartamento_id = a.id
        WHERE a.administrador_id = %s
        ORDER BY l.fecha DESC, a.numero
    """, (session["admin_id"],))
    lecturas = cursor.fetchall()
    con.close()
    return render_template("lecturas_gas_ver.html", lecturas=lecturas)

@app.route("/lecturas_gas", methods=["GET", "POST"])
def lecturas_gas():
    if not es_admin():
        return redirect("/login")
    con = conectar()
    cursor = con.cursor()

    grupo_actual = int(request.args.get("grupo", 1))
    if request.method == "POST" and "grupo_sel" in request.form and int(request.form["grupo_sel"]) != grupo_actual:
        grupo_actual = int(request.form["grupo_sel"])
        return redirect(f"/lecturas_gas?grupo={grupo_actual}")

    cursor.execute("SELECT * FROM recibos_gas WHERE grupo = %s AND administrador_id = %s ORDER BY fecha DESC LIMIT 1", (grupo_actual, session["admin_id"]))
    recibo = cursor.fetchone()

    if grupo_actual == 1:
        numeros = ("101", "401", "402", "501")
    else:
        numeros = ("201", "202", "301", "302")
    placeholders = ",".join(["%s"] * len(numeros))
    # query to fetch apartments with correct placeholders
    cursor.execute(f"SELECT * FROM apartamentos WHERE numero IN ({placeholders}) AND administrador_id = %s ORDER BY numero", list(numeros) + [session["admin_id"]])
    apartamentos = cursor.fetchall()

    ultimas = {}
    for a in apartamentos:
        cursor.execute("""
            SELECT lectura_actual FROM lecturas_gas 
            WHERE apartamento_id = %s 
            ORDER BY fecha DESC LIMIT 1
        """, (a["id"],))
        ultima = cursor.fetchone()
        ultimas[a["id"]] = ultima["lectura_actual"] if ultima else 0

    guardado = request.args.get("guardado") == "1"
    if request.method == "POST":
        fecha = request.form.get("fecha_lectura")
        for a in apartamentos:
            lectura_actual = int(request.form[f"lectura_{a['id']}"])

            cursor.execute("""
                SELECT id, lectura_anterior FROM lecturas_gas 
                WHERE apartamento_id = %s AND fecha = %s
            """, (a["id"], fecha))
            existente = cursor.fetchone()

            if existente:
                lectura_anterior = existente["lectura_anterior"]
                consumo = lectura_actual - lectura_anterior
                cursor.execute("""
                    UPDATE lecturas_gas
                    SET lectura_actual = %s, consumo_mes = %s
                    WHERE id = %s
                """, (lectura_actual, consumo, existente["id"]))
            else:
                lectura_anterior = ultimas[a["id"]]
                consumo = lectura_actual - lectura_anterior
                cursor.execute("""
                    INSERT INTO lecturas_gas
                    (apartamento_id, lectura_anterior, fecha, lectura_actual, consumo_mes)
                    VALUES (%s, %s, %s, %s, %s)
                """, (a["id"], lectura_anterior, fecha, lectura_actual, consumo))

        con.commit()
        con.close()
        return redirect(f"/lecturas_gas?grupo={grupo_actual}&guardado=1")

    con.close()
    return render_template("lecturas_gas.html",
                           apartamentos=apartamentos,
                           ultimas=ultimas,
                           recibo=recibo,
                           guardado=guardado,
                           grupo_actual=grupo_actual)

@app.route("/editar_lectura_gas/<int:lectura_id>", methods=["GET", "POST"])
def editar_lectura_gas(lectura_id):
    if not es_admin():
        return redirect("/login")
    con = conectar()
    cursor = con.cursor()

    cursor.execute("""
        SELECT l.*, a.numero FROM lecturas_gas l
        JOIN apartamentos a ON l.apartamento_id = a.id
        WHERE l.id = %s AND a.administrador_id = %s
    """, (lectura_id, session["admin_id"]))
    lectura = cursor.fetchone()

    if not lectura:
        con.close()
        return "Lectura no encontrada o no tienes permisos", 403

    if request.method == "POST":
        lectura_actual = int(request.form["lectura_actual"])
        lectura_anterior = int(request.form["lectura_anterior"])
        consumo = lectura_actual - lectura_anterior

        cursor.execute("""
            UPDATE lecturas_gas 
            SET lectura_anterior = %s, lectura_actual = %s, consumo_mes = %s
            WHERE id = %s
        """, (lectura_anterior, lectura_actual, consumo, lectura_id))

        cursor.execute("""
            SELECT c.id, r.valor_m3
            FROM cobros_gas c
            JOIN recibos_gas r ON c.recibo_id = r.id
            WHERE c.apartamento_id = %s
            ORDER BY r.fecha DESC LIMIT 1
        """, (lectura["apartamento_id"],))
        cobro = cursor.fetchone()

        if cobro:
            valor_gas = round(consumo * float(cobro["valor_m3"]), 2)
            cursor.execute("""
                UPDATE cobros_gas
                SET consumo = %s, valor_gas = %s, total = %s
                WHERE id = %s
            """, (consumo, valor_gas, valor_gas, cobro["id"]))

        con.commit()
        con.close()
        return redirect("/lecturas_gas_ver")

    con.close()
    return render_template("editar_lectura_gas.html", lectura=lectura)

@app.route("/admin/eliminar_lectura_gas/<int:lectura_id>")
def eliminar_lectura_gas(lectura_id):
    if not es_admin():
        return redirect("/login")
    con = conectar()
    cursor = con.cursor()

    cursor.execute("""
        SELECT l.*, a.administrador_id 
        FROM lecturas_gas l
        JOIN apartamentos a ON l.apartamento_id = a.id
        WHERE l.id = %s AND a.administrador_id = %s
    """, (lectura_id, session["admin_id"]))
    lectura = cursor.fetchone()

    if not lectura:
        con.close()
        return "Lectura no encontrada o no tienes permisos", 403

    # Limpiar cobros asociados si existe recibo
    cursor.execute("SELECT id, grupo FROM recibos_gas WHERE fecha = %s AND administrador_id = %s", (lectura["fecha"], session["admin_id"]))
    recibos = cursor.fetchall()
    for r in recibos:
        cursor.execute("DELETE FROM cobros_gas WHERE apartamento_id = %s AND recibo_id = %s", (lectura["apartamento_id"], r["id"]))

    cursor.execute("DELETE FROM lecturas_gas WHERE id = %s", (lectura_id,))
    con.commit()
    con.close()
    return redirect("/lecturas_gas_ver")

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        usuario = request.form["usuario"]
        password = request.form["password"]
        
        con = conectar()
        cursor = con.cursor()
        cursor.execute("SELECT * FROM administradores WHERE usuario = %s", (usuario,))
        admin_rec = cursor.fetchone()
        con.close()
        
        if admin_rec and check_password_hash(admin_rec["password"], password):
            session["usuario_admin"] = usuario
            session["admin_id"] = admin_rec["id"]
            return redirect("/")
        else:
            error = "Usuario o contraseña incorrectos"
            
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.pop("usuario_admin", None)
    session.pop("admin_id", None)
    return redirect("/")

@app.route("/admin/apartamentos", methods=["GET", "POST"])
def admin_apartamentos():
    if not es_admin():
        return redirect("/login")
        
    con = conectar()
    cursor = con.cursor()
    
    if request.method == "POST":
        numero = request.form["numero"]
        nombre = request.form["nombre_inquilino"]
        telefono = request.form["telefono"]
        piso = request.form.get("piso", "")
        personas = int(request.form.get("personas", 1) or 1)
        
        cursor.execute("""
            INSERT INTO apartamentos (numero, nombre_inquilino, telefono, piso, personas, administrador_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (numero, nombre, telefono, piso, personas, session["admin_id"]))
        con.commit()
        
    order_clause = "id" if es_casaabuela() else "numero"
    cursor.execute(f"SELECT * FROM apartamentos WHERE administrador_id = %s ORDER BY {order_clause}", (session["admin_id"],))
    apartamentos = cursor.fetchall()
    con.close()
    
    return render_template("admin_apartamentos.html", apartamentos=apartamentos, es_abuela=es_casaabuela())

@app.route("/admin/editar_apartamento/<int:apto_id>", methods=["GET", "POST"])
def editar_apartamento(apto_id):
    if not es_admin():
        return redirect("/login")
        
    con = conectar()
    cursor = con.cursor()
    
    # Validar propiedad
    cursor.execute("SELECT * FROM apartamentos WHERE id = %s AND administrador_id = %s", (apto_id, session["admin_id"]))
    apto = cursor.fetchone()
    
    if not apto:
        con.close()
        return "Apartamento no encontrado o no tienes permisos", 403
        
    if request.method == "POST":
        numero = request.form["numero"]
        nombre = request.form["nombre_inquilino"]
        telefono = request.form["telefono"]
        piso = request.form.get("piso", apto.get("piso", ""))
        personas = int(request.form.get("personas", apto.get("personas", 1)) or 1)
        
        cursor.execute("""
            UPDATE apartamentos 
            SET numero = %s, nombre_inquilino = %s, telefono = %s, piso = %s, personas = %s
            WHERE id = %s
        """, (numero, nombre, telefono, piso, personas, apto_id))
        con.commit()
        con.close()
        return redirect("/admin/apartamentos")
        
    con.close()
    return render_template("editar_apartamento.html", apartamento=apto, es_abuela=es_casaabuela())

@app.route("/admin/eliminar_apartamento/<int:apto_id>")
def eliminar_apartamento(apto_id):
    if not es_admin():
        return redirect("/login")
        
    con = conectar()
    cursor = con.cursor()
    
    # Validar propiedad
    cursor.execute("SELECT id FROM apartamentos WHERE id = %s AND administrador_id = %s", (apto_id, session["admin_id"]))
    if not cursor.fetchone():
        con.close()
        return "Apartamento no encontrado o no tienes permisos", 403
        
    cursor.execute("DELETE FROM apartamentos WHERE id = %s", (apto_id,))
    con.commit()
    con.close()
    return redirect("/admin/apartamentos")

@app.route("/admin/editar_recibo/<int:recibo_id>", methods=["GET", "POST"])
def editar_recibo(recibo_id):
    if not es_admin():
        return redirect("/login")
        
    con = conectar()
    cursor = con.cursor()
    
    cursor.execute("SELECT * FROM recibos_luz WHERE id = %s AND administrador_id = %s", (recibo_id, session["admin_id"]))
    recibo = cursor.fetchone()

    if not recibo:
        con.close()
        return "Recibo no encontrado o no tienes permisos", 403
    
    if request.method == "POST":
        fecha = request.form["fecha"]
        energia_facturada = int(request.form["energia_facturada"])
        valor_kwh = float(request.form["valor_kwh"])
        valor_energia = float(request.form["valor_energia"])
        valor_aseo = float(request.form["valor_aseo"])
        observaciones = request.form.get("observaciones", "")
        
        # Update recibo
        cursor.execute("""
            UPDATE recibos_luz
            SET fecha = %s, energia_facturada = %s, valor_kwh = %s, valor_energia = %s, valor_aseo = %s, observaciones = %s
            WHERE id = %s
        """, (fecha, energia_facturada, valor_kwh, valor_energia, valor_aseo, observaciones, recibo_id))
        
        # Recalculate cobros
        cursor.execute("""
            SELECT l.*, a.id as apartamento_id
            FROM lecturas_luz l
            JOIN apartamentos a ON l.apartamento_id = a.id
            WHERE l.fecha = %s AND a.administrador_id = %s
        """, (fecha, session["admin_id"]))
        lecturas = cursor.fetchall()
        
        valor_aseo_por_apto = round(valor_aseo / 8, 2)
        for l in lecturas:
            val_energia = round(l["consumo_mes"] * valor_kwh, 2)
            tot = round(val_energia + valor_aseo_por_apto, 2)
            
            cursor.execute("SELECT id FROM cobros_luz WHERE apartamento_id = %s AND recibo_id = %s", (l["apartamento_id"], recibo_id))
            cobro = cursor.fetchone()
            if cobro:
                cursor.execute("""
                    UPDATE cobros_luz
                    SET consumo = %s, valor_energia = %s, valor_aseo = %s, total = %s
                    WHERE id = %s
                """, (l["consumo_mes"], val_energia, valor_aseo_por_apto, tot, cobro["id"]))
            else:
                cursor.execute("""
                    INSERT INTO cobros_luz (apartamento_id, recibo_id, consumo, valor_energia, valor_aseo, total)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (l["apartamento_id"], recibo_id, l["consumo_mes"], val_energia, valor_aseo_por_apto, tot))
                
        # Recalculate taller_luz
        cursor.execute("""
            SELECT SUM(l.consumo_mes) as total_aptos 
            FROM lecturas_luz l
            JOIN apartamentos a ON l.apartamento_id = a.id
            WHERE l.fecha = %s AND a.administrador_id = %s
        """, (fecha, session["admin_id"]))
        resultado = cursor.fetchone()
        total_aptos = resultado["total_aptos"] or 0
        
        consumo_taller = energia_facturada - total_aptos
        valor_taller = round(consumo_taller * valor_kwh, 2)
        
        cursor.execute("SELECT id FROM taller_luz WHERE recibo_id = %s", (recibo_id,))
        taller = cursor.fetchone()
        if taller:
            cursor.execute("""
                UPDATE taller_luz
                SET consumo_apartamentos = %s, consumo_recibo = %s, consumo_taller = %s, valor_taller = %s, fecha = %s
                WHERE id = %s
            """, (total_aptos, energia_facturada, consumo_taller, valor_taller, fecha, taller["id"]))
        elif consumo_taller > 0:
            cursor.execute("""
                INSERT INTO taller_luz (recibo_id, consumo_apartamentos, consumo_recibo, consumo_taller, valor_taller, fecha, administrador_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (recibo_id, total_aptos, energia_facturada, consumo_taller, valor_taller, fecha, session["admin_id"]))
            
        con.commit()
        con.close()
        return redirect("/historial")
        
    con.close()
    return render_template("editar_recibo.html", recibo=recibo)

@app.route("/admin/eliminar_recibo/<int:recibo_id>")
def eliminar_recibo(recibo_id):
    if not es_admin():
        return redirect("/login")
        
    con = conectar()
    cursor = con.cursor()
    
    # Validar propiedad
    cursor.execute("SELECT id FROM recibos_luz WHERE id = %s AND administrador_id = %s", (recibo_id, session["admin_id"]))
    if not cursor.fetchone():
        con.close()
        return "Recibo no encontrado o no tienes permisos", 403
        
    # Eliminar cobros y taller asociados primero
    cursor.execute("DELETE FROM taller_luz WHERE recibo_id = %s", (recibo_id,))
    cursor.execute("DELETE FROM cobros_luz WHERE recibo_id = %s", (recibo_id,))
    # Eliminar recibo
    cursor.execute("DELETE FROM recibos_luz WHERE id = %s", (recibo_id,))
    
    con.commit()
    con.close()
    return redirect("/historial")

@app.route("/admin/editar_recibo_gas/<int:recibo_id>", methods=["GET", "POST"])
def editar_recibo_gas(recibo_id):
    if not es_admin():
        return redirect("/login")
        
    con = conectar()
    cursor = con.cursor()
    
    cursor.execute("SELECT * FROM recibos_gas WHERE id = %s AND administrador_id = %s", (recibo_id, session["admin_id"]))
    recibo = cursor.fetchone()

    if not recibo:
        con.close()
        return "Recibo no encontrado o no tienes permisos", 403
    
    if request.method == "POST":
        fecha = request.form["fecha"]
        grupo = int(request.form["grupo"])
        referencia = request.form["referencia"]
        consumo_total = int(request.form["consumo_total"])
        valor_total = float(request.form["valor_total"])
        valor_m3 = float(request.form["valor_m3"])
        observaciones = request.form.get("observaciones", "")
        
        # Update recibo
        cursor.execute("""
            UPDATE recibos_gas
            SET fecha = %s, grupo = %s, referencia = %s, consumo_total = %s, valor_total = %s, valor_m3 = %s, observaciones = %s
            WHERE id = %s
        """, (fecha, grupo, referencia, consumo_total, valor_total, valor_m3, observaciones, recibo_id))
        
        # Recalculate cobros
        if grupo == 1:
            numeros = ("101", "401", "402", "501")
        else:
            numeros = ("201", "202", "301", "302")
            
        placeholders = ",".join(["%s"] * len(numeros))
        cursor.execute("""
            SELECT l.*, a.id as apartamento_id
            FROM lecturas_gas l
            JOIN apartamentos a ON l.apartamento_id = a.id
            WHERE l.fecha = %s AND a.numero IN ({placeholders}) AND a.administrador_id = %s
        """, [fecha] + list(numeros) + [session["admin_id"]])
        lecturas = cursor.fetchall()
        
        for l in lecturas:
            val_gas = round(l["consumo_mes"] * valor_m3, 2)
            
            cursor.execute("SELECT id FROM cobros_gas WHERE apartamento_id = %s AND recibo_id = %s", (l["apartamento_id"], recibo_id))
            cobro = cursor.fetchone()
            if cobro:
                cursor.execute("""
                    UPDATE cobros_gas
                    SET consumo = %s, valor_gas = %s, total = %s
                    WHERE id = %s
                """, (l["consumo_mes"], val_gas, val_gas, cobro["id"]))
            else:
                cursor.execute("""
                    INSERT INTO cobros_gas (apartamento_id, recibo_id, consumo, valor_gas, total)
                    VALUES (%s, %s, %s, %s, %s)
                """, (l["apartamento_id"], recibo_id, l["consumo_mes"], val_gas, val_gas))
                
        con.commit()
        con.close()
        return redirect(f"/cobros_gas?grupo={grupo}")
        
    con.close()
    return render_template("editar_recibo_gas.html", recibo=recibo)

@app.route("/admin/eliminar_recibo_gas/<int:recibo_id>")
def eliminar_recibo_gas(recibo_id):
    if not es_admin():
        return redirect("/login")
        
    con = conectar()
    cursor = con.cursor()
    
    # Validar propiedad y obtener grupo
    cursor.execute("SELECT id, grupo FROM recibos_gas WHERE id = %s AND administrador_id = %s", (recibo_id, session["admin_id"]))
    recibo = cursor.fetchone()
    if not recibo:
        con.close()
        return "Recibo no encontrado o no tienes permisos", 403
        
    grupo = recibo["grupo"]
    
    # Eliminar cobros asociados
    cursor.execute("DELETE FROM cobros_gas WHERE recibo_id = %s", (recibo_id,))
    # Eliminar recibo
    cursor.execute("DELETE FROM recibos_gas WHERE id = %s", (recibo_id,))
    
    con.commit()
    con.close()
    return redirect(f"/cobros_gas?grupo={grupo}")

# ==================== MODULO DE AGUA ====================

@app.route("/recibo_agua", methods=["GET", "POST"])
def recibo_agua():
    if not es_admin():
        return redirect("/login")
    if request.method == "POST":
        fecha = request.form["fecha"]
        consumo_total = request.form["consumo_total"]
        valor_total = request.form["valor_total"]
        valor_m3 = request.form["valor_m3"]
        observaciones = request.form.get("observaciones", "")

        con = conectar()
        cursor = con.cursor()
        cursor.execute("""
            INSERT INTO recibos_agua 
            (fecha, consumo_total, valor_total, valor_m3, observaciones, administrador_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (fecha, consumo_total, valor_total, valor_m3, observaciones, session["admin_id"]))
        con.commit()
        con.close()
        return render_template("recibo_agua.html", guardado=True)

    return render_template("recibo_agua.html", guardado=False)

@app.route("/lecturas_agua", methods=["GET", "POST"])
def lecturas_agua():
    if not es_admin():
        return redirect("/login")
    con = conectar()
    cursor = con.cursor()

    cursor.execute("SELECT * FROM apartamentos WHERE administrador_id = %s ORDER BY numero", (session["admin_id"],))
    apartamentos = cursor.fetchall()

    ultimas = {}
    for a in apartamentos:
        cursor.execute("""
            SELECT lectura_actual FROM lecturas_agua 
            WHERE apartamento_id = %s 
            ORDER BY fecha DESC LIMIT 1
        """, (a["id"],))
        ultima = cursor.fetchone()
        ultimas[a["id"]] = ultima["lectura_actual"] if ultima else 0

    guardado = request.args.get("guardado") == "1"
    if request.method == "POST":
        fecha = request.form.get("fecha_lectura")
        for a in apartamentos:
            lectura_actual = int(request.form[f"lectura_{a['id']}"])

            cursor.execute("""
                SELECT id, lectura_anterior FROM lecturas_agua 
                WHERE apartamento_id = %s AND fecha = %s
            """, (a["id"], fecha))
            existente = cursor.fetchone()

            if existente:
                lectura_anterior = existente["lectura_anterior"]
                consumo = lectura_actual - lectura_anterior
                cursor.execute("""
                    UPDATE lecturas_agua 
                    SET lectura_actual = %s, consumo_mes = %s
                    WHERE id = %s
                """, (lectura_actual, consumo, existente["id"]))
            else:
                lectura_anterior = ultimas[a["id"]]
                consumo = lectura_actual - lectura_anterior
                cursor.execute("""
                    INSERT INTO lecturas_agua 
                    (apartamento_id, lectura_anterior, fecha, lectura_actual, consumo_mes)
                    VALUES (%s, %s, %s, %s, %s)
                """, (a["id"], lectura_anterior, fecha, lectura_actual, consumo))

        con.commit()
        con.close()
        return redirect(url_for("lecturas_agua", guardado=1))

    con.close()
    return render_template("lecturas_agua.html",
                           apartamentos=apartamentos,
                           ultimas=ultimas,
                           guardado=guardado)

@app.route("/cobros_agua")
def cobros_agua():
    if not es_admin():
        return redirect("/login")
    con = conectar()
    cursor = con.cursor()

    cursor.execute("SELECT * FROM recibos_agua WHERE administrador_id = %s ORDER BY fecha DESC LIMIT 1", (session["admin_id"],))
    recibo = cursor.fetchone()

    if not recibo:
        con.close()
        return render_template("cobros_agua.html", cobros=[], recibo=None)

    cursor.execute("""
        SELECT l.*, a.numero, a.nombre_inquilino, a.id as apartamento_id
        FROM lecturas_agua l
        JOIN apartamentos a ON l.apartamento_id = a.id
        WHERE l.fecha = %s AND a.administrador_id = %s
        ORDER BY a.numero
    """, (recibo["fecha"], session["admin_id"]))
    lecturas = cursor.fetchall()

    # Deduplicar lecturas por apartamento_id por seguridad
    lecturas_map = {}
    for l in lecturas:
        aid = l["apartamento_id"]
        if aid not in lecturas_map or l["consumo_mes"] > lecturas_map[aid]["consumo_mes"]:
            lecturas_map[aid] = l
    lecturas = list(lecturas_map.values())
    lecturas.sort(key=lambda x: str(x["numero"]))

    # Paso 1: Calcular cobro base por consumo
    cobros_lista = []
    consumo_total_aptos = 0
    suma_base = 0
    for l in lecturas:
        valor_agua = round(l["consumo_mes"] * float(recibo["valor_m3"]), 2)
        consumo_total_aptos += l["consumo_mes"]
        suma_base += valor_agua
        cobros_lista.append({
            "numero": l["numero"],
            "nombre": l["nombre_inquilino"],
            "consumo": l["consumo_mes"],
            "valor_agua_base": valor_agua,
            "valor_agua": valor_agua,
            "ajuste": 0,
            "apartamento_id": l["apartamento_id"]
        })

    # Paso 2: Calcular diferencia y repartir proporcionalmente
    valor_total_recibo = float(recibo["valor_total"])
    diferencia = round(valor_total_recibo - suma_base, 2)

    if consumo_total_aptos > 0 and diferencia != 0:
        for c in cobros_lista:
            proporcion = c["consumo"] / consumo_total_aptos
            ajuste = round(diferencia * proporcion, 2)
            c["ajuste"] = ajuste
            c["valor_agua"] = round(c["valor_agua_base"] + ajuste, 2)

    # Guardar cobros en BD con upsert
    if lecturas:
        for c in cobros_lista:
            cursor.execute("SELECT id FROM cobros_agua WHERE apartamento_id = %s AND recibo_id = %s", (c["apartamento_id"], recibo["id"]))
            cobro_existente = cursor.fetchone()
            if cobro_existente:
                cursor.execute("""
                    UPDATE cobros_agua
                    SET consumo = %s, valor_agua = %s, total = %s
                    WHERE id = %s
                """, (c["consumo"], c["valor_agua"], c["valor_agua"], cobro_existente["id"]))
            else:
                cursor.execute("""
                    INSERT INTO cobros_agua
                    (apartamento_id, recibo_id, consumo, valor_agua, total)
                    VALUES (%s, %s, %s, %s, %s)
                """, (c["apartamento_id"], recibo["id"], c["consumo"],
                      c["valor_agua"], c["valor_agua"]))

        # Limpiar cobros sobrantes para este recibo si no corresponden
        ids_validos = [c["apartamento_id"] for c in cobros_lista]
        if ids_validos:
            placeholders_clean = ",".join(["%s"] * len(ids_validos))
            cursor.execute(f"DELETE FROM cobros_agua WHERE recibo_id = %s AND apartamento_id NOT IN ({placeholders_clean})", [recibo["id"]] + ids_validos)

        con.commit()

    con.close()

    # Resumen de validación
    suma_final = sum(c["valor_agua"] for c in cobros_lista)
    resumen = {
        "valor_recibo": valor_total_recibo,
        "suma_cobros_base": suma_base,
        "diferencia": diferencia,
        "suma_final": round(suma_final, 2)
    }

    return render_template("cobros_agua.html", cobros=cobros_lista, recibo=recibo, resumen=resumen)

@app.route("/cobros_agua/<int:recibo_id>")
def cobros_agua_mes(recibo_id):
    if not es_admin():
        return redirect("/login")
    con = conectar()
    cursor = con.cursor()

    cursor.execute("SELECT * FROM recibos_agua WHERE id = %s AND administrador_id = %s", (recibo_id, session["admin_id"]))
    recibo = cursor.fetchone()

    if not recibo:
        con.close()
        return "Recibo no encontrado o no tienes permisos", 403

    cursor.execute("""
        SELECT c.*, a.numero, a.nombre_inquilino, a.id as apartamento_id
        FROM cobros_agua c
        JOIN apartamentos a ON c.apartamento_id = a.id
        WHERE c.recibo_id = %s AND a.administrador_id = %s
        ORDER BY a.numero
    """, (recibo_id, session["admin_id"]))
    cobros = cursor.fetchall()

    # Deduplicar por si quedaron duplicados
    cobros_map = {}
    for c in cobros:
        aid = c["apartamento_id"]
        if aid not in cobros_map or c["consumo"] > cobros_map[aid]["consumo"]:
            cobros_map[aid] = c
    cobros = list(cobros_map.values())
    cobros.sort(key=lambda x: str(x["numero"]))

    con.close()

    return render_template("cobros_agua.html", cobros=cobros, recibo=recibo)

@app.route("/lecturas_agua_ver")
def lecturas_agua_ver():
    if not es_admin():
        return redirect("/login")
    con = conectar()
    cursor = con.cursor()
    cursor.execute("""
        SELECT l.*, a.numero, a.nombre_inquilino
        FROM lecturas_agua l
        JOIN apartamentos a ON l.apartamento_id = a.id
        WHERE a.administrador_id = %s
        ORDER BY l.fecha DESC, a.numero
    """, (session["admin_id"],))
    lecturas = cursor.fetchall()
    con.close()
    return render_template("lecturas_agua_ver.html", lecturas=lecturas)

@app.route("/editar_lectura_agua/<int:lectura_id>", methods=["GET", "POST"])
def editar_lectura_agua(lectura_id):
    if not es_admin():
        return redirect("/login")
    con = conectar()
    cursor = con.cursor()

    cursor.execute("""
        SELECT l.*, a.numero FROM lecturas_agua l
        JOIN apartamentos a ON l.apartamento_id = a.id
        WHERE l.id = %s AND a.administrador_id = %s
    """, (lectura_id, session["admin_id"]))
    lectura = cursor.fetchone()

    if not lectura:
        con.close()
        return "Lectura no encontrada o no tienes permisos", 403

    if request.method == "POST":
        lectura_actual = int(request.form["lectura_actual"])
        lectura_anterior = int(request.form["lectura_anterior"])
        consumo = lectura_actual - lectura_anterior

        cursor.execute("""
            UPDATE lecturas_agua 
            SET lectura_anterior = %s, lectura_actual = %s, consumo_mes = %s
            WHERE id = %s
        """, (lectura_anterior, lectura_actual, consumo, lectura_id))

        # Recalcular cobro si existe
        cursor.execute("""
            SELECT c.id, r.valor_m3
            FROM cobros_agua c
            JOIN recibos_agua r ON c.recibo_id = r.id
            WHERE c.apartamento_id = %s AND r.administrador_id = %s
            ORDER BY r.fecha DESC LIMIT 1
        """, (lectura["apartamento_id"], session["admin_id"]))
        cobro = cursor.fetchone()

        if cobro:
            valor_agua = round(consumo * float(cobro["valor_m3"]), 2)
            cursor.execute("""
                UPDATE cobros_agua
                SET consumo = %s, valor_agua = %s, total = %s
                WHERE id = %s
            """, (consumo, valor_agua, valor_agua, cobro["id"]))

        con.commit()
        con.close()
        return redirect("/lecturas_agua_ver")

    con.close()
    return render_template("editar_lectura_agua.html", lectura=lectura)

@app.route("/admin/eliminar_lectura_agua/<int:lectura_id>")
def eliminar_lectura_agua(lectura_id):
    if not es_admin():
        return redirect("/login")
    con = conectar()
    cursor = con.cursor()

    cursor.execute("""
        SELECT l.*, a.administrador_id 
        FROM lecturas_agua l
        JOIN apartamentos a ON l.apartamento_id = a.id
        WHERE l.id = %s AND a.administrador_id = %s
    """, (lectura_id, session["admin_id"]))
    lectura = cursor.fetchone()

    if not lectura:
        con.close()
        return "Lectura no encontrada o no tienes permisos", 403

    # Buscar recibo de esa fecha para limpiar cobro asociado
    cursor.execute("SELECT id FROM recibos_agua WHERE fecha = %s AND administrador_id = %s", (lectura["fecha"], session["admin_id"]))
    recibo = cursor.fetchone()
    if recibo:
        cursor.execute("DELETE FROM cobros_agua WHERE apartamento_id = %s AND recibo_id = %s", (lectura["apartamento_id"], recibo["id"]))

    cursor.execute("DELETE FROM lecturas_agua WHERE id = %s", (lectura_id,))
    con.commit()
    con.close()
    return redirect("/lecturas_agua_ver")

@app.route("/whatsapp_agua/<int:apartamento_id>")
def whatsapp_agua(apartamento_id):
    recibo_id = request.args.get("recibo_id")
    con = conectar()
    cursor = con.cursor()

    cursor.execute("SELECT * FROM apartamentos WHERE id = %s", (apartamento_id,))
    apto = cursor.fetchone()

    if recibo_id:
        cursor.execute("""
            SELECT c.*, r.fecha 
            FROM cobros_agua c
            JOIN recibos_agua r ON c.recibo_id = r.id
            WHERE c.apartamento_id = %s AND r.id = %s
        """, (apartamento_id, recibo_id))
    else:
        cursor.execute("""
            SELECT c.*, r.fecha 
            FROM cobros_agua c
            JOIN recibos_agua r ON c.recibo_id = r.id
            WHERE c.apartamento_id = %s
            ORDER BY r.fecha DESC LIMIT 1
        """, (apartamento_id,))
    cobro = cursor.fetchone()
    con.close()

    if not cobro or not apto:
        return "No hay datos", 404

    mensaje = f"""Hola,

Apartamento {apto['numero']}

Consumo agua: {cobro['consumo']} m³
Total a pagar: ${int(cobro['total']):,}

Gracias."""

    telefono = apto['telefono']
    print("RAW DB PHONE:", telefono)
    telefono = str(telefono).strip()
    telefono = telefono.replace(" ", "")
    telefono = telefono.replace("-", "")
    telefono = telefono.replace("+", "")
    if telefono.startswith("57"):
        telefono = telefono[2:]
    print("CLEAN PHONE:", telefono)
    if len(telefono) == 10:
        telefono = "57" + telefono
    print("FINAL PHONE:", telefono)
    url_whatsapp = f"https://wa.me/{telefono}?text={quote(mensaje)}"
    return redirect(url_whatsapp)

@app.route("/admin/editar_recibo_agua/<int:recibo_id>", methods=["GET", "POST"])
def editar_recibo_agua(recibo_id):
    if not es_admin():
        return redirect("/login")
        
    con = conectar()
    cursor = con.cursor()
    
    cursor.execute("SELECT * FROM recibos_agua WHERE id = %s AND administrador_id = %s", (recibo_id, session["admin_id"]))
    recibo = cursor.fetchone()

    if not recibo:
        con.close()
        return "Recibo no encontrado o no tienes permisos", 403
    
    if request.method == "POST":
        fecha = request.form["fecha"]
        consumo_total = int(request.form["consumo_total"])
        valor_total = float(request.form["valor_total"])
        valor_m3 = float(request.form["valor_m3"])
        observaciones = request.form.get("observaciones", "")
        
        # Update recibo
        cursor.execute("""
            UPDATE recibos_agua
            SET fecha = %s, consumo_total = %s, valor_total = %s, valor_m3 = %s, observaciones = %s
            WHERE id = %s
        """, (fecha, consumo_total, valor_total, valor_m3, observaciones, recibo_id))
        
        # Recalculate cobros
        cursor.execute("""
            SELECT l.*, a.id as apartamento_id
            FROM lecturas_agua l
            JOIN apartamentos a ON l.apartamento_id = a.id
            WHERE l.fecha = %s AND a.administrador_id = %s
        """, (fecha, session["admin_id"]))
        lecturas = cursor.fetchall()
        
        for l in lecturas:
            val_agua = round(l["consumo_mes"] * valor_m3, 2)
            
            cursor.execute("SELECT id FROM cobros_agua WHERE apartamento_id = %s AND recibo_id = %s", (l["apartamento_id"], recibo_id))
            cobro = cursor.fetchone()
            if cobro:
                cursor.execute("""
                    UPDATE cobros_agua
                    SET consumo = %s, valor_agua = %s, total = %s
                    WHERE id = %s
                """, (l["consumo_mes"], val_agua, val_agua, cobro["id"]))
            else:
                cursor.execute("""
                    INSERT INTO cobros_agua (apartamento_id, recibo_id, consumo, valor_agua, total)
                    VALUES (%s, %s, %s, %s, %s)
                """, (l["apartamento_id"], recibo_id, l["consumo_mes"], val_agua, val_agua))
                
        con.commit()
        con.close()
        return redirect("/cobros_agua")
        
    con.close()
    return render_template("editar_recibo_agua.html", recibo=recibo)

@app.route("/admin/eliminar_recibo_agua/<int:recibo_id>")
def eliminar_recibo_agua(recibo_id):
    if not es_admin():
        return redirect("/login")
        
    con = conectar()
    cursor = con.cursor()
    
    # Validar propiedad
    cursor.execute("SELECT id FROM recibos_agua WHERE id = %s AND administrador_id = %s", (recibo_id, session["admin_id"]))
    if not cursor.fetchone():
        con.close()
        return "Recibo no encontrado o no tienes permisos", 403
        
    # Eliminar cobros asociados
    cursor.execute("DELETE FROM cobros_agua WHERE recibo_id = %s", (recibo_id,))
    # Eliminar recibo
    cursor.execute("DELETE FROM recibos_agua WHERE id = %s", (recibo_id,))
    
    con.commit()
    con.close()
    return redirect("/cobros_agua")

# ==================== MODULO CASA ABUELA (COBRO POR CABEZA) ====================

@app.route("/abuela/recibo", methods=["GET", "POST"])
def abuela_recibo():
    if not es_admin():
        return redirect("/login")
    
    con = conectar()
    cursor = con.cursor()

    if request.method == "POST":
        fecha = request.form["fecha"]
        tipo_recibo = request.form.get("tipo_recibo", "Todos") # "Todos", "Luz", "Agua", "Gas"
        concepto = request.form.get("concepto", "").strip() or f"Recibo de {tipo_recibo}"
        observaciones = request.form.get("observaciones", "").strip()

        val_luz = float(request.form.get("valor_luz", 0) or 0)
        val_agua = float(request.form.get("valor_agua", 0) or 0)
        val_gas = float(request.form.get("valor_gas", 0) or 0)
        val_directo = float(request.form.get("valor_total_directo", 0) or 0)

        if val_directo > 0:
            valor_total = val_directo
        else:
            valor_total = val_luz + val_agua + val_gas

        cursor.execute("SELECT * FROM apartamentos WHERE administrador_id = %s ORDER BY id", (session["admin_id"],))
        apartamentos = cursor.fetchall()
        
        total_personas = sum(a.get("personas", 1) for a in apartamentos)
        if total_personas == 0:
            total_personas = 1

        valor_por_cabeza = round(valor_total / total_personas, 2)

        cursor.execute("""
            INSERT INTO recibos_cabeza 
            (fecha, concepto, tipo_recibo, valor_luz, valor_agua, valor_gas, valor_total, total_personas, valor_por_cabeza, observaciones, administrador_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (fecha, concepto, tipo_recibo, val_luz, val_agua, val_gas, valor_total, total_personas, valor_por_cabeza, observaciones, session["admin_id"]))
        recibo_id = cursor.lastrowid

        # Insertar cobros por inquilino
        for a in apartamentos:
            p = a.get("personas", 1)
            if val_directo > 0 or (val_luz == 0 and val_agua == 0 and val_gas == 0):
                apto_luz = round((valor_por_cabeza * p), 2) if tipo_recibo == "Luz" else 0
                apto_agua = round((valor_por_cabeza * p), 2) if tipo_recibo == "Agua" else 0
                apto_gas = round((valor_por_cabeza * p), 2) if tipo_recibo == "Gas" else 0
                apto_total = round(valor_por_cabeza * p, 2)
            else:
                apto_luz = round((val_luz / total_personas) * p, 2) if val_luz > 0 else 0
                apto_agua = round((val_agua / total_personas) * p, 2) if val_agua > 0 else 0
                apto_gas = round((val_gas / total_personas) * p, 2) if val_gas > 0 else 0
                apto_total = round(apto_luz + apto_agua + apto_gas, 2)

            cursor.execute("""
                INSERT INTO cobros_cabeza
                (recibo_id, apartamento_id, personas, valor_luz, valor_agua, valor_gas, total)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (recibo_id, a["id"], p, apto_luz, apto_agua, apto_gas, apto_total))

        con.commit()
        con.close()
        return redirect(f"/abuela/cobros?guardado=1&recibo_id={recibo_id}")

    cursor.execute("SELECT * FROM apartamentos WHERE administrador_id = %s ORDER BY id", (session["admin_id"],))
    apartamentos = cursor.fetchall()
    total_personas = sum(a.get("personas", 1) for a in apartamentos)
    con.close()
    return render_template("abuela_recibo.html", total_personas=total_personas, num_inquilinos=len(apartamentos))

@app.route("/abuela/cobros")
def abuela_cobros():
    if not es_admin():
        return redirect("/login")
    
    con = conectar()
    cursor = con.cursor()

    recibo_id = request.args.get("recibo_id")
    if recibo_id:
        cursor.execute("SELECT * FROM recibos_cabeza WHERE id = %s AND administrador_id = %s", (recibo_id, session["admin_id"]))
    else:
        cursor.execute("SELECT * FROM recibos_cabeza WHERE administrador_id = %s ORDER BY fecha DESC, id DESC LIMIT 1", (session["admin_id"],))
    recibo = cursor.fetchone()

    cobros = []
    if recibo:
        cursor.execute("""
            SELECT c.*, a.numero, a.nombre_inquilino, a.telefono, a.piso
            FROM cobros_cabeza c
            JOIN apartamentos a ON c.apartamento_id = a.id
            WHERE c.recibo_id = %s
            ORDER BY a.id ASC
        """, (recibo["id"],))
        cobros = cursor.fetchall()

    guardado = request.args.get("guardado") == "1"
    con.close()
    return render_template("abuela_cobros.html", recibo=recibo, cobros=cobros, guardado=guardado)

@app.route("/abuela/whatsapp/<int:apartamento_id>")
def abuela_whatsapp(apartamento_id):
    if not es_admin():
        return redirect("/login")

    recibo_id = request.args.get("recibo_id")
    con = conectar()
    cursor = con.cursor()

    cursor.execute("SELECT * FROM apartamentos WHERE id = %s AND administrador_id = %s", (apartamento_id, session["admin_id"]))
    apto = cursor.fetchone()

    if recibo_id:
        cursor.execute("SELECT * FROM recibos_cabeza WHERE id = %s AND administrador_id = %s", (recibo_id, session["admin_id"]))
    else:
        cursor.execute("SELECT * FROM recibos_cabeza WHERE administrador_id = %s ORDER BY fecha DESC, id DESC LIMIT 1", (session["admin_id"],))
    recibo = cursor.fetchone()

    if not apto or not recibo:
        con.close()
        return "No hay información disponible", 404

    cursor.execute("SELECT * FROM cobros_cabeza WHERE recibo_id = %s AND apartamento_id = %s", (recibo["id"], apartamento_id))
    cobro = cursor.fetchone()
    con.close()

    if not cobro:
        return "Cobro no encontrado", 404

    nombre_mes = "este mes"
    if hasattr(recibo["fecha"], "month"):
        nombre_mes = MESES.get(recibo["fecha"].month, "este mes")
    elif isinstance(recibo["fecha"], str):
        try:
            from datetime import datetime
            dt = datetime.strptime(recibo["fecha"], "%Y-%m-%d")
            nombre_mes = MESES.get(dt.month, "este mes")
        except Exception:
            pass

    piso_txt = f" ({apto['piso']})" if apto.get('piso') else ""
    
    # Construcción del mensaje
    tipo = recibo.get("tipo_recibo", "Servicios")
    desglose_lineas = []
    if cobro.get("valor_luz") and float(cobro["valor_luz"]) > 0:
        desglose_lineas.append(f"💡 Luz: ${int(cobro['valor_luz']):,}")
    if cobro.get("valor_agua") and float(cobro["valor_agua"]) > 0:
        desglose_lineas.append(f"💧 Agua: ${int(cobro['valor_agua']):,}")
    if cobro.get("valor_gas") and float(cobro["valor_gas"]) > 0:
        desglose_lineas.append(f"🔥 Gas: ${int(cobro['valor_gas']):,}")
    
    texto_desglose = "\n".join(desglose_lineas)
    if texto_desglose:
        texto_desglose = "\n" + texto_desglose + "\n"
    else:
        texto_desglose = ""

    nombre_concepto = "servicios" if tipo == "Todos" else f"recibo de {tipo}"

    mensaje = f"""Hola {apto['nombre_inquilino']}{piso_txt} 👋

Cobro de {nombre_concepto} del mes de {nombre_mes}:
👥 Personas a cargo: {cobro['personas']} persona(s)
{texto_desglose}
👤 Valor por persona: ${int(recibo['valor_por_cabeza']):,}
💰 Total a pagar: ${int(cobro['total']):,}

Por favor realizar el pago correspondiente. ¡Muchas gracias! 🙏"""

    telefono = str(apto.get('telefono', '')).strip()
    telefono = telefono.replace(" ", "").replace("-", "").replace("+", "")
    if telefono.startswith("57"):
        telefono = telefono[2:]
    if len(telefono) == 10:
        telefono = "57" + telefono

    url_whatsapp = f"https://wa.me/{telefono}?text={quote(mensaje)}"
    return redirect(url_whatsapp)

@app.route("/abuela/historial")
def abuela_historial():
    if not es_admin():
        return redirect("/login")
    
    con = conectar()
    cursor = con.cursor()
    cursor.execute("SELECT * FROM recibos_cabeza WHERE administrador_id = %s ORDER BY fecha DESC, id DESC", (session["admin_id"],))
    recibos = cursor.fetchall()
    con.close()
    return render_template("abuela_historial.html", recibos=recibos)

@app.route("/abuela/eliminar_recibo/<int:recibo_id>")
def abuela_eliminar_recibo(recibo_id):
    if not es_admin():
        return redirect("/login")
    
    con = conectar()
    cursor = con.cursor()
    cursor.execute("SELECT id FROM recibos_cabeza WHERE id = %s AND administrador_id = %s", (recibo_id, session["admin_id"]))
    if not cursor.fetchone():
        con.close()
        return "Recibo no encontrado o sin permisos", 403

    cursor.execute("DELETE FROM cobros_cabeza WHERE recibo_id = %s", (recibo_id,))
    cursor.execute("DELETE FROM recibos_cabeza WHERE id = %s", (recibo_id,))
    con.commit()
    con.close()
    return redirect("/abuela/historial")

if __name__ == "__main__":
    app.run(debug=True)