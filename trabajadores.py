# trabajadores.py
# Modulo de administracion de personal:
# - Alta de trabajadores
# - Busqueda
# - Edicion
# - Contratos
# - Documentos PDF organizados por carpetas (guardados como bytea en la BD)

from datetime import datetime
import json

from flask import (
    Blueprint, request, render_template, jsonify, Response, abort
)

from auth import login_requerido
from db import obtener_conexion

trabajadores_bp = Blueprint("trabajadores", __name__)

TAMANO_MAXIMO_PDF = 25 * 1024 * 1024  # 25 MB


# ==========================================================
# HELPERS
# ==========================================================

def psycopg2_binary(contenido_bytes):
    import psycopg2
    return psycopg2.Binary(contenido_bytes)


def _fecha_o_none(valor):
    valor = (valor or "").strip()
    return valor if valor else None


def _sueldo_o_none(valor):
    valor = (valor or "").strip()
    if not valor:
        return None
    try:
        return float(valor)
    except ValueError:
        return None


def _worker_a_dict(fila, columnas):
    w = dict(zip(columnas, fila))

    for campo in ("fecha_registro", "fecha_ingreso", "fecha_fin_contrato", "fecha_renovacion"):
        if w.get(campo):
            w[campo] = str(w[campo])

    for campo in ("hora_entrada", "hora_salida"):
        if w.get(campo):
            w[campo] = w[campo].strftime("%H:%M")

    # Postgres devuelve NUMERIC como Decimal, que no se puede convertir a
    # JSON directamente -- lo pasamos a float.
    if w.get("sueldo_neto") is not None:
        w["sueldo_neto"] = float(w["sueldo_neto"])

    return w


COLUMNAS_TRABAJADOR = [
    "id", "codigo_empleado", "dni", "nombres", "apellidos", "cargo", "area",
    "estado", "supervisor", "sueldo_neto", "telefono", "email", "fecha_ingreso",
    "fecha_fin_contrato", "fecha_renovacion", "direccion", "observaciones",
    "historial_renovaciones", "hora_entrada", "hora_salida", "fecha_registro"
]


def _obtener_worker(cursor, worker_id):
    cursor.execute(
        f"SELECT {', '.join(COLUMNAS_TRABAJADOR)} FROM trabajadores WHERE id = %s",
        (worker_id,)
    )
    fila = cursor.fetchone()
    if not fila:
        return None
    return _worker_a_dict(fila, COLUMNAS_TRABAJADOR)


def _obtener_carpetas(cursor, worker_id):
    cursor.execute("""
        SELECT id, nombre, creado_en
        FROM carpetas_documentos
        WHERE trabajador_id = %s
        ORDER BY nombre
    """, (worker_id,))

    return [
        {"id": fila[0], "nombre": fila[1], "creado_en": str(fila[2])}
        for fila in cursor.fetchall()
    ]


def _obtener_documentos(cursor, worker_id):
    cursor.execute("""
        SELECT d.id, d.nombre, d.archivo_original, d.tamano_bytes,
               d.subido_en, d.carpeta_id, c.nombre
        FROM documentos d
        LEFT JOIN carpetas_documentos c ON c.id = d.carpeta_id
        WHERE d.trabajador_id = %s
        ORDER BY d.subido_en
    """, (worker_id,))

    documentos = []
    for fila in cursor.fetchall():
        documentos.append({
            "id": fila[0],
            "nombre": fila[1],
            "archivo_original": fila[2],
            "tamano_bytes": fila[3],
            "subido_en": str(fila[4]),
            "carpeta_id": fila[5],
            "carpeta": fila[6] or "Sin carpeta"
        })
    return documentos


def _agregar_datos_completos(cursor, worker):
    worker["documentos"] = _obtener_documentos(cursor, worker["id"])
    worker["carpetas"] = _obtener_carpetas(cursor, worker["id"])
    return worker


def _guardar_documentos(cursor, worker_id, archivos, nombres_docs, carpetas_ids=None):
    """Guarda una lista de archivos subidos como documentos de un trabajador.
    Usada tanto al crear el trabajador como al agregarle mas documentos
    despues. Devuelve None si todo sale bien, o un mensaje de error si algun
    archivo supera el tamano maximo permitido."""
    carpetas_ids = carpetas_ids or []

    for idx, archivo in enumerate(archivos):
        if not archivo or not archivo.filename:
            continue

        contenido = archivo.read()
        if len(contenido) > TAMANO_MAXIMO_PDF:
            return f'El archivo "{archivo.filename}" supera los 25MB'

        nombre_doc = (
            nombres_docs[idx].strip()
            if idx < len(nombres_docs) and nombres_docs[idx].strip()
            else archivo.filename
        )

        carpeta_id = carpetas_ids[idx] if idx < len(carpetas_ids) else None

        cursor.execute("""
            INSERT INTO documentos (
                trabajador_id, carpeta_id, nombre, archivo_original,
                tipo_mime, contenido, tamano_bytes, subido_en
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            worker_id, carpeta_id, nombre_doc, archivo.filename,
            archivo.mimetype or "application/pdf",
            psycopg2_binary(contenido), len(contenido), datetime.now()
        ))

    return None


# ==========================================================
# PAGINAS
# ==========================================================

@trabajadores_bp.route("/nuevo-trabajador")
@login_requerido
def pagina_nuevo_trabajador():
    return render_template("nuevo_trabajador.html")


@trabajadores_bp.route("/buscar-trabajador")
@login_requerido
def pagina_buscar_trabajador():
    return render_template("buscar_trabajador.html")


# ==========================================================
# ESTADISTICAS
# ==========================================================

@trabajadores_bp.route("/api/trabajadores/stats")
@login_requerido
def api_stats():
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT COUNT(*) FROM trabajadores")
    total = cursor.fetchone()[0]
    cursor.close()
    conexion.close()
    return jsonify({"totalTrabajadores": total})


# ==========================================================
# CREAR TRABAJADOR (con documentos PDF opcionales)
# ==========================================================

@trabajadores_bp.route("/api/trabajadores", methods=["POST"])
@login_requerido
def api_crear_trabajador():
    nombres = (request.form.get("nombres") or "").strip()
    apellidos = (request.form.get("apellidos") or "").strip()
    dni = (request.form.get("dni") or "").strip()

    if not nombres or not apellidos or not dni:
        return jsonify({"error": "Nombres, apellidos y DNI son obligatorios"}), 400

    cargo = request.form.get("cargo", "").strip()
    area = request.form.get("area", "").strip()
    supervisor = request.form.get("supervisor", "").strip()
    sueldo_neto = _sueldo_o_none(request.form.get("sueldoNeto"))
    telefono = request.form.get("telefono", "").strip()
    email = request.form.get("email", "").strip()
    fecha_ingreso = _fecha_o_none(request.form.get("fechaIngreso"))
    fecha_fin = _fecha_o_none(request.form.get("fechaFinContrato"))
    fecha_renovacion = _fecha_o_none(request.form.get("fechaRenovacion"))
    direccion = request.form.get("direccion", "").strip()
    observaciones = request.form.get("observaciones", "").strip()

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:
        cursor.execute("SELECT id FROM trabajadores WHERE dni = %s", (dni,))
        if cursor.fetchone():
            return jsonify({"error": "Ya existe un trabajador con ese DNI"}), 400

        cursor.execute("""
            INSERT INTO trabajadores (
                dni, nombres, apellidos, cargo, area, supervisor, sueldo_neto,
                telefono, email, fecha_ingreso, fecha_fin_contrato, fecha_renovacion,
                direccion, observaciones, estado, fecha_registro
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVO', %s)
            RETURNING id
        """, (
            dni, nombres, apellidos, cargo, area, supervisor, sueldo_neto,
            telefono, email, fecha_ingreso, fecha_fin, fecha_renovacion,
            direccion, observaciones, datetime.now()
        ))
        worker_id = cursor.fetchone()[0]

        try:
            nombres_docs = json.loads(request.form.get("documentosNombres") or "[]")
        except (ValueError, TypeError):
            nombres_docs = []

        archivos = request.files.getlist("documentos")
        error_doc = _guardar_documentos(cursor, worker_id, archivos, nombres_docs)
        if error_doc:
            conexion.rollback()
            return jsonify({"error": error_doc}), 400

        conexion.commit()

        worker = _obtener_worker(cursor, worker_id)
        _agregar_datos_completos(cursor, worker)

        return jsonify({"ok": True, "worker": worker}), 201

    except Exception as error:
        conexion.rollback()
        print("ERROR CREANDO TRABAJADOR:", error)
        return jsonify({"error": "Error al crear trabajador"}), 500
    finally:
        cursor.close()
        conexion.close()


# ==========================================================
# BUSCAR TRABAJADOR
# ==========================================================

@trabajadores_bp.route("/api/trabajadores/buscar")
@login_requerido
def api_buscar():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"results": []})

    patron = f"%{q}%"

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("""
        SELECT id, nombres, apellidos, dni, cargo, area, estado
        FROM trabajadores
        WHERE (nombres || ' ' || apellidos) ILIKE %s
           OR dni ILIKE %s
           OR codigo_empleado ILIKE %s
        ORDER BY nombres
        LIMIT 50
    """, (patron, patron, patron))

    resultados = [
        {
            "id": f[0], "nombres": f[1], "apellidos": f[2], "dni": f[3],
            "cargo": f[4], "area": f[5], "estado": f[6] or "ACTIVO"
        }
        for f in cursor.fetchall()
    ]

    cursor.close()
    conexion.close()

    return jsonify({"results": resultados})


# ==========================================================
# CARPETAS DE DOCUMENTOS
# ==========================================================

@trabajadores_bp.route("/api/trabajadores/<int:worker_id>/carpetas", methods=["POST"])
@login_requerido
def api_crear_carpeta(worker_id):
    datos = request.get_json(silent=True) or {}
    nombre = (datos.get("nombre") or "").strip()

    if not nombre:
        return jsonify({"error": "Debe indicar nombre de carpeta"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:
        cursor.execute("SELECT id FROM trabajadores WHERE id = %s", (worker_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Trabajador no encontrado"}), 404

        cursor.execute("""
            INSERT INTO carpetas_documentos (trabajador_id, nombre, creado_en)
            VALUES (%s, %s, %s)
            ON CONFLICT (trabajador_id, nombre) DO NOTHING
            RETURNING id
        """, (worker_id, nombre, datetime.now()))

        fila = cursor.fetchone()
        if not fila:
            return jsonify({"error": "Ya existe una carpeta con ese nombre"}), 400

        conexion.commit()
        return jsonify({"ok": True, "carpeta": {"id": fila[0], "nombre": nombre}}), 201

    except Exception as error:
        conexion.rollback()
        print("ERROR CREANDO CARPETA:", error)
        return jsonify({"error": "No se pudo crear carpeta"}), 500
    finally:
        cursor.close()
        conexion.close()


# ==========================================================
# DETALLE TRABAJADOR
# ==========================================================

@trabajadores_bp.route("/api/trabajadores/<int:worker_id>")
@login_requerido
def api_detalle(worker_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    worker = _obtener_worker(cursor, worker_id)
    if not worker:
        cursor.close()
        conexion.close()
        return jsonify({"error": "Trabajador no encontrado"}), 404

    _agregar_datos_completos(cursor, worker)

    cursor.close()
    conexion.close()
    return jsonify({"worker": worker})


# ==========================================================
# ACTUALIZAR DATOS GENERALES
# ==========================================================

@trabajadores_bp.route("/api/trabajadores/<int:worker_id>", methods=["PUT"])
@login_requerido
def api_actualizar(worker_id):
    datos = request.get_json(silent=True) or {}

    nombres = (datos.get("nombres") or "").strip()
    apellidos = (datos.get("apellidos") or "").strip()
    dni = (datos.get("dni") or "").strip()

    if not nombres or not apellidos or not dni:
        return jsonify({"error": "Nombres, apellidos y DNI son obligatorios"}), 400

    estado = (datos.get("estado") or "ACTIVO").strip().upper()
    if estado not in ("ACTIVO", "INACTIVO"):
        estado = "ACTIVO"

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:
        cursor.execute(
            "SELECT id FROM trabajadores WHERE dni = %s AND id <> %s", (dni, worker_id)
        )
        if cursor.fetchone():
            return jsonify({"error": "DNI ya pertenece a otro trabajador"}), 400

        cursor.execute("""
            UPDATE trabajadores SET
                nombres = %s, apellidos = %s, dni = %s, cargo = %s, area = %s,
                supervisor = %s, sueldo_neto = %s, estado = %s,
                telefono = %s, email = %s, fecha_ingreso = %s,
                direccion = %s, observaciones = %s,
                hora_entrada = %s, hora_salida = %s
            WHERE id = %s
        """, (
            nombres, apellidos, dni,
            (datos.get("cargo") or "").strip(),
            (datos.get("area") or "").strip(),
            (datos.get("supervisor") or "").strip(),
            _sueldo_o_none(datos.get("sueldoNeto")),
            estado,
            (datos.get("telefono") or "").strip(),
            (datos.get("email") or "").strip(),
            _fecha_o_none(datos.get("fechaIngreso")),
            (datos.get("direccion") or "").strip(),
            (datos.get("observaciones") or "").strip(),
            (datos.get("horaEntrada") or "").strip() or None,
            (datos.get("horaSalida") or "").strip() or None,
            worker_id
        ))

        if cursor.rowcount == 0:
            conexion.rollback()
            return jsonify({"error": "Trabajador no encontrado"}), 404

        conexion.commit()

        worker = _obtener_worker(cursor, worker_id)
        _agregar_datos_completos(cursor, worker)

        return jsonify({"ok": True, "worker": worker})

    except Exception as error:
        conexion.rollback()
        print("ERROR ACTUALIZANDO:", error)
        return jsonify({"error": "No se pudo actualizar"}), 500
    finally:
        cursor.close()
        conexion.close()


# ==========================================================
# ACTUALIZAR CONTRATO / RENOVACION
# ==========================================================

@trabajadores_bp.route("/api/trabajadores/<int:worker_id>/contrato", methods=["PUT"])
@login_requerido
def api_actualizar_contrato(worker_id):
    datos = request.get_json(silent=True) or {}
    fecha_fin_contrato = _fecha_o_none(datos.get("fechaFinContrato"))
    fecha_renovacion = _fecha_o_none(datos.get("fechaRenovacion"))

    if not fecha_fin_contrato:
        return jsonify({"error": "La fecha fin de contrato es obligatoria"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:
        trabajador = _obtener_worker(cursor, worker_id)
        if not trabajador:
            return jsonify({"error": "Trabajador no encontrado"}), 404

        historial = trabajador.get("historial_renovaciones") or []
        historial.append({
            "fechaAnterior": trabajador.get("fecha_fin_contrato"),
            "fechaNueva": fecha_fin_contrato,
            "fechaRenovacion": fecha_renovacion,
            "actualizado": datetime.now().isoformat()
        })

        cursor.execute("""
            UPDATE trabajadores SET
                fecha_fin_contrato = %s,
                fecha_renovacion = %s,
                historial_renovaciones = %s
            WHERE id = %s
        """, (fecha_fin_contrato, fecha_renovacion, json.dumps(historial), worker_id))

        conexion.commit()

        worker = _obtener_worker(cursor, worker_id)
        _agregar_datos_completos(cursor, worker)

        return jsonify({"ok": True, "worker": worker})

    except Exception as error:
        conexion.rollback()
        print("ERROR CONTRATO:", error)
        return jsonify({"error": "No se pudo actualizar contrato"}), 500
    finally:
        cursor.close()
        conexion.close()


# ==========================================================
# AGREGAR DOCUMENTOS A TRABAJADOR (con carpeta opcional por archivo)
# ==========================================================

@trabajadores_bp.route("/api/trabajadores/<int:worker_id>/documentos", methods=["POST"])
@login_requerido
def api_agregar_documentos(worker_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:
        trabajador = _obtener_worker(cursor, worker_id)
        if not trabajador:
            return jsonify({"error": "Trabajador no encontrado"}), 404

        try:
            nombres_docs = json.loads(request.form.get("documentosNombres") or "[]")
        except (ValueError, TypeError):
            nombres_docs = []

        try:
            carpetas_ids = json.loads(request.form.get("carpetasIds") or "[]")
        except (ValueError, TypeError):
            carpetas_ids = []

        archivos = request.files.getlist("documentos")
        if not archivos or all(not a.filename for a in archivos):
            return jsonify({"error": "No hay archivos"}), 400

        error_doc = _guardar_documentos(cursor, worker_id, archivos, nombres_docs, carpetas_ids)
        if error_doc:
            conexion.rollback()
            return jsonify({"error": error_doc}), 400

        conexion.commit()

        worker = _obtener_worker(cursor, worker_id)
        _agregar_datos_completos(cursor, worker)

        return jsonify({"ok": True, "worker": worker})

    except Exception as error:
        conexion.rollback()
        print("ERROR SUBIENDO DOCUMENTOS:", error)
        return jsonify({"error": "No se pudieron subir documentos"}), 500
    finally:
        cursor.close()
        conexion.close()


# ==========================================================
# SUBIR VARIOS DOCUMENTOS DIRECTO A UNA CARPETA
# ==========================================================
# A diferencia de /documentos (que puede asignar una carpeta distinta a
# cada archivo via "carpetasIds"), esta ruta es para el caso simple:
# todos los archivos subidos van a la MISMA carpeta.

@trabajadores_bp.route("/api/trabajadores/<int:worker_id>/documentos/carpeta", methods=["POST"])
@login_requerido
def api_subir_documentos_carpeta(worker_id):
    carpeta_id = request.form.get("carpeta_id")

    if not carpeta_id:
        return jsonify({"error": "Seleccione carpeta"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:
        trabajador = _obtener_worker(cursor, worker_id)
        if not trabajador:
            return jsonify({"error": "Trabajador no encontrado"}), 404

        archivos = request.files.getlist("documentos")
        if not archivos or all(not a.filename for a in archivos):
            return jsonify({"error": "No hay archivos"}), 400

        for archivo in archivos:
            if not archivo.filename:
                continue

            contenido = archivo.read()
            if len(contenido) > TAMANO_MAXIMO_PDF:
                conexion.rollback()
                return jsonify({"error": f'El archivo "{archivo.filename}" supera los 25MB'}), 400

            cursor.execute("""
                INSERT INTO documentos (
                    trabajador_id, carpeta_id, nombre, archivo_original,
                    tipo_mime, contenido, tamano_bytes, subido_en
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                worker_id, carpeta_id, archivo.filename, archivo.filename,
                archivo.mimetype or "application/pdf",
                psycopg2_binary(contenido), len(contenido), datetime.now()
            ))

        conexion.commit()

        worker = _obtener_worker(cursor, worker_id)
        _agregar_datos_completos(cursor, worker)

        return jsonify({"ok": True, "worker": worker})

    except Exception as error:
        conexion.rollback()
        print("ERROR SUBIENDO POR CARPETA:", error)
        return jsonify({"error": "Error al subir archivos"}), 500
    finally:
        cursor.close()
        conexion.close()


# ==========================================================
# ELIMINAR UN DOCUMENTO
# ==========================================================

@trabajadores_bp.route(
    "/api/trabajadores/<int:worker_id>/documentos/<int:doc_id>", methods=["DELETE"]
)
@login_requerido
def api_eliminar_documento(worker_id, doc_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute(
        "DELETE FROM documentos WHERE id = %s AND trabajador_id = %s", (doc_id, worker_id)
    )
    eliminado = cursor.rowcount > 0
    conexion.commit()
    cursor.close()
    conexion.close()

    if not eliminado:
        return jsonify({"error": "Documento no encontrado"}), 404
    return jsonify({"ok": True})


# ==========================================================
# SERVIR EL PDF (protegido por login)
# ==========================================================

@trabajadores_bp.route("/documentos/<int:doc_id>")
@login_requerido
def servir_documento(doc_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        "SELECT nombre, tipo_mime, contenido FROM documentos WHERE id = %s", (doc_id,)
    )
    fila = cursor.fetchone()
    cursor.close()
    conexion.close()

    if not fila:
        abort(404)

    nombre, tipo_mime, contenido = fila
    return Response(
        bytes(contenido),
        mimetype=tipo_mime or "application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}.pdf"'}
    )