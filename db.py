# db.py
# Conexión a PostgreSQL y creación / migración de tablas.
# Se ejecuta una sola vez al arrancar la app (ver inicializar_base_datos()).

import os
import psycopg2
from werkzeug.security import generate_password_hash

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("No se encontró la variable de entorno DATABASE_URL")


def obtener_conexion():
    return psycopg2.connect(DATABASE_URL)


def _columna_existe(cursor, tabla, columna):
    cursor.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (tabla, columna))
    return cursor.fetchone() is not None


def _agregar_columna_si_falta(cursor, tabla, columna, definicion):
    if not _columna_existe(cursor, tabla, columna):
        cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")
        print(f"MIGRACIÓN: columna '{columna}' agregada a '{tabla}'")


def inicializar_base_datos():
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        # --- Tablas del sistema de asistencias (ya existentes) ---
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
                UNIQUE(codigo_empleado, fecha_hora, sn_dispositivo)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trabajadores (
                id SERIAL PRIMARY KEY,
                codigo_empleado TEXT UNIQUE,
                dni TEXT UNIQUE,
                nombres TEXT NOT NULL,
                apellidos TEXT NOT NULL,
                cargo TEXT,
                estado TEXT DEFAULT 'ACTIVO',
                fecha_registro TIMESTAMP NOT NULL
            )
        """)

        # Si la tabla "trabajadores" ya existia de una version anterior (solo
        # con las columnas del sistema de asistencias), le agregamos las
        # columnas nuevas del modulo de personal sin borrar nada de lo que
        # ya tenia. Tambien relajamos codigo_empleado para que pueda quedar
        # vacio cuando un trabajador se registra primero desde el modulo de
        # personal y todavia no esta enrolado en el biometrico.
        cursor.execute("ALTER TABLE trabajadores ALTER COLUMN codigo_empleado DROP NOT NULL")

        _agregar_columna_si_falta(cursor, "trabajadores", "area", "TEXT")
        _agregar_columna_si_falta(cursor, "trabajadores", "telefono", "TEXT")
        _agregar_columna_si_falta(cursor, "trabajadores", "email", "TEXT")
        _agregar_columna_si_falta(cursor, "trabajadores", "email_corporativo", "TEXT")
        _agregar_columna_si_falta(cursor, "trabajadores", "fecha_ingreso", "DATE")
        _agregar_columna_si_falta(cursor, "trabajadores", "fecha_fin_contrato", "DATE")
        _agregar_columna_si_falta(cursor, "trabajadores", "fecha_renovacion", "DATE")
        _agregar_columna_si_falta(cursor, "trabajadores", "direccion", "TEXT")
        _agregar_columna_si_falta(cursor, "trabajadores", "observaciones", "TEXT")
        _agregar_columna_si_falta(
            cursor, "trabajadores", "historial_renovaciones", "JSONB DEFAULT '[]'::jsonb"
        )
        # Horario personalizado. Si quedan en NULL, el trabajador usa el
        # horario estandar de la empresa (8:00 - 17:00), que se aplica en
        # el codigo, no en la base de datos.
        _agregar_columna_si_falta(cursor, "trabajadores", "hora_entrada", "TIME")
        _agregar_columna_si_falta(cursor, "trabajadores", "hora_salida", "TIME")

        # Supervisor (texto libre, no un vinculo a otro trabajador) y sueldo
        # neto (informacion sensible, solo se muestra en las fichas de
        # personal, nunca en los reportes de asistencia).
        _agregar_columna_si_falta(cursor, "trabajadores", "supervisor", "TEXT")
        _agregar_columna_si_falta(cursor, "trabajadores", "sueldo_neto", "NUMERIC(10,2)")
        _agregar_columna_si_falta(cursor, "trabajadores", "fecha_nacimiento", "DATE")

        # La columna "estado" ya existia desde la version original, pero
        # nunca se expuso en pantalla. Por las dudas, si algun registro
        # viejo quedo con estado en NULL, lo normalizamos a ACTIVO para que
        # no desaparezca de los reportes por accidente.
        cursor.execute("UPDATE trabajadores SET estado = 'ACTIVO' WHERE estado IS NULL")

        # --- Feriados: dias en los que no se espera marcacion normal ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feriados (
                fecha DATE PRIMARY KEY,
                descripcion TEXT,
                creado_en TIMESTAMP NOT NULL
            )
        """)

        # --- Ajustes: justificaciones puntuales de tardanza por trabajador/dia ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ajustes_asistencia (
                id SERIAL PRIMARY KEY,
                trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id) ON DELETE CASCADE,
                fecha DATE NOT NULL,
                motivo TEXT NOT NULL,
                creado_por TEXT,
                creado_en TIMESTAMP NOT NULL,
                UNIQUE(trabajador_id, fecha)
            )
        """)

        # --- Documentos (PDFs) de cada trabajador, guardados en la propia BD ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documentos (
                id SERIAL PRIMARY KEY,
                trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id) ON DELETE CASCADE,
                nombre TEXT NOT NULL,
                archivo_original TEXT,
                tipo_mime TEXT DEFAULT 'application/pdf',
                contenido BYTEA NOT NULL,
                tamano_bytes INTEGER,
                subido_en TIMESTAMP NOT NULL
            )
        """)

        # --- Carpetas para organizar los documentos de cada trabajador ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS carpetas_documentos (
                id SERIAL PRIMARY KEY,
                trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id) ON DELETE CASCADE,
                nombre TEXT NOT NULL,
                creado_en TIMESTAMP NOT NULL,
                UNIQUE(trabajador_id, nombre)
            )
        """)

        # Si "documentos" ya existia sin la columna de carpeta, se la
        # agregamos. Un documento sin carpeta_id simplemente queda
        # clasificado como "Sin carpeta" en la app.
        _agregar_columna_si_falta(
            cursor, "documentos", "carpeta_id",
            "INTEGER REFERENCES carpetas_documentos(id) ON DELETE SET NULL"
        )

        # --- Token OAuth de Microsoft (para enviar boletas via Graph) ---
        # Una sola fila (id=1 siempre): la cuenta de correo de administracion
        # es compartida por todo el sistema, no hay tokens por usuario.
        # Nunca se guarda la contraseña ni el MFA -- solo lo que Microsoft
        # entrega al final del login (access_token/refresh_token).
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS microsoft_oauth_token (
                id INTEGER PRIMARY KEY DEFAULT 1,
                access_token TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                cuenta_correo TEXT,
                expira_en TIMESTAMP NOT NULL,
                actualizado_en TIMESTAMP NOT NULL,
                CHECK (id = 1)
            )
        """)

        # --- Boletas de pago: periodos y archivos por trabajador ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS periodos_pago (
                id SERIAL PRIMARY KEY,
                nombre TEXT NOT NULL,
                creado_por TEXT,
                creado_en TIMESTAMP NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS boletas_pago (
                id SERIAL PRIMARY KEY,
                periodo_id INTEGER NOT NULL REFERENCES periodos_pago(id) ON DELETE CASCADE,
                trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id) ON DELETE CASCADE,
                archivo_nombre TEXT NOT NULL,
                archivo_contenido BYTEA NOT NULL,
                correo_destino TEXT,
                estado_envio TEXT NOT NULL DEFAULT 'PENDIENTE',
                error_detalle TEXT,
                enviado_en TIMESTAMP,
                subido_en TIMESTAMP NOT NULL,
                UNIQUE(periodo_id, trabajador_id)
            )
        """)

        # --- Eventos del calendario de la empresa ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS eventos (
                id SERIAL PRIMARY KEY,
                titulo TEXT NOT NULL,
                descripcion TEXT,
                fecha DATE NOT NULL,
                hora TIME,
                color TEXT DEFAULT '#133984',
                creado_por TEXT,
                creado_en TIMESTAMP NOT NULL
            )
        """)

        # --- Periodos de pago y boletas (PDF enviados por correo) ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS periodos_pago (
                id SERIAL PRIMARY KEY,
                nombre TEXT NOT NULL,
                asunto TEXT NOT NULL,
                mensaje TEXT NOT NULL,
                creado_por TEXT,
                creado_en TIMESTAMP NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS boletas_pago (
                id SERIAL PRIMARY KEY,
                periodo_id INTEGER NOT NULL REFERENCES periodos_pago(id) ON DELETE CASCADE,
                trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id) ON DELETE CASCADE,
                archivo_original TEXT,
                contenido BYTEA NOT NULL,
                tamano_bytes INTEGER,
                correo_destino TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'PENDIENTE',
                mensaje_error TEXT,
                enviado_en TIMESTAMP,
                subido_en TIMESTAMP NOT NULL,
                UNIQUE(periodo_id, trabajador_id)
            )
        """)

        # --- Usuarios del sistema (login) ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            )
        """)

        cursor.execute("SELECT COUNT(*) FROM usuarios")
        total_usuarios = cursor.fetchone()[0]

        if total_usuarios == 0:
            cursor.execute(
                "INSERT INTO usuarios (username, password_hash) VALUES (%s, %s)",
                ("admin", generate_password_hash("admin123"))
            )
            print("USUARIO POR DEFECTO CREADO -> usuario: admin / contraseña: admin123")

        conexion.commit()
        print("BASE DE DATOS POSTGRESQL INICIALIZADA CORRECTAMENTE")
    except Exception as error:
        conexion.rollback()
        print("ERROR INICIALIZANDO BASE DE DATOS:", error)
        raise
    finally:
        cursor.close()
        conexion.close()
