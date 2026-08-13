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
        _agregar_columna_si_falta(cursor, "trabajadores", "foto", "BYTEA")
        _agregar_columna_si_falta(cursor, "trabajadores", "foto_mime", "TEXT")

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

        # --- Boletas de pago: periodos, boletas por trabajador, y sus PDFs ---
        # (una boleta puede tener VARIOS archivos PDF adjuntos, por eso los
        # archivos viven en su propia tabla en vez de una columna aca)
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
                correo_destino TEXT,
                estado_envio TEXT NOT NULL DEFAULT 'PENDIENTE',
                error_detalle TEXT,
                enviado_en TIMESTAMP,
                subido_en TIMESTAMP NOT NULL,
                UNIQUE(periodo_id, trabajador_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS boletas_pago_archivos (
                id SERIAL PRIMARY KEY,
                boleta_id INTEGER NOT NULL REFERENCES boletas_pago(id) ON DELETE CASCADE,
                archivo_nombre TEXT NOT NULL,
                archivo_contenido BYTEA NOT NULL,
                subido_en TIMESTAMP NOT NULL
            )
        """)

        # Migracion: las boletas viejas guardaban un solo PDF en la propia
        # fila. Si ese esquema viejo todavia existe, pasamos esos PDFs a la
        # tabla nueva de archivos multiples, y despues quitamos esas
        # columnas de boletas_pago.
        if _columna_existe(cursor, "boletas_pago", "archivo_contenido"):
            cursor.execute("""
                INSERT INTO boletas_pago_archivos (boleta_id, archivo_nombre, archivo_contenido, subido_en)
                SELECT id, archivo_nombre, archivo_contenido, subido_en
                FROM boletas_pago
                WHERE archivo_contenido IS NOT NULL
            """)
            cursor.execute("ALTER TABLE boletas_pago DROP COLUMN archivo_nombre")
            cursor.execute("ALTER TABLE boletas_pago DROP COLUMN archivo_contenido")
            print("MIGRACIÓN: boletas de pago movidas a tabla de archivos múltiples")

        # --- Actas de entrega: control de items entregados (y devueltos) por trabajador ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS actas_entrega (
                id SERIAL PRIMARY KEY,
                nombre TEXT NOT NULL,
                descripcion TEXT,
                creado_por TEXT,
                creado_en TIMESTAMP NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS actas_entrega_items (
                id SERIAL PRIMARY KEY,
                acta_id INTEGER NOT NULL REFERENCES actas_entrega(id) ON DELETE CASCADE,
                nombre TEXT NOT NULL,
                requiere_devolucion BOOLEAN NOT NULL DEFAULT FALSE,
                orden INTEGER NOT NULL DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS actas_entrega_registros (
                id SERIAL PRIMARY KEY,
                item_id INTEGER NOT NULL REFERENCES actas_entrega_items(id) ON DELETE CASCADE,
                trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id) ON DELETE CASCADE,
                entregado BOOLEAN NOT NULL DEFAULT FALSE,
                fecha_entrega DATE,
                fecha_devolucion DATE,
                actualizado_en TIMESTAMP,
                UNIQUE(item_id, trabajador_id)
            )
        """)

        # --- Vacaciones: ajuste manual del acumulado, y registro de dias tomados ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vacaciones_ajustes (
                trabajador_id INTEGER PRIMARY KEY REFERENCES trabajadores(id) ON DELETE CASCADE,
                dias_acumulados_manual NUMERIC(6,2),
                actualizado_en TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vacaciones_tomadas (
                id SERIAL PRIMARY KEY,
                trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id) ON DELETE CASCADE,
                fecha DATE NOT NULL,
                dias NUMERIC(5,2) NOT NULL,
                observacion TEXT,
                creado_en TIMESTAMP NOT NULL
            )
        """)

        # --- Vehiculos de la empresa (propios o alquilados) ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vehiculos (
                id SERIAL PRIMARY KEY,
                placa TEXT NOT NULL UNIQUE,
                marca TEXT,
                modelo TEXT,
                anio INTEGER,
                color TEXT,
                tipo TEXT,
                tipo_adquisicion TEXT NOT NULL DEFAULT 'COMPRA',
                fecha_adquisicion DATE,
                conductor_id INTEGER REFERENCES trabajadores(id) ON DELETE SET NULL,
                estado TEXT NOT NULL DEFAULT 'ACTIVO',
                alquiler_proveedor TEXT,
                alquiler_fecha_fin DATE,
                observaciones TEXT,
                creado_en TIMESTAMP NOT NULL
            )
        """)

        # Documentos del vehiculo (SOAT, revision tecnica, tarjeta de
        # propiedad, etc.) -- el tipo es texto libre a proposito, para no
        # limitar a una lista fija. Cada fila es un documento con su
        # propia fecha de vencimiento, asi se guarda historial (ej. el
        # SOAT del año pasado y el de este año quedan los dos).
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vehiculos_documentos (
                id SERIAL PRIMARY KEY,
                vehiculo_id INTEGER NOT NULL REFERENCES vehiculos(id) ON DELETE CASCADE,
                tipo TEXT NOT NULL,
                fecha_vencimiento DATE,
                archivo_nombre TEXT NOT NULL,
                archivo_contenido BYTEA NOT NULL,
                subido_en TIMESTAMP NOT NULL
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
