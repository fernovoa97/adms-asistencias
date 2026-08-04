# trabajadores.py
# Modulo de administracion de personal: alta de trabajadores, busqueda,
# edicion de datos, actualizacion de contrato, y documentos PDF (guardados
# como bytea directamente en PostgreSQL).

from datetime import datetime
import json

from flask import (
    Blueprint, request, render_template, jsonify, session, Response, abort
)

from auth import login_requerido
from db import obtener_conexion

trabajadores_bp = Blueprint("trabajadores", __name__)

TAMANO_MAXIMO_PDF = 25 * 1024 * 1024  # 25 MB por archivo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fecha_o_none(valor):
    """Convierte '' -> None para que Postgres lo guarde como NULL en columnas DATE."""
    valor = (valor or "").strip()
    return valor if valor else None


def _worker_a_dict(fila_worker, columnas):
    w = dict(zip(columnas, fila_worker))
    for campo in ("fecha_registro", "fecha_ingreso", "fecha_fin_contrato", "fecha_renovacion"):
        if w.get(campo) is not None:
            w[campo] = str(w[campo])
    return w


COLUMNAS_TRABAJADOR = [
    "id", "codigo_empleado", "dni", "nombres", "apellidos", "cargo", "area",
    "estado", "telefono", "email", "fecha_ingreso", "fecha_fin_contrato",
    "fecha_renovacion", "direccion", "observaciones", "historial_renovaciones",
    "fecha_registro"
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


def _obtener_documentos(cursor, worker_id):
    cursor.execute("""
        SELECT id, nombre, archivo_original, tamano_bytes, subido_en
        FROM documentos
        WHERE trabajador_id = %s
        ORDER BY subido_en ASC
    """, (worker_id,))
    columnas = ["id", "nombre", "archivo_original", "tamano_bytes", "subido_en"]
    docs = []
    for fila in cursor.fetchall():
        d = dict(zip(columnas, fila))
        d["subido_en"] = str(d["subido_en"])
        docs.append(d)
    return docs


# ---------------------------------------------------------------------------
# Páginas
# ---------------------------------------------------------------------------

@trabajadores_bp.route("/nuevo-trabajador")
@login_requerido
def pagina_nuevo_trabajador():
    return render_template("nuevo_trabajador.html")


@trabajadores_bp.route("/buscar-trabajador")
@login_requerido
def pagina_buscar_trabajador():
    return render_template("buscar_trabajador.html")


# ---------------------------------------------------------------------------
# API: estadísticas (tarjeta del inicio)
# ---------------------------------------------------------------------------

@trabajadores_bp.route("/api/trabajadores/stats")
@login_requerido
def api_stats():
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT COUNT(*) FROM trabajadores")
    total_trabajadores = cursor.fetchone()[0]
    cursor.close()
    conexion.close()
    return jsonify({"totalTrabajadores": total_trabajadores})


# ---------------------------------------------------------------------------
# API: crear trabajador (con documentos PDF opcionales)
# ---------------------------------------------------------------------------

@trabajadores_bp.route("/api/trabajadores", methods=["POST"])
@login_requerido
def api_crear_trabajador():
    nombres = (request.form.get("nombres") or "").strip()
    apellidos = (request.form.get("apellidos") or "").strip()
    dni = (request.form.get("dni") or "").strip()

    if not nombres or not apellidos or not dni:
        return jsonify({"error": "Nombres, apellidos y DNI son obligatorios"}), 400

    cargo = (request.form.get("cargo") or "").strip()
    area = (request.form.get("area") or "").strip()
    telefono = (request.form.get("telefono") or "").strip()
    email = (request.form.get("email") or "").strip()
    fecha_ingreso = _fecha_o_none(request.form.get("fechaIngreso"))
    fecha_fin_contrato = _fecha_o_none(request.form.get("fechaFinContrato"))
    fecha_renovacion = _fecha_o_none(request.form.get("fechaRenovacion"))
    direccion = (request.form.get("direccion") or "").strip()
    observaciones = (request.form.get("observaciones") or "").strip()

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:
        cursor.execute("SELECT id FROM trabajadores WHERE dni = %s", (dni,))
        if cursor.fetchone():
            return jsonify({"error": "Ya existe un trabajador con ese DNI"}), 400

        cursor.execute("""
            INSERT INTO trabajadores (
                dni, nombres, apellidos, cargo, area, telefono, email,
                fecha_ingreso, fecha_fin_contrato, fecha_renovacion,
                direccion, observaciones, estado, fecha_registro
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVO', %s)
            RETURNING id
        """, (
            dni, nombres, apellidos, cargo, area, telefono, email,
            fecha_ingreso, fecha_fin_contrato, fecha_renovacion,
            direccion, observaciones, datetime.now()
        ))
        worker_id = cursor.fetchone()[0]

        try:
            nombres_docs = json.loads(request.form.get("documentosNombres") or "[]")
        except (ValueError, TypeError):
            nombres_docs = []

        archivos = request.files.getlist("documentos")
        for idx, archivo in enumerate(archivos):
            if not archivo or not archivo.filename:
                continue
            contenido = archivo.read()
            if len(contenido) > TAMANO_MAXIMO_PDF:
                conexion.rollback()
                return jsonify({"error": f'El archivo "{archivo.filename}" supera los 25MB'}), 400

            nombre_doc = (
                nombres_docs[idx].strip()
                if idx < len(nombres_docs) and nombres_docs[idx].strip()
                else archivo.filename
            )

            cursor.execute("""
                INSERT INTO documentos (
                    trabajador_id, nombre, archivo_original, tipo_mime,
                    contenido, tamano_bytes, subido_en
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                worker_id, nombre_doc, archivo.filename,
                archivo.mimetype or "application/pdf",
                psycopg2_binary(contenido), len(contenido), datetime.now()
            ))

        conexion.commit()

        worker = _obtener_worker(cursor, worker_id)
        worker["documentos"] = _obtener_documentos(cursor, worker_id)

        return jsonify({"ok": True, "worker": worker}), 201

    except Exception as error:
        conexion.rollback()
        print("ERROR AL CREAR TRABAJADOR:", error)
        return jsonify({"error": "Error al crear el trabajador"}), 500
    finally:
        cursor.close()
        conexion.close()


def psycopg2_binary(contenido_bytes):
    import psycopg2
    return psycopg2.Binary(contenido_bytes)


# ---------------------------------------------------------------------------
# API: buscar por nombre, apellido o DNI
# ---------------------------------------------------------------------------

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
        SELECT id, nombres, apellidos, dni, cargo, area
        FROM trabajadores
        WHERE (nombres || ' ' || apellidos) ILIKE %s
           OR dni ILIKE %s
           OR codigo_empleado ILIKE %s
        ORDER BY nombres
        LIMIT 50
    """, (patron, patron, patron))

    columnas = ["id", "nombres", "apellidos", "dni", "cargo", "area"]
    resultados = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]

    cursor.close()
    conexion.close()

    return jsonify({"results": resultados})


# ---------------------------------------------------------------------------
# API: detalle de un trabajador (incluye documentos)
# ---------------------------------------------------------------------------

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

    worker["documentos"] = _obtener_documentos(cursor, worker_id)

    cursor.close()
    conexion.close()
    return jsonify({"worker": worker})


# ---------------------------------------------------------------------------
# API: actualizar datos generales de un trabajador
# ---------------------------------------------------------------------------

@trabajadores_bp.route("/api/trabajadores/<int:worker_id>", methods=["PUT"])
@login_requerido
def api_actualizar(worker_id):
    datos = request.get_json(silent=True) or {}

    nombres = (datos.get("nombres") or "").strip()
    apellidos = (datos.get("apellidos") or "").strip()
    dni = (datos.get("dni") or "").strip()

    if not nombres or not apellidos or not dni:
        return jsonify({"error": "Nombres, apellidos y DNI son obligatorios"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:
        cursor.execute(
            "SELECT id FROM trabajadores WHERE dni = %s AND id != %s", (dni, worker_id)
        )
        if cursor.fetchone():
            return jsonify({"error": "Ya existe otro trabajador con ese DNI"}), 400

        cursor.execute("""
            UPDATE trabajadores SET
                nombres = %s, apellidos = %s, dni = %s, cargo = %s, area = %s,
                telefono = %s, email = %s, fecha_ingreso = %s,
                direccion = %s, observaciones = %s
            WHERE id = %s
        """, (
            nombres, apellidos, dni,
            (datos.get("cargo") or "").strip(),
            (datos.get("area") or "").strip(),
            (datos.get("telefono") or "").strip(),
            (datos.get("email") or "").strip(),
            _fecha_o_none(datos.get("fechaIngreso")),
            (datos.get("direccion") or "").strip(),
            (datos.get("observaciones") or "").strip(),
            worker_id
        ))

        if cursor.rowcount == 0:
            conexion.rollback()
            return jsonify({"error": "Trabajador no encontrado"}), 404

        conexion.commit()

        worker = _obtener_worker(cursor, worker_id)
        worker["documentos"] = _obtener_documentos(cursor, worker_id)
        return jsonify({"ok": True, "worker": worker})

    except Exception as error:
        conexion.rollback()
        print("ERROR AL ACTUALIZAR TRABAJADOR:", error)
        return jsonify({"error": "Error al actualizar el trabajador"}), 500
    finally:
        cursor.close()
        conexion.close()


# ---------------------------------------------------------------------------
# API: actualizar fecha de fin de contrato / renovación
# ---------------------------------------------------------------------------

@trabajadores_bp.route("/api/trabajadores/<int:worker_id>/contrato", methods=["PUT"])
@login_requerido
def api_actualizar_contrato(worker_id):
    datos = request.get_json(silent=True) or {}
    fecha_fin_contrato = _fecha_o_none(datos.get("fechaFinContrato"))
    fecha_renovacion = _fecha_o_none(datos.get("fechaRenovacion"))

    if not fecha_fin_contrato:
        return jsonify({"error": "La nueva fecha de fin de contrato es obligatoria"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:
        worker_actual = _obtener_worker(cursor, worker_id)
        if not worker_actual:
            return jsonify({"error": "Trabajador no encontrado"}), 404

        historial = worker_actual.get("historial_renovaciones") or []
        historial.append({
            "fechaFinContratoAnterior": worker_actual.get("fecha_fin_contrato"),
            "fechaFinContratoNueva": fecha_fin_contrato,
            "fechaRenovacion": fecha_renovacion,
            "actualizadoEn": datetime.now().isoformat()
        })

        cursor.execute("""
            UPDATE trabajadores SET
                fecha_fin_contrato = %s,
                fecha_renovacion = %s,
                historial_renovaciones = %s
            WHERE id = %s
        """, (
            fecha_fin_contrato, fecha_renovacion, json.dumps(historial), worker_id
        ))

        conexion.commit()

        worker = _obtener_worker(cursor, worker_id)
        worker["documentos"] = _obtener_documentos(cursor, worker_id)
        return jsonify({"ok": True, "worker": worker})

    except Exception as error:
        conexion.rollback()
        print("ERROR AL ACTUALIZAR CONTRATO:", error)
        return jsonify({"error": "Error al actualizar el contrato"}), 500
    finally:
        cursor.close()
        conexion.close()


# ---------------------------------------------------------------------------
# API: agregar documentos a un trabajador existente
# ---------------------------------------------------------------------------

@trabajadores_bp.route("/api/trabajadores/<int:worker_id>/documentos", methods=["POST"])
@login_requerido
def api_agregar_documentos(worker_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:
        worker_actual = _obtener_worker(cursor, worker_id)
        if not worker_actual:
            return jsonify({"error": "Trabajador no encontrado"}), 404

        try:
            nombres_docs = json.loads(request.form.get("documentosNombres") or "[]")
        except (ValueError, TypeError):
            nombres_docs = []

        archivos = request.files.getlist("documentos")
        if not archivos or all(not a.filename for a in archivos):
            return jsonify({"error": "No se recibió ningún archivo"}), 400

        for idx, archivo in enumerate(archivos):
            if not archivo or not archivo.filename:
                continue
            contenido = archivo.read()
            if len(contenido) > TAMANO_MAXIMO_PDF:
                conexion.rollback()
                return jsonify({"error": f'El archivo "{archivo.filename}" supera los 25MB'}), 400

            nombre_doc = (
                nombres_docs[idx].strip()
                if idx < len(nombres_docs) and nombres_docs[idx].strip()
                else archivo.filename
            )

            cursor.execute("""
                INSERT INTO documentos (
                    trabajador_id, nombre, archivo_original, tipo_mime,
                    contenido, tamano_bytes, subido_en
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                worker_id, nombre_doc, archivo.filename,
                archivo.mimetype or "application/pdf",
                psycopg2_binary(contenido), len(contenido), datetime.now()
            ))

        conexion.commit()

        worker = _obtener_worker(cursor, worker_id)
        worker["documentos"] = _obtener_documentos(cursor, worker_id)
        return jsonify({"ok": True, "worker": worker})

    except Exception as error:
        conexion.rollback()
        print("ERROR AL AGREGAR DOCUMENTOS:", error)
        return jsonify({"error": "Error al agregar documentos"}), 500
    finally:
        cursor.close()
        conexion.close()


# ---------------------------------------------------------------------------
# API: eliminar un documento
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Servir el PDF (protegido por login)
# ---------------------------------------------------------------------------

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
