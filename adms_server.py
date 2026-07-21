from flask import Flask, request, render_template, Response
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import csv
import io
import os
import itertools


app = Flask(__name__)


# ==========================================
# CONFIGURACIÓN
# ==========================================

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:

    raise RuntimeError(
        "No se encontró la variable de entorno DATABASE_URL"
    )


# ==========================================
# COMANDOS PENDIENTES
# ==========================================

# Los comandos se mantienen temporalmente en memoria.
# Si Railway reinicia la aplicación, se pierden.
# Esto no afecta a los datos almacenados en PostgreSQL.

COMANDOS_PENDIENTES = {}

CONTADOR_COMANDOS = itertools.count(1)


# ==========================================
# BASE DE DATOS
# ==========================================

def obtener_conexion():

    return psycopg2.connect(
        DATABASE_URL
    )


def inicializar_base_datos():

    conexion = obtener_conexion()

    cursor = conexion.cursor()

    try:

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS asistencias (

                id SERIAL PRIMARY KEY,

                codigo_empleado TEXT NOT NULL,

                fecha_hora TIMESTAMP NOT NULL,

                fecha DATE NOT NULL,

                hora TIME NOT NULL,

                tipo_marcaje TEXT,

                estado TEXT,

                verificacion TEXT,

                sn_dispositivo TEXT,

                fecha_recepcion TIMESTAMP NOT NULL,

                UNIQUE(
                    codigo_empleado,
                    fecha_hora,
                    sn_dispositivo
                )

            )
        """)


        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trabajadores (

                id SERIAL PRIMARY KEY,

                codigo_empleado TEXT NOT NULL UNIQUE,

                dni TEXT UNIQUE,

                nombres TEXT NOT NULL,

                apellidos TEXT NOT NULL,

                cargo TEXT,

                estado TEXT DEFAULT 'ACTIVO',

                fecha_registro TIMESTAMP NOT NULL

            )
        """)


        conexion.commit()

        print(
            "BASE DE DATOS POSTGRESQL INICIALIZADA CORRECTAMENTE"
        )


    except Exception as error:

        conexion.rollback()

        print(
            "ERROR INICIALIZANDO BASE DE DATOS:",
            error
        )

        raise


    finally:

        cursor.close()

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


        fecha = fecha_hora_obj.date()

        hora = fecha_hora_obj.time()


        fecha_recepcion = datetime.now()


        conexion = obtener_conexion()

        cursor = conexion.cursor()


        cursor.execute("""

            INSERT INTO asistencias (

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

            VALUES (

                %s,

                %s,

                %s,

                %s,

                %s,

                %s,

                %s,

                %s,

                %s

            )

            ON CONFLICT (

                codigo_empleado,

                fecha_hora,

                sn_dispositivo

            )

            DO NOTHING

        """, (

            codigo_empleado,

            fecha_hora_obj,

            fecha,

            hora,

            tipo_marcaje,

            estado,

            verificacion,

            sn_dispositivo,

            fecha_recepcion

        ))


        filas_afectadas = cursor.rowcount


        conexion.commit()


        cursor.close()

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
# ==========================================

def guardar_trabajador(

    codigo_empleado,

    nombre_completo

):

    try:

        codigo_empleado = codigo_empleado.strip()

        nombre_completo = nombre_completo.strip()


        if not codigo_empleado:

            return


        partes = nombre_completo.split(

            " ",

            1

        )


        nombres = (

            partes[0]

            if partes and partes[0]

            else "SIN NOMBRE"

        )


        apellidos = (

            partes[1]

            if len(partes) > 1

            else ""

        )


        fecha_registro = datetime.now()


        conexion = obtener_conexion()

        cursor = conexion.cursor()


        cursor.execute("""

            INSERT INTO trabajadores (

                codigo_empleado,

                nombres,

                apellidos,

                fecha_registro

            )

            VALUES (

                %s,

                %s,

                %s,

                %s

            )

            ON CONFLICT (

                codigo_empleado

            )

            DO UPDATE SET

                nombres = EXCLUDED.nombres,

                apellidos = EXCLUDED.apellidos

        """, (

            codigo_empleado,

            nombres,

            apellidos,

            fecha_registro

        ))


        conexion.commit()


        cursor.close()

        conexion.close()


        print(

            f"TRABAJADOR SINCRONIZADO DESDE HUELLERO: "

            f"{codigo_empleado} - "

            f"{nombre_completo}"

        )


    except Exception as error:

        print(

            "ERROR GUARDANDO TRABAJADOR:",

            error

        )


# ==========================================
# PROCESAR OPERLOG
# ==========================================

def procesar_operlog(datos):

    lineas = datos.strip().splitlines()


    for linea in lineas:

        linea = linea.strip()


        if not linea:

            continue


        if not linea.upper().startswith("USER"):

            continue


        campos = linea.split("\t")


        datos_usuario = {}


        for campo in campos:

            campo = campo.strip()


            if campo.upper().startswith("USER "):

                campo = campo[5:]


            if "=" in campo:

                clave, _, valor = campo.partition("=")


                datos_usuario[

                    clave.strip().upper()

                ] = valor.strip()


        pin = datos_usuario.get(

            "PIN"

        )


        nombre = datos_usuario.get(

            "NAME",

            ""

        )


        if pin:

            guardar_trabajador(

                pin,

                nombre

            )


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


    # ======================================
    # GET
    # ======================================

    if request.method == "GET":

        print(

            f"GET CDATA recibido desde "

            f"{numero_serie}"

        )

        return "OK"


    # ======================================
    # POST
    # ======================================

    datos = request.data.decode(

        errors="ignore"

    )


    print("\n==============================")

    print(

        "DATOS RECIBIDOS DEL HUELLERO"

    )

    print("==============================")

    print(

        "SN:",

        numero_serie

    )

    print(

        "TABLA:",

        tabla

    )

    print(

        "CONTENIDO:"

    )

    print(datos)

    print("==============================")


    # ======================================
    # MARCAJES
    # ======================================

    if tabla.upper() == "ATTLOG":

        lineas = datos.strip().splitlines()


        for linea in lineas:

            if not linea.strip():

                continue


            campos = linea.split()


            if len(campos) < 2:

                print(

                    "Línea ATTLOG inválida:",

                    linea

                )

                continue


            codigo_empleado = campos[0]


            fecha = campos[1]


            hora = (

                campos[2]

                if len(campos) > 2

                else ""

            )


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

                codigo_empleado,

                fecha_hora,

                tipo_marcaje,

                estado,

                verificacion,

                numero_serie

            )


    # ======================================
    # USUARIOS
    # ======================================

    elif tabla.upper() == "OPERLOG":

        procesar_operlog(datos)


    return "OK"


# ==========================================
# CONSULTAR COMANDOS
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


    comandos = COMANDOS_PENDIENTES.pop(

        numero_serie,

        None

    )


    if comandos:

        respuesta = "\n".join(

            comandos

        )


        print(

            f"ENVIANDO COMANDO A "

            f"{numero_serie}: "

            f"{respuesta}"

        )


        return respuesta


    return "OK"


# ==========================================
# SOLICITAR USUARIOS
# ==========================================

@app.route(

    "/solicitar-usuarios"

)

def solicitar_usuarios():

    numero_serie = request.args.get(

        "SN",

        ""

    )


    if not numero_serie:

        return (

            "Falta el parámetro SN",

            400

        )


    comando_id = next(

        CONTADOR_COMANDOS

    )


    comando = (

        f"C:{comando_id}:"

        f"DATA QUERY USERINFO"

    )


    COMANDOS_PENDIENTES.setdefault(

        numero_serie,

        []

    ).append(

        comando

    )


    print(

        f"COMANDO ENCOLADO PARA "

        f"{numero_serie}: "

        f"{comando}"

    )


    return (

        f"Solicitud enviada al dispositivo "

        f"{numero_serie}. "

        f"Espera unos segundos y recarga "

        f"el panel."

    )


# ==========================================
# PANEL WEB
# ==========================================

@app.route("/")

def inicio():

    conexion = obtener_conexion()


    cursor = conexion.cursor(

        cursor_factory=RealDictCursor

    )


    # ======================================
    # ÚLTIMOS MARCAJES
    # ======================================

    cursor.execute("""

        SELECT

            a.*,

            t.nombres

                AS nombres_trabajador,

            t.apellidos

                AS apellidos_trabajador


        FROM asistencias a


        LEFT JOIN trabajadores t

            ON t.codigo_empleado =

               a.codigo_empleado


        ORDER BY a.fecha_hora DESC


        LIMIT 100

    """)


    asistencias = cursor.fetchall()


    # ======================================
    # DISPOSITIVOS
    # ======================================

    cursor.execute("""

        SELECT DISTINCT

            sn_dispositivo


        FROM asistencias


        WHERE sn_dispositivo IS NOT NULL


        AND sn_dispositivo != ''

    """)


    dispositivos = cursor.fetchall()


    # ======================================
    # KPIs
    # ======================================

    cursor.execute("""

        SELECT COUNT(*)

        FROM asistencias

    """)


    total_marcajes = cursor.fetchone()["count"]


    cursor.execute("""

        SELECT COUNT(*)

        FROM trabajadores

    """)


    total_trabajadores = cursor.fetchone()["count"]


    fecha_hoy = datetime.now().date()


    cursor.execute("""

        SELECT COUNT(*)

        FROM asistencias


        WHERE fecha = %s


        AND tipo_marcaje = '0'

    """, (

        fecha_hoy,

    ))


    entradas_hoy = cursor.fetchone()["count"]


    cursor.execute("""

        SELECT COUNT(*)

        FROM asistencias


        WHERE fecha = %s


        AND tipo_marcaje = '1'

    """, (

        fecha_hoy,

    ))


    salidas_hoy = cursor.fetchone()["count"]


    cursor.execute("""

        SELECT fecha_recepcion

        FROM asistencias


        ORDER BY id DESC


        LIMIT 1

    """)


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


        ultimo_marcaje=(

            ultimo_marcaje[

                "fecha_recepcion"

            ]

            if ultimo_marcaje

            else "Sin registros"

        )

    )


# ==========================================
# EXPORTAR CSV
# ==========================================

@app.route(

    "/exportar"

)

def exportar():

    conexion = obtener_conexion()


    cursor = conexion.cursor(

        cursor_factory=RealDictCursor

    )


    cursor.execute("""

        SELECT

            a.codigo_empleado,


            t.nombres

                AS nombres_trabajador,


            t.apellidos

                AS apellidos_trabajador,


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


            ON t.codigo_empleado =

               a.codigo_empleado


        ORDER BY a.fecha_hora DESC

    """)


    asistencias = cursor.fetchall()


    cursor.close()

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


        nombre_completo = " ".join(

            filter(

                None,

                [

                    asistencia[

                        "nombres_trabajador"

                    ],

                    asistencia[

                        "apellidos_trabajador"

                    ]

                ]

            )

        ) or "Sin registrar"


        escritor.writerow([

            asistencia[

                "codigo_empleado"

            ],


            nombre_completo,


            asistencia[

                "fecha_hora"

            ],


            asistencia[

                "fecha"

            ],


            asistencia[

                "hora"

            ],


            asistencia[

                "tipo_marcaje"

            ],


            asistencia[

                "estado"

            ],


            asistencia[

                "verificacion"

            ],


            asistencia[

                "sn_dispositivo"

            ],


            asistencia[

                "fecha_recepcion"

            ]

        ])


    respuesta = Response(

        salida.getvalue(),

        mimetype="text/csv"

    )


    respuesta.headers[

        "Content-Disposition"

    ] = (

        "attachment; "

        "filename=asistencias.csv"

    )


    return respuesta


# ==========================================
# INICIO
# ==========================================

if __name__ == "__main__":

    inicializar_base_datos()


    port = int(

        os.environ.get(

            "PORT",

            8080

        )

    )


    app.run(

        host="0.0.0.0",

        port=port,

        debug=False

    )