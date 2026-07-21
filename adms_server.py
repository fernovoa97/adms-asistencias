from flask import Flask, request, render_template, Response
import sqlite3
from datetime import datetime
import csv
import io
import os
import itertools

app = Flask(__name__)

# ==========================================
# CONFIGURACIÓN
# ==========================================

DATABASE = "asistencias.db"

# Comandos pendientes de enviar a cada dispositivo (por número de serie).
# Es una estructura simple en memoria: se pierde si reinicias el servidor,
# pero es suficiente para pedirle al huellero que reenvíe sus datos.
COMANDOS_PENDIENTES = {}
CONTADOR_COMANDOS = itertools.count(1)


# ==========================================
# BASE DE DATOS
# ==========================================

def obtener_conexion():
    conexion = sqlite3.connect(DATABASE)
    conexion.row_factory = sqlite3.Row
    return conexion


def inicializar_base_datos():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS asistencias (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            codigo_empleado TEXT NOT NULL,

            fecha_hora TEXT NOT NULL,

            fecha TEXT NOT NULL,

            hora TEXT NOT NULL,

            tipo_marcaje TEXT,

            estado TEXT,

            verificacion TEXT,

            sn_dispositivo TEXT,

            fecha_recepcion TEXT NOT NULL,

            UNIQUE(
                codigo_empleado,
                fecha_hora,
                sn_dispositivo
            )

        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trabajadores (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            codigo_empleado TEXT NOT NULL UNIQUE,

            dni TEXT UNIQUE,

            nombres TEXT NOT NULL,

            apellidos TEXT NOT NULL,

            cargo TEXT,

            estado TEXT DEFAULT 'ACTIVO',

            fecha_registro TEXT NOT NULL

        )
    """)

    conexion.commit()
    conexion.close()


# ==========================================
# GUARDAR ASISTENCIA
# ==========================================

def guardar_asistencia(
    codigo_empleado,
    fecha_hora,
    tipo_marcaje,
    estado,
    verificacion,
    sn_dispositivo
):

    try:

        fecha_hora_obj = datetime.strptime(
            fecha_hora,
            "%Y-%m-%d %H:%M:%S"
        )

        fecha = fecha_hora_obj.strftime("%Y-%m-%d")
        hora = fecha_hora_obj.strftime("%H:%M:%S")

        fecha_recepcion = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        conexion = obtener_conexion()
        cursor = conexion.cursor()

        cursor.execute("""
            INSERT OR IGNORE INTO asistencias (

                codigo_empleado,
                fecha_hora,
                fecha,
                hora,
                tipo_marcaje,
                estado,
                verificacion,
                sn_dispositivo,
                fecha_recepcion

            )

            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)

        """, (

            codigo_empleado,
            fecha_hora,
            fecha,
            hora,
            tipo_marcaje,
            estado,
            verificacion,
            sn_dispositivo,
            fecha_recepcion

        ))

        conexion.commit()

        filas_afectadas = cursor.rowcount

        conexion.close()

        if filas_afectadas > 0:

            print(
                f"ASISTENCIA GUARDADA: "
                f"{codigo_empleado} - "
                f"{fecha_hora}"
            )

        else:

            print(
                f"ASISTENCIA DUPLICADA: "
                f"{codigo_empleado} - "
                f"{fecha_hora}"
            )

    except Exception as error:

        print(
            "ERROR GUARDANDO ASISTENCIA:",
            error
        )


# ==========================================
# GUARDAR / ACTUALIZAR TRABAJADOR
# (llega desde el huellero en la tabla OPERLOG)
# ==========================================

def guardar_trabajador(codigo_empleado, nombre_completo):

    try:

        codigo_empleado = codigo_empleado.strip()
        nombre_completo = nombre_completo.strip()

        if not codigo_empleado:
            return

        # El huellero manda el nombre completo en un solo campo.
        # Lo partimos en "nombres" (primera palabra) y "apellidos"
        # (el resto), de forma simple. Se puede editar luego a mano
        # si quieres separarlo distinto.

        partes = nombre_completo.split(" ", 1)

        nombres = partes[0] if partes and partes[0] else "SIN NOMBRE"

        apellidos = partes[1] if len(partes) > 1 else ""

        fecha_registro = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        conexion = obtener_conexion()
        cursor = conexion.cursor()

        cursor.execute("""
            INSERT INTO trabajadores (
                codigo_empleado,
                nombres,
                apellidos,
                fecha_registro
            )
            VALUES (?, ?, ?, ?)

            ON CONFLICT(codigo_empleado) DO UPDATE SET
                nombres = excluded.nombres,
                apellidos = excluded.apellidos
        """, (
            codigo_empleado,
            nombres,
            apellidos,
            fecha_registro
        ))

        conexion.commit()
        conexion.close()

        print(
            f"TRABAJADOR SINCRONIZADO DESDE HUELLERO: "
            f"{codigo_empleado} - {nombre_completo}"
        )

    except Exception as error:

        print(
            "ERROR GUARDANDO TRABAJADOR:",
            error
        )


def procesar_operlog(datos):

    lineas = datos.strip().splitlines()

    for linea in lineas:

        linea = linea.strip()

        if not linea:
            continue

        # Solo nos interesan las líneas de usuario, con este formato:
        # USER PIN=75069735\tName=JUAN PEREZ\tPri=0\tPasswd=\tCard=\t...

        if not linea.upper().startswith("USER"):
            continue

        campos = linea.split("\t")

        datos_usuario = {}

        for campo in campos:

            campo = campo.strip()

            if campo.upper().startswith("USER "):
                campo = campo[5:]  # quitamos el prefijo "USER "

            if "=" in campo:

                clave, _, valor = campo.partition("=")

                datos_usuario[clave.strip().upper()] = valor.strip()

        pin = datos_usuario.get("PIN")
        nombre = datos_usuario.get("NAME", "")

        if pin:
            guardar_trabajador(pin, nombre)


# ==========================================
# COMUNICACIÓN ADMS
# ==========================================

@app.route(
    "/iclock/cdata",
    methods=["GET", "POST"]
)
def cdata():

    numero_serie = request.args.get(
        "SN",
        "DESCONOCIDO"
    )

    tabla = request.args.get(
        "table",
        ""
    )

    # --------------------------------------
    # GET DE CONFIGURACIÓN DEL DISPOSITIVO
    # --------------------------------------

    if request.method == "GET":

        print(
            f"GET CDATA recibido desde "
            f"{numero_serie}"
        )

        return "OK"


    # --------------------------------------
    # POST DE DATOS
    # --------------------------------------

    datos = request.data.decode(
        errors="ignore"
    )

    print("\n==============================")
    print("DATOS RECIBIDOS DEL HUELLERO")
    print("==============================")
    print("SN:", numero_serie)
    print("TABLA:", tabla)
    print("CONTENIDO:")
    print(datos)
    print("==============================")

    # --------------------------------------
    # MARCAJES DE ASISTENCIA
    # --------------------------------------

    if tabla.upper() == "ATTLOG":

        lineas = datos.strip().splitlines()

        for linea in lineas:

            if not linea.strip():
                continue

            # El dispositivo envía campos separados
            # normalmente por espacios o tabulaciones

            campos = linea.split()

            if len(campos) < 2:

                print(
                    "Línea ATTLOG inválida:",
                    linea
                )

                continue

            codigo_empleado = campos[0]

            fecha = campos[1]

            hora = campos[2] if len(campos) > 2 else ""

            fecha_hora = f"{fecha} {hora}"

            tipo_marcaje = (
                campos[3]
                if len(campos) > 3
                else ""
            )

            verificacion = (
                campos[4]
                if len(campos) > 4
                else ""
            )

            estado = (
                campos[5]
                if len(campos) > 5
                else ""
            )

            guardar_asistencia(

                codigo_empleado=codigo_empleado,

                fecha_hora=fecha_hora,

                tipo_marcaje=tipo_marcaje,

                estado=estado,

                verificacion=verificacion,

                sn_dispositivo=numero_serie

            )

    # --------------------------------------
    # DATOS DE USUARIOS (nombres, PIN, etc.)
    # --------------------------------------

    elif tabla.upper() == "OPERLOG":

        procesar_operlog(datos)

    return "OK"


# ==========================================
# CONSULTAR COMANDOS PENDIENTES
# ==========================================

@app.route(
    "/iclock/getrequest",
    methods=["GET"]
)
def getrequest():

    numero_serie = request.args.get(
        "SN",
        "DESCONOCIDO"
    )

    comandos = COMANDOS_PENDIENTES.pop(numero_serie, None)

    if comandos:

        respuesta = "\n".join(comandos)

        print(
            f"ENVIANDO COMANDO A {numero_serie}: {respuesta}"
        )

        return respuesta

    return "OK"


# ==========================================
# SOLICITAR SINCRONIZACIÓN DE USUARIOS
# ==========================================

@app.route("/solicitar-usuarios")
def solicitar_usuarios():

    numero_serie = request.args.get("SN", "")

    if not numero_serie:
        return "Falta el parámetro SN", 400

    comando_id = next(CONTADOR_COMANDOS)

    comando = f"C:{comando_id}:DATA QUERY USERINFO"

    COMANDOS_PENDIENTES.setdefault(
        numero_serie, []
    ).append(comando)

    print(
        f"COMANDO ENCOLADO PARA {numero_serie}: {comando}"
    )

    return (
        f"Solicitud enviada al dispositivo {numero_serie}. "
        f"Espera unos segundos y recarga el panel."
    )


# ==========================================
# PANEL WEB
# ==========================================

@app.route("/")
def inicio():

    conexion = obtener_conexion()

    asistencias = conexion.execute("""
        SELECT
            a.*,
            t.nombres AS nombres_trabajador,
            t.apellidos AS apellidos_trabajador

        FROM asistencias a

        LEFT JOIN trabajadores t
            ON t.codigo_empleado = a.codigo_empleado

        ORDER BY a.fecha_hora DESC

        LIMIT 100
    """).fetchall()

    dispositivos = conexion.execute("""
        SELECT DISTINCT sn_dispositivo
        FROM asistencias
        WHERE sn_dispositivo IS NOT NULL
          AND sn_dispositivo != ''
    """).fetchall()

    conexion.close()

    return render_template(
        "index.html",
        asistencias=asistencias,
        dispositivos=dispositivos
    )


# ==========================================
# EXPORTAR CSV
# ==========================================

@app.route("/exportar")
def exportar():

    conexion = obtener_conexion()

    asistencias = conexion.execute("""
        SELECT
            a.codigo_empleado,
            t.nombres AS nombres_trabajador,
            t.apellidos AS apellidos_trabajador,
            a.fecha_hora,
            a.fecha,
            a.hora,
            a.tipo_marcaje,
            a.estado,
            a.verificacion,
            a.sn_dispositivo,
            a.fecha_recepcion

        FROM asistencias a

        LEFT JOIN trabajadores t
            ON t.codigo_empleado = a.codigo_empleado

        ORDER BY a.fecha_hora DESC

    """).fetchall()

    conexion.close()

    salida = io.StringIO()

    escritor = csv.writer(
        salida
    )

    escritor.writerow([

        "Código empleado",
        "Nombre completo",
        "Fecha y hora",
        "Fecha",
        "Hora",
        "Tipo de marcaje",
        "Estado",
        "Verificación",
        "Dispositivo",
        "Fecha recepción"

    ])

    for asistencia in asistencias:

        nombre_completo = " ".join(filter(None, [
            asistencia["nombres_trabajador"],
            asistencia["apellidos_trabajador"]
        ])) or "Sin registrar"

        escritor.writerow([

            asistencia["codigo_empleado"],
            nombre_completo,
            asistencia["fecha_hora"],
            asistencia["fecha"],
            asistencia["hora"],
            asistencia["tipo_marcaje"],
            asistencia["estado"],
            asistencia["verificacion"],
            asistencia["sn_dispositivo"],
            asistencia["fecha_recepcion"]

        ])

    respuesta = Response(

        salida.getvalue(),

        mimetype="text/csv"

    )

    respuesta.headers["Content-Disposition"] = (
        "attachment; filename=asistencias.csv"
    )

    return respuesta


# ==========================================
# INICIO
# ==========================================

if __name__ == "__main__":

    inicializar_base_datos()

    port = int(os.environ.get("PORT", 8080))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )