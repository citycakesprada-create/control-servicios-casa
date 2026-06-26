from flask import Flask, render_template, request, redirect, session, url_for
from database.conexion import conectar
from urllib.parse import quote
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "clave_secreta_super_segura_para_servicios_casa"

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

        con.close()
    except Exception as e:
        print("Error al inicializar la base de datos:", e)

inicializar_db()

def es_admin():
    return "usuario_admin" in session and "admin_id" in session

@app.route("/")
def inicio():
    if not es_admin():
        return redirect("/login")
    con = conectar()
    cursor = con.cursor()
    cursor.execute("SELECT * FROM apartamentos WHERE administrador_id = %s ORDER BY numero", (session["admin_id"],))
    apartamentos = cursor.fetchall()
    con.close()
    return render_template("index.html", apartamentos=apartamentos)

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

    if request.method == "POST":
        fecha = request.form.get("fecha_lectura")
        for a in apartamentos:
            lectura_actual = int(request.form[f"lectura_{a['id']}"])
            lectura_anterior = ultimas[a["id"]]
            consumo = lectura_actual - lectura_anterior

            cursor.execute("""
                INSERT INTO lecturas_luz 
                (apartamento_id, lectura_anterior, fecha, lectura_actual, consumo_mes)
                VALUES (%s, %s, %s, %s, %s)
            """, (a["id"], lectura_anterior, fecha, lectura_actual, consumo))

        con.commit()
        con.close()
        return render_template("lecturas.html",
                               apartamentos=apartamentos,
                               ultimas=ultimas,
                               recibo=recibo,
                               guardado=True)

    con.close()
    return render_template("lecturas.html",
                           apartamentos=apartamentos,
                           ultimas=ultimas,
                           recibo=recibo,
                           guardado=False)

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

    cursor.execute("SELECT id FROM cobros_luz WHERE recibo_id = %s LIMIT 1", (recibo["id"],))
    ya_calculado = cursor.fetchone()

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

        if not ya_calculado:
            cursor.execute("""
                INSERT INTO cobros_luz 
                (apartamento_id, recibo_id, consumo, valor_energia, valor_aseo, total)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (l["apartamento_id"], recibo["id"], l["consumo_mes"],
                  valor_energia, valor_aseo_por_apto, total))

    if not ya_calculado:
        con.commit()
    con.close()

    return render_template("cobros.html", cobros=cobros_lista, recibo=recibo)

@app.route("/whatsapp/<int:apartamento_id>")
def whatsapp(apartamento_id):
    con = conectar()
    cursor = con.cursor()

    cursor.execute("SELECT * FROM apartamentos WHERE id = %s", (apartamento_id,))
    apto = cursor.fetchone()

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

    mensaje = f"""Hola,

Apartamento {apto['numero']}

Consumo energia: {cobro['consumo']} kWh
Valor energia: ${int(cobro['valor_energia']):,}
Aseo: ${int(cobro['valor_aseo']):,}

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
    con = conectar()
    cursor = con.cursor()

    cursor.execute("SELECT * FROM apartamentos WHERE id = %s", (apartamento_id,))
    apto = cursor.fetchone()

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

    mensaje = f"""Hola,

Apartamento {apto['numero']}

Gas consumido: {cobro['consumo']} m3
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

    cursor.execute("SELECT id FROM cobros_gas WHERE recibo_id = %s LIMIT 1", (recibo["id"],))
    ya_calculado = cursor.fetchone()

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

    # Guardar cobros en BD
    if not ya_calculado and lecturas:
        for c in cobros_lista:
            cursor.execute("""
                INSERT INTO cobros_gas
                (apartamento_id, recibo_id, consumo, valor_gas, total)
                VALUES (%s, %s, %s, %s, %s)
            """, (c["apartamento_id"], recibo["id"], c["consumo"],
                  c["valor_gas"], c["valor_gas"]))
        con.commit()
        print("COBROS GENERADOS:", len(cobros_lista))

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

    if request.method == "POST":
        fecha = request.form.get("fecha_lectura")
        for a in apartamentos:
            lectura_actual = int(request.form[f"lectura_{a['id']}"])
            lectura_anterior = ultimas[a["id"]]
            consumo = lectura_actual - lectura_anterior

            cursor.execute("""
                INSERT INTO lecturas_gas
                (apartamento_id, lectura_anterior, fecha, lectura_actual, consumo_mes)
                VALUES (%s, %s, %s, %s, %s)
            """, (a["id"], lectura_anterior, fecha, lectura_actual, consumo))
            print("APARTAMENTO:", a["id"])
            print("CONSUMO:", consumo)
            print("FECHA:", fecha)
            print("INSERT EXECUTED")

        con.commit()
        cursor.execute("SELECT * FROM lecturas_gas ORDER BY id DESC LIMIT 10")
        print("ULTIMAS LECTURAS:", cursor.fetchall())
        con.close()
        return render_template("lecturas_gas.html",
                               apartamentos=apartamentos,
                               ultimas=ultimas,
                               recibo=recibo,
                               guardado=True,
                               grupo_actual=grupo_actual)

    con.close()
    return render_template("lecturas_gas.html",
                           apartamentos=apartamentos,
                           ultimas=ultimas,
                           recibo=recibo,
                           guardado=False,
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
        
        cursor.execute("""
            INSERT INTO apartamentos (numero, nombre_inquilino, telefono, administrador_id)
            VALUES (%s, %s, %s, %s)
        """, (numero, nombre, telefono, session["admin_id"]))
        con.commit()
        
    cursor.execute("SELECT * FROM apartamentos WHERE administrador_id = %s ORDER BY numero", (session["admin_id"],))
    apartamentos = cursor.fetchall()
    con.close()
    
    return render_template("admin_apartamentos.html", apartamentos=apartamentos)

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
        
        cursor.execute("""
            UPDATE apartamentos 
            SET numero = %s, nombre_inquilino = %s, telefono = %s
            WHERE id = %s
        """, (numero, nombre, telefono, apto_id))
        con.commit()
        con.close()
        return redirect("/admin/apartamentos")
        
    con.close()
    return render_template("editar_apartamento.html", apartamento=apto)

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

    if request.method == "POST":
        fecha = request.form.get("fecha_lectura")
        for a in apartamentos:
            lectura_actual = int(request.form[f"lectura_{a['id']}"])
            lectura_anterior = ultimas[a["id"]]
            consumo = lectura_actual - lectura_anterior

            cursor.execute("""
                INSERT INTO lecturas_agua 
                (apartamento_id, lectura_anterior, fecha, lectura_actual, consumo_mes)
                VALUES (%s, %s, %s, %s, %s)
            """, (a["id"], lectura_anterior, fecha, lectura_actual, consumo))

        con.commit()
        con.close()
        return render_template("lecturas_agua.html",
                               apartamentos=apartamentos,
                               ultimas=ultimas,
                               guardado=True)

    con.close()
    return render_template("lecturas_agua.html",
                           apartamentos=apartamentos,
                           ultimas=ultimas,
                           guardado=False)

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

    cursor.execute("SELECT id FROM cobros_agua WHERE recibo_id = %s LIMIT 1", (recibo["id"],))
    ya_calculado = cursor.fetchone()

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

    # Guardar cobros en BD
    if not ya_calculado and lecturas:
        for c in cobros_lista:
            cursor.execute("""
                INSERT INTO cobros_agua
                (apartamento_id, recibo_id, consumo, valor_agua, total)
                VALUES (%s, %s, %s, %s, %s)
            """, (c["apartamento_id"], recibo["id"], c["consumo"],
                  c["valor_agua"], c["valor_agua"]))
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

@app.route("/whatsapp_agua/<int:apartamento_id>")
def whatsapp_agua(apartamento_id):
    con = conectar()
    cursor = con.cursor()

    cursor.execute("SELECT * FROM apartamentos WHERE id = %s", (apartamento_id,))
    apto = cursor.fetchone()

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

if __name__ == "__main__":
    app.run(debug=True)