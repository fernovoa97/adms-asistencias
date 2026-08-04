from flask import Flask, request, render_template, Response
from datetime import datetime
import csv
import io
import os
import itertools
import secrets

from db import obtener_conexion, inicializar_base_datos
from auth import auth_bp, login_requerido
from trabajadores import trabajadores_bp

app = Flask(__name__)

# La clave de sesion DEBE ser fija (definida por variable de entorno) en
# produccion. Si no esta definida, generamos una aleatoria para que la app
# funcione igual, pero avisamos: con una clave aleatoria, las sesiones se
# invalidan cada vez que la app se reinicia/redepliega en Railway.
app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    app.secret_key = secrets.token_hex(32)
    print(
        "ADVERTENCIA: no se definio la variable de entorno SECRET_KEY. "
        "Se genero una clave temporal; las sesiones se cerraran solas "
        "cada vez que la app se reinicie. Define SECRET_KEY en Railway "
        "para evitarlo."
    )

inicializar_base_datos()

app.register_blueprint(auth_bp)
app.register_blueprint(trabajadores_bp)


# ==========================================
# COMANDOS PENDIENTES (huellero)
# ==========================================
# Los comandos se mantienen temporalmente en memoria.
# Si Railway reinicia la aplicación, se pierden.
# Esto no afecta a los datos almacenados en PostgreSQL.

COMANDOS_PENDIENTES = {}
CONTADOR_COMANDOS = itertools.count(1)


# ==========================================
# GUARDAR ASISTENCIA
# ==========================================

def guardar_asistencia(codigo_empleado, fecha_hora, tipo_marcaje, estado, verificacion, sn_dispositivo):
    try:
        fecha_hora_obj = datetime.strptime(fecha_hora, "%Y-%m-%d %H:%M:%S")
        fecha = fecha_hora_obj.date()
        hora = fecha_hora_obj.time()
        fecha_recepcion = datetime.now()

        conexion = obtener_conexion()
        cursor = conexion.cursor()

        cursor.execute("""
            INSERT INTO asistencias (
                codigo_empleado, fecha_hora, fecha, hora,
                tipo_marcaje, estado, verificacion, sn_dispositivo, fecha_recepcion
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (codigo_empleado, fecha_hora, sn_dispositivo) DO NOTHING
        """, (
            codigo_empleado, fecha_hora_obj, fecha, hora,
            tipo_marcaje, estado, verificacion, sn_dispositivo, fecha_recepcion
        ))

        filas_afectadas = cursor.rowcount
        conexion.commit()
        cursor.close()
        conexion.close()

        if filas_afectadas > 0:
            print(f"ASISTENCIA GUARDADA: {codigo_empleado} - {fecha_hora}")
        else:
            print(f"ASISTENCIA DUPLICADA: {codigo_empleado} - {fecha_hora}")

    except Exception as error:
        print("ERROR GUARDANDO ASISTENCIA:", error)


# ==========================================
# GUARDAR / ACTUALIZAR TRABAJADOR (desde el huellero)
# ==========================================
# Nota: esto sincroniza codigo_empleado + nombre desde el dispositivo.
# Si el trabajador ya existia (creado desde el modulo de personal), esto
# solo actualiza su nombre y le asocia el codigo de empleado; no toca DNI,
# documentos ni el resto de sus datos.

def guardar_trabajador(codigo_empleado, nombre_completo):
    try:
        codigo_empleado = codigo_empleado.strip()
        nombre_completo = nombre_completo.strip()

        if not codigo_empleado:
            return

        partes = nombre_completo.split(" ", 1)
        nombres = partes[0] if partes and partes[0] else "SIN NOMBRE"
        apellidos = partes[1] if len(partes) > 1 else ""

        fecha_registro = datetime.now()

        conexion = obtener_conexion()
        cursor = conexion.cursor()

        cursor.execute("""
            INSERT INTO trabajadores (codigo_empleado, nombres, apellidos, fecha_registro)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (codigo_empleado)
            DO UPDATE SET nombres = EXCLUDED.nombres, apellidos = EXCLUDED.apellidos
        """, (codigo_empleado, nombres, apellidos, fecha_registro))

        conexion.commit()
        cursor.close()
        conexion.close()

        print(f"TRABAJADOR SINCRONIZADO DESDE HUELLERO: {codigo_empleado} - {nombre_completo}")

    except Exception as error:
        print("ERROR GUARDANDO TRABAJADOR:", error)


# ==========================================
# PROCESAR OPERLOG
# ==========================================

def procesar_operlog(datos):
    lineas = datos.strip().splitlines()

    for linea in lineas:
        linea = linea.strip()

        if not linea or not linea.upper().startswith("USER"):
            continue

        campos = linea.split("\t")
        datos_usuario = {}

        for campo in campos:
            campo = campo.strip()

            if campo.upper().startswith("USER "):
                campo = campo[5:]

            if "=" in campo:
                clave, _, valor = campo.partition("=")
                datos_usuario[clave.strip().upper()] = valor.strip()

        pin = datos_usuario.get("PIN")
        nombre = datos_usuario.get("NAME", "")

        if pin:
            guardar_trabajador(pin, nombre)


# ==========================================
# COMUNICACIÓN ADMS (sin login: las usa el dispositivo, no una persona)
# ==========================================

@app.route("/iclock/cdata", methods=["GET", "POST"])
def cdata():
    numero_serie = request.args.get("SN", "DESCONOCIDO")
    tabla = request.args.get("table", "")

    if request.method == "GET":
        print(f"GET CDATA recibido desde {numero_serie}")
        return "OK"

    datos = request.data.decode(errors="ignore")

    print("\n==============================")
    print("DATOS RECIBIDOS DEL HUELLERO")
    print("==============================")
    print("SN:", numero_serie)
    print("TABLA:", tabla)
    print("CONTENIDO:")
    print(datos)
    print("==============================")

    if tabla.upper() == "ATTLOG":
        lineas = datos.strip().splitlines()

        for linea in lineas:
            if not linea.strip():
                continue

            campos = linea.split()

            if len(campos) < 2:
                print("Línea ATTLOG inválida:", linea)
                continue

            codigo_empleado = campos[0]
            fecha = campos[1]
            hora = campos[2] if len(campos) > 2 else ""
            fecha_hora = f"{fecha} {hora}"
            tipo_marcaje = campos[3] if len(campos) > 3 else ""
            verificacion = campos[4] if len(campos) > 4 else ""
            estado = campos[5] if len(campos) > 5 else ""

            guardar_asistencia(
                codigo_empleado, fecha_hora, tipo_marcaje,
                estado, verificacion, numero_serie
            )

    elif tabla.upper() == "OPERLOG":
        procesar_operlog(datos)

    return "OK"


@app.route("/iclock/getrequest", methods=["GET"])
def getrequest():
    numero_serie = request.args.get("SN", "DESCONOCIDO")
    comandos = COMANDOS_PENDIENTES.pop(numero_serie, None)

    if comandos:
        respuesta = "\n".join(comandos)
        print(f"ENVIANDO COMANDO A {numero_serie}: {respuesta}")
        return respuesta

    return "OK"


@app.route("/solicitar-usuarios")
@login_requerido
def solicitar_usuarios():
    numero_serie = request.args.get("SN", "")

    if not numero_serie:
        return "Falta el parámetro SN", 400

    comando_id = next(CONTADOR_COMANDOS)
    comando = f"C:{comando_id}:DATA QUERY USERINFO"

    COMANDOS_PENDIENTES.setdefault(numero_serie, []).append(comando)

    print(f"COMANDO ENCOLADO PARA {numero_serie}: {comando}")

    return (
        f"Solicitud enviada al dispositivo {numero_serie}. "
        f"Espera unos segundos y recarga el panel."
    )


# ==========================================
# PANEL WEB (protegido con login)
# ==========================================

@app.route("/")
@login_requerido
def inicio():
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT a.codigo_empleado, a.fecha, a.hora, a.tipo_marcaje,
               a.verificacion, a.sn_dispositivo,
               t.nombres AS nombres_trabajador, t.apellidos AS apellidos_trabajador
        FROM asistencias a
        LEFT JOIN trabajadores t ON t.codigo_empleado = a.codigo_empleado
        ORDER BY a.fecha_hora DESC
        LIMIT 100
    """)
    columnas = [
        "codigo_empleado", "fecha", "hora", "tipo_marcaje", "verificacion",
        "sn_dispositivo", "nombres_trabajador", "apellidos_trabajador"
    ]
    asistencias = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]

    cursor.execute("""
        SELECT DISTINCT sn_dispositivo
        FROM asistencias
        WHERE sn_dispositivo IS NOT NULL AND sn_dispositivo != ''
    """)
    dispositivos = [{"sn_dispositivo": fila[0]} for fila in cursor.fetchall()]

    cursor.execute("SELECT COUNT(*) FROM asistencias")
    total_marcajes = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM trabajadores")
    total_trabajadores = cursor.fetchone()[0]

    fecha_hoy = datetime.now().date()

    cursor.execute(
        "SELECT COUNT(*) FROM asistencias WHERE fecha = %s AND tipo_marcaje = '0'",
        (fecha_hoy,)
    )
    entradas_hoy = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM asistencias WHERE fecha = %s AND tipo_marcaje = '1'",
        (fecha_hoy,)
    )
    salidas_hoy = cursor.fetchone()[0]

    cursor.execute("SELECT fecha_recepcion FROM asistencias ORDER BY id DESC LIMIT 1")
    ultimo_marcaje = cursor.fetchone()

    cursor.close()
    conexion.close()

    return render_template(
        "index.html",
        asistencias=asistencias,
        dispositivos=dispositivos,
        total_marcajes=total_marcajes,
        total_trabajadores=total_trabajadores,
        entradas_hoy=entradas_hoy,
        salidas_hoy=salidas_hoy,
        ultimo_marcaje=(ultimo_marcaje[0] if ultimo_marcaje else "Sin registros")
    )


# ==========================================
# EXPORTAR CSV (protegido con login)
# ==========================================

@app.route("/exportar")
@login_requerido
def exportar():
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT
            a.codigo_empleado,
            t.nombres, t.apellidos,
            a.fecha_hora, a.fecha, a.hora, a.tipo_marcaje,
            a.estado, a.verificacion, a.sn_dispositivo, a.fecha_recepcion
        FROM asistencias a
        LEFT JOIN trabajadores t ON t.codigo_empleado = a.codigo_empleado
        ORDER BY a.fecha_hora DESC
    """)
    asistencias = cursor.fetchall()

    cursor.close()
    conexion.close()

    salida = io.StringIO()
    escritor = csv.writer(salida)

    escritor.writerow([
        "Código empleado", "Nombre completo", "Fecha y hora", "Fecha", "Hora",
        "Tipo de marcaje", "Estado", "Verificación", "Dispositivo", "Fecha recepción"
    ])

    for fila in asistencias:
        (codigo_empleado, nombres, apellidos, fecha_hora, fecha, hora,
         tipo_marcaje, estado, verificacion, sn_dispositivo, fecha_recepcion) = fila

        nombre_completo = " ".join(filter(None, [nombres, apellidos])) or "Sin registrar"

        escritor.writerow([
            codigo_empleado, nombre_completo, fecha_hora, fecha, hora,
            tipo_marcaje, estado, verificacion, sn_dispositivo, fecha_recepcion
        ])

    respuesta = Response(salida.getvalue(), mimetype="text/csv")
    respuesta.headers["Content-Disposition"] = "attachment; filename=asistencias.csv"
    return respuesta


# ==========================================
# INICIO (ejecución local)
# ==========================================
# En Railway (producción) se usa gunicorn a través del Procfile:
#   web: gunicorn app:app
# Este bloque solo corre cuando ejecutas "python app.py" directamente.

if __name__ == "__main__":
    from waitress import serve

    port = int(os.environ.get("PORT", 8080))
    print(f"Sirviendo en http://0.0.0.0:{port} (waitress)")
    serve(app, host="0.0.0.0", port=port)
