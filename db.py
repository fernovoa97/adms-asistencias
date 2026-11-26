# db.py
# Conexión a PostgreSQL y creación / migración de tablas.
# Se ejecuta una sola vez al arrancar la app (ver inicializar_base_datos()).

import os
from datetime import datetime
import psycopg2
from werkzeug.security import generate_password_hash

DATABASE_URL = os.environ.get("DATABASE_URL")

# Tipos de justificacion con los que arranca el panel de asistencia:
# (nombre, color de celda, cuenta como falta). Despues se editan en Ajustes.
TIPOS_JUSTIFICACION_INICIALES = [
    ("Día libre", "#8db4e2", False),
    ("Gestiones en Mina / Viaje", "#d9d2e9", False),
    ("Trabajo remoto", "#fbd5a8", False),
    ("Permiso personal", "#fff4cf", False),
    ("Gestiones fuera de oficina", "#bfeaf9", False),
    ("Falta injustificada", "#f28b82", True),
    ("Descanso médico", "#c7e8d3", False),
]

# Codigos del roster de mina (leyenda del Excel modelo). Categoria: para que
# suman los totales de planilla. Los "sistema" no se pueden borrar ni cambiar
# de codigo: el roster los usa al generar dias o al traer vacaciones,
# descansos medicos y feriados.
CODIGOS_ROSTER_INICIALES = [
    # codigo, nombre, color, color_texto, categoria, sistema
    ("T", "Día trabajado", "#ffff00", "#17202f", "trabajado", True),
    ("OF", "Oficina", "#ffc000", "#17202f", "trabajado", False),
    ("DL", "Días libres (descanso)", "#fbe5d6", "#17202f", "descanso", True),
    ("C", "Coordinaciones o cursos", "#70ad47", "#ffffff", "trabajado", False),
    ("VA", "Vacaciones", "#0d0d0d", "#ff0000", "vacaciones", True),
    ("FE", "Feriado", "#d9d9d9", "#17202f", "descanso", True),
    ("BA", "Bajadas adelantadas", "#e4dfec", "#17202f", "otro", False),
    ("DM", "Descanso médico por otros motivos", "#ddebf7", "#17202f", "descanso_medico", True),
    ("DMC", "Descanso médico por positivo a Covid", "#00b0f0", "#17202f", "descanso_medico", False),
    ("DP", "Descanso por paternidad", "#e2efda", "#17202f", "licencia", False),
    ("F", "Falta", "#ffffff", "#ff0000", "falta", False),
    ("LSG", "Licencia sin goce", "#ffffff", "#ff0000", "licencia", False),
    ("LCG", "Licencia con goce", "#ffffff", "#ff0000", "licencia", False),
    ("LF", "Licencia por fallecimiento familiar directo", "#ffffff", "#ff0000", "licencia", False),
    ("SP", "Suspensión", "#ffffff", "#ff0000", "falta", False),
    ("STB", "Stand-by, a la espera de recibir órdenes", "#ffffff", "#ff0000", "otro", False),
    ("9A", "Abonado al 100% (pago doble)", "#a9d08e", "#17202f", "pago_doble", False),
]

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
        _agregar_columna_si_falta(cursor, "trabajadores", "excluido_asistencia", "BOOLEAN NOT NULL DEFAULT FALSE")
        _agregar_columna_si_falta(cursor, "trabajadores", "telefono_corporativo", "TEXT")
        _agregar_columna_si_falta(cursor, "trabajadores", "estado_civil", "TEXT")
        _agregar_columna_si_falta(cursor, "trabajadores", "tiene_hijos", "BOOLEAN NOT NULL DEFAULT FALSE")
        _agregar_columna_si_falta(cursor, "trabajadores", "cantidad_hijos", "INTEGER")
        _agregar_columna_si_falta(cursor, "trabajadores", "conyuge_nombres", "TEXT")
        _agregar_columna_si_falta(cursor, "trabajadores", "conyuge_dni", "TEXT")
        _agregar_columna_si_falta(cursor, "trabajadores", "contacto_emergencia_nombres", "TEXT")
        _agregar_columna_si_falta(cursor, "trabajadores", "contacto_emergencia_telefono", "TEXT")
        _agregar_columna_si_falta(cursor, "trabajadores", "contacto_emergencia_direccion", "TEXT")

        # Datos del contrato. tiempo_renovacion guarda la opcion elegida
        # ("3 meses", "6 meses", "Anual", "Otro") y tiempo_renovacion_meses
        # su equivalente en meses.
        _agregar_columna_si_falta(cursor, "trabajadores", "tipo_contrato", "TEXT")
        _agregar_columna_si_falta(cursor, "trabajadores", "tiempo_renovacion", "TEXT")
        _agregar_columna_si_falta(cursor, "trabajadores", "tiempo_renovacion_meses", "INTEGER")

        # Direccion separada. La columna "direccion" que ya existia se
        # conserva tal cual y pasa a ser la linea de calle, numero y
        # referencia, asi los textos actuales no se pierden ni se mueven.
        _agregar_columna_si_falta(cursor, "trabajadores", "pais", "TEXT")
        _agregar_columna_si_falta(cursor, "trabajadores", "departamento", "TEXT")
        _agregar_columna_si_falta(cursor, "trabajadores", "provincia", "TEXT")
        _agregar_columna_si_falta(cursor, "trabajadores", "distrito", "TEXT")

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

        # --- Hijos de cada trabajador (para navidad, seguro, etc.) ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trabajadores_hijos (
                id SERIAL PRIMARY KEY,
                trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id) ON DELETE CASCADE,
                nombres_completos TEXT NOT NULL,
                dni TEXT,
                fecha_nacimiento DATE,
                creado_en TIMESTAMP NOT NULL
            )
        """)

        # --- Renovaciones de EMO, activos y EPPs: cada renovacion es una
        # fila nueva, asi se conserva el historial completo ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trabajadores_renovaciones (
                id SERIAL PRIMARY KEY,
                trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id) ON DELETE CASCADE,
                tipo TEXT NOT NULL,
                activo TEXT,
                fecha_renovacion DATE NOT NULL,
                fecha_proxima DATE NOT NULL,
                creado_por TEXT,
                creado_en TIMESTAMP NOT NULL
            )
        """)

        # PDF de sustento de la renovacion. Vive en "documentos": si alguien
        # lo elimina desde la ficha, la renovacion queda sin PDF y se puede
        # volver a subir.
        _agregar_columna_si_falta(
            cursor, "trabajadores_renovaciones", "documento_id",
            "INTEGER REFERENCES documentos(id) ON DELETE SET NULL"
        )

        # --- Catalogo administrable de activos (Laptop, Celular, ...) ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activos_catalogo (
                id SERIAL PRIMARY KEY,
                nombre TEXT NOT NULL UNIQUE,
                creado_en TIMESTAMP NOT NULL
            )
        """)

        cursor.execute("SELECT COUNT(*) FROM activos_catalogo")
        if cursor.fetchone()[0] == 0:
            for nombre_activo in ("Laptop", "Celular"):
                cursor.execute(
                    "INSERT INTO activos_catalogo (nombre, creado_en) VALUES (%s, %s)",
                    (nombre_activo, datetime.now())
                )
            print("CATÁLOGO DE ACTIVOS POR DEFECTO CREADO")

        # --- Seguros de cada colaborador y sus dependientes ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS seguros (
                id SERIAL PRIMARY KEY,
                trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id) ON DELETE CASCADE,
                tipo TEXT NOT NULL,
                fecha_afiliacion DATE NOT NULL,
                creado_por TEXT,
                creado_en TIMESTAMP NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS seguros_dependientes (
                id SERIAL PRIMARY KEY,
                seguro_id INTEGER NOT NULL REFERENCES seguros(id) ON DELETE CASCADE,
                parentesco TEXT NOT NULL,
                nombre_completo TEXT NOT NULL,
                fecha_nacimiento DATE NOT NULL,
                creado_en TIMESTAMP NOT NULL
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

        # --- Documentos de sustento adjuntos a cada periodo de vacaciones ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vacaciones_tomadas_archivos (
                id SERIAL PRIMARY KEY,
                periodo_id INTEGER NOT NULL REFERENCES vacaciones_tomadas(id) ON DELETE CASCADE,
                archivo_nombre TEXT NOT NULL,
                archivo_contenido BYTEA NOT NULL,
                subido_en TIMESTAMP NOT NULL
            )
        """)

        # --- Descansos medicos: periodos (fecha inicio/fin) por trabajador ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS descansos_medicos (
                id SERIAL PRIMARY KEY,
                trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id) ON DELETE CASCADE,
                fecha_inicio DATE NOT NULL,
                fecha_fin DATE NOT NULL,
                dias INTEGER NOT NULL,
                observacion TEXT,
                creado_en TIMESTAMP NOT NULL
            )
        """)

        # --- Documentos de sustento (certificado medico) adjuntos a cada
        # periodo de descanso medico ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS descansos_medicos_archivos (
                id SERIAL PRIMARY KEY,
                periodo_id INTEGER NOT NULL REFERENCES descansos_medicos(id) ON DELETE CASCADE,
                archivo_nombre TEXT NOT NULL,
                archivo_contenido BYTEA NOT NULL,
                subido_en TIMESTAMP NOT NULL
            )
        """)

        # --- Licencias: permisos de unas horas dentro de un dia (ej. medio
        # dia por cita medica), con su documento de sustento ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS licencias (
                id SERIAL PRIMARY KEY,
                trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id) ON DELETE CASCADE,
                fecha DATE NOT NULL,
                hora_inicio TIME NOT NULL,
                hora_fin TIME NOT NULL,
                motivo TEXT,
                creado_en TIMESTAMP NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS licencias_archivos (
                id SERIAL PRIMARY KEY,
                licencia_id INTEGER NOT NULL REFERENCES licencias(id) ON DELETE CASCADE,
                archivo_nombre TEXT NOT NULL,
                archivo_contenido BYTEA NOT NULL,
                subido_en TIMESTAMP NOT NULL
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

        # --- Registro general de contratos. "modulo" separa laborales,
        # inmuebles, seguros, servicios y comerciales. El estado no se guarda:
        # se calcula con las fechas (ver contratos.py) ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contratos (
                id SERIAL PRIMARY KEY,
                numero TEXT NOT NULL UNIQUE,
                modulo TEXT NOT NULL,
                categoria TEXT NOT NULL,
                contraparte_nombre TEXT NOT NULL,
                contraparte_ruc TEXT,
                objeto TEXT NOT NULL,
                fecha_suscripcion DATE,
                inicio_vigencia DATE NOT NULL,
                fin_vigencia DATE,
                importe NUMERIC(14,2),
                moneda TEXT NOT NULL DEFAULT 'PEN',
                responsable TEXT NOT NULL,
                trabajador_id INTEGER REFERENCES trabajadores(id) ON DELETE SET NULL,
                archivo_nombre TEXT,
                archivo_contenido BYTEA,
                fecha_cierre DATE,
                motivo_cierre TEXT,
                cerrado_por TEXT,
                creado_por TEXT,
                creado_en TIMESTAMP NOT NULL
            )
        """)

        # Ampliaciones, modificaciones y renovaciones. Una adenda esta
        # formalizada cuando tiene fecha de firma y PDF; recien ahi su
        # nueva fecha de fin cambia la vigencia del contrato.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contratos_adendas (
                id SERIAL PRIMARY KEY,
                contrato_id INTEGER NOT NULL REFERENCES contratos(id) ON DELETE CASCADE,
                numero INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                fecha_suscripcion DATE,
                nuevo_fin DATE,
                archivo_nombre TEXT,
                archivo_contenido BYTEA,
                creado_por TEXT,
                creado_en TIMESTAMP NOT NULL,
                UNIQUE(contrato_id, numero)
            )
        """)

        # --- Ordenes de compra. El correlativo (ADM-AAAA-C<numero>) se
        # reinicia cada anio; el anio sale de la fecha de la orden. Los
        # importes se guardan ya calculados (ver montos.py) ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ordenes_compra (
                id SERIAL PRIMARY KEY,
                anio INTEGER NOT NULL,
                numero INTEGER NOT NULL,
                fecha DATE NOT NULL,
                proveedor_nombre TEXT NOT NULL,
                proveedor_ruc TEXT NOT NULL,
                proveedor_direccion TEXT,
                moneda TEXT NOT NULL DEFAULT 'PEN',
                forma_pago TEXT,
                autorizado_por TEXT,
                nota TEXT,
                entrega TEXT,
                atencion TEXT,
                observaciones TEXT,
                valor_venta NUMERIC(14,2) NOT NULL,
                igv NUMERIC(14,2) NOT NULL,
                total NUMERIC(14,2) NOT NULL,
                creado_por TEXT,
                creado_en TIMESTAMP NOT NULL,
                actualizado_en TIMESTAMP,
                UNIQUE(anio, numero)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ordenes_compra_items (
                id SERIAL PRIMARY KEY,
                orden_id INTEGER NOT NULL REFERENCES ordenes_compra(id) ON DELETE CASCADE,
                orden INTEGER NOT NULL,
                cantidad NUMERIC(14,3) NOT NULL,
                descripcion TEXT NOT NULL,
                valor_unitario NUMERIC(14,4) NOT NULL,
                total NUMERIC(14,2) NOT NULL
            )
        """)

        # --- Proveedores de las ordenes de compra (uno por RUC). Al crear la
        # tabla se llena con los proveedores de las ordenes ya registradas
        # (sus datos de la ultima orden); solo esa vez, para que un proveedor
        # eliminado a mano no vuelva a aparecer en cada reinicio ---
        cursor.execute("SELECT to_regclass('proveedores') IS NULL")
        proveedores_nueva = cursor.fetchone()[0]
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS proveedores (
                id SERIAL PRIMARY KEY,
                ruc TEXT NOT NULL UNIQUE,
                nombre TEXT NOT NULL,
                direccion TEXT,
                creado_en TIMESTAMP NOT NULL,
                actualizado_en TIMESTAMP
            )
        """)
        if proveedores_nueva:
            cursor.execute("""
                INSERT INTO proveedores (ruc, nombre, direccion, creado_en)
                SELECT DISTINCT ON (proveedor_ruc) proveedor_ruc, proveedor_nombre, proveedor_direccion, creado_en
                FROM ordenes_compra
                ORDER BY proveedor_ruc, creado_en DESC, id DESC
            """)
            if cursor.rowcount:
                print(f"MIGRACIÓN: {cursor.rowcount} proveedores cargados desde las órdenes de compra")

        # --- Sedes (combo administrable, con alerta opcional de inasistencia) ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sedes (
                id SERIAL PRIMARY KEY,
                nombre TEXT NOT NULL UNIQUE,
                alerta_inasistencia BOOLEAN NOT NULL DEFAULT FALSE,
                creado_en TIMESTAMP NOT NULL
            )
        """)
        _agregar_columna_si_falta(cursor, "trabajadores", "sede_id", "INTEGER REFERENCES sedes(id) ON DELETE SET NULL")

        # --- Catalogo administrable de motivos de justificacion ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS motivos_justificacion (
                id SERIAL PRIMARY KEY,
                nombre TEXT NOT NULL UNIQUE,
                creado_en TIMESTAMP NOT NULL
            )
        """)

        cursor.execute("SELECT COUNT(*) FROM motivos_justificacion")
        if cursor.fetchone()[0] == 0:
            motivos_por_defecto = [
                "Cita médica", "Descanso médico", "Permiso personal",
                "Trabajo remoto", "Olvidó marcar", "Gestión interna",
                "Capacitación"
            ]
            for nombre_motivo in motivos_por_defecto:
                cursor.execute(
                    "INSERT INTO motivos_justificacion (nombre, creado_en) VALUES (%s, %s)",
                    (nombre_motivo, datetime.now())
                )
            print("MOTIVOS DE JUSTIFICACIÓN POR DEFECTO CREADOS")

        # El catalogo de motivos pasa a ser tambien el de tipos de
        # justificacion del panel de asistencia. Los colores iniciales se
        # siembran una sola vez (al crear la columna), para no pisar lo que
        # se edite despues en Ajustes.
        sembrar_tipos = not _columna_existe(cursor, "motivos_justificacion", "color")
        _agregar_columna_si_falta(cursor, "motivos_justificacion", "color", "TEXT NOT NULL DEFAULT '#e4e4de'")
        _agregar_columna_si_falta(cursor, "motivos_justificacion", "es_falta", "BOOLEAN NOT NULL DEFAULT FALSE")
        _agregar_columna_si_falta(cursor, "motivos_justificacion", "orden", "INTEGER NOT NULL DEFAULT 100")

        if sembrar_tipos:
            for orden, (nombre_tipo, color, es_falta) in enumerate(TIPOS_JUSTIFICACION_INICIALES, 1):
                cursor.execute("""
                    UPDATE motivos_justificacion SET color = %s, es_falta = %s, orden = %s
                    WHERE LOWER(nombre) = LOWER(%s)
                """, (color, es_falta, orden, nombre_tipo))
                if cursor.rowcount == 0:
                    cursor.execute("""
                        INSERT INTO motivos_justificacion (nombre, color, es_falta, orden, creado_en)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (nombre_tipo, color, es_falta, orden, datetime.now()))

        # Cada justificacion queda enlazada a su tipo. "motivo" se conserva
        # como texto (es lo que ya leen Panel, Resumen e Historial); las
        # justificaciones viejas con texto libre quedan sin tipo y no se
        # pierden.
        vincular_tipos = not _columna_existe(cursor, "ajustes_asistencia", "tipo_id")
        _agregar_columna_si_falta(
            cursor, "ajustes_asistencia", "tipo_id",
            "INTEGER REFERENCES motivos_justificacion(id) ON DELETE SET NULL"
        )
        _agregar_columna_si_falta(cursor, "ajustes_asistencia", "observacion", "TEXT")

        if vincular_tipos:
            cursor.execute("""
                UPDATE ajustes_asistencia a SET tipo_id = m.id
                FROM motivos_justificacion m
                WHERE LOWER(TRIM(a.motivo)) = LOWER(m.nombre)
            """)

        # Quien registro una marcacion manual (NULL = vino del dispositivo).
        _agregar_columna_si_falta(cursor, "asistencias", "registrado_por", "TEXT")

        # --- Configuracion del panel de asistencia (una sola fila) ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS config_asistencia (
                id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
                hora_entrada TIME NOT NULL DEFAULT '08:00:00',
                umbral_semanal_seg INTEGER NOT NULL DEFAULT 5400
            )
        """)
        cursor.execute("INSERT INTO config_asistencia (id) VALUES (1) ON CONFLICT (id) DO NOTHING")

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
        # admin = Administracion (todo el sistema); logistica = solo
        # ordenes de compra. Los usuarios que ya existian quedan como admin.
        _agregar_columna_si_falta(cursor, "usuarios", "rol", "TEXT NOT NULL DEFAULT 'admin'")

        cursor.execute("SELECT COUNT(*) FROM usuarios")
        total_usuarios = cursor.fetchone()[0]

        if total_usuarios == 0:
            cursor.execute(
                "INSERT INTO usuarios (username, password_hash) VALUES (%s, %s)",
                ("admin", generate_password_hash("admin123"))
            )
            print("USUARIO POR DEFECTO CREADO -> usuario: admin / contraseña: admin123")

        _migrar_roster(cursor)

        conexion.commit()
        print("BASE DE DATOS POSTGRESQL INICIALIZADA CORRECTAMENTE")
    except Exception as error:
        conexion.rollback()
        print("ERROR INICIALIZANDO BASE DE DATOS:", error)
        raise
    finally:
        cursor.close()
        conexion.close()

def _migrar_roster(cursor):
    """Tablas del roster de mina: minas, codigos (leyenda), una fila por
    trabajador y mes (sus datos de mina) y un codigo por trabajador y dia."""
    _agregar_columna_si_falta(cursor, "trabajadores", "sexo", "TEXT")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS roster_minas (
            id SERIAL PRIMARY KEY,
            nombre TEXT NOT NULL UNIQUE,
            creado_en TIMESTAMP NOT NULL
        )
    """)

    cursor.execute("SELECT to_regclass('roster_codigos') IS NULL")
    sembrar_codigos = cursor.fetchone()[0]
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS roster_codigos (
            id SERIAL PRIMARY KEY,
            codigo TEXT NOT NULL UNIQUE,
            nombre TEXT NOT NULL,
            color TEXT NOT NULL DEFAULT '#ffffff',
            color_texto TEXT NOT NULL DEFAULT '#17202f',
            categoria TEXT NOT NULL DEFAULT 'otro',
            sistema BOOLEAN NOT NULL DEFAULT FALSE,
            orden INTEGER NOT NULL DEFAULT 100,
            creado_en TIMESTAMP NOT NULL
        )
    """)
    if sembrar_codigos:
        for orden, (codigo, nombre, color, color_texto, categoria, sistema) in enumerate(CODIGOS_ROSTER_INICIALES, 1):
            cursor.execute("""
                INSERT INTO roster_codigos (codigo, nombre, color, color_texto, categoria, sistema, orden, creado_en)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (codigo, nombre, color, color_texto, categoria, sistema, orden, datetime.now()))

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS roster_filas (
            id SERIAL PRIMARY KEY,
            anio INTEGER NOT NULL,
            mes INTEGER NOT NULL,
            trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id) ON DELETE CASCADE,
            mina_id INTEGER REFERENCES roster_minas(id) ON DELETE SET NULL,
            guardia TEXT,
            regimen_trabajo INTEGER,
            regimen_descanso INTEGER,
            inicio_ciclo DATE,
            horas_guardia NUMERIC(4,1) NOT NULL DEFAULT 12,
            condicion TEXT,
            conduce_mina BOOLEAN NOT NULL DEFAULT FALSE,
            residencia TEXT,
            creado_en TIMESTAMP NOT NULL,
            UNIQUE (anio, mes, trabajador_id)
        )
    """)

    # manual = puesto a mano (no lo pisa "Generar por regimen").
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS roster_dias (
            trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id) ON DELETE CASCADE,
            fecha DATE NOT NULL,
            codigo_id INTEGER NOT NULL REFERENCES roster_codigos(id) ON DELETE CASCADE,
            manual BOOLEAN NOT NULL DEFAULT TRUE,
            actualizado_por TEXT,
            actualizado_en TIMESTAMP NOT NULL,
            PRIMARY KEY (trabajador_id, fecha)
        )
    """)
