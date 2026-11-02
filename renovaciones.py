# renovaciones.py
# Renovaciones periodicas de cada colaborador: EMO (examen medico
# ocupacional), activos (laptop, celular, etc.) y EPPs.
#
# Cada renovacion es una fila nueva y nunca se modifica, asi queda el
# historial completo (igual que el historial de renovaciones del contrato).
# La vigente es simplemente la ultima registrada.

from datetime import datetime

import psycopg2
from flask import Blueprint, request, jsonify, session

from auth import login_requerido
from db import obtener_conexion
from validaciones import parsear_fecha

renovaciones_bp = Blueprint("renovaciones", __name__)

TIPOS_RENOVACION = ("EMO", "ACTIVO", "EPP")
TAMANO_MAXIMO_PDF = 25 * 1024 * 1024  # 25 MB
CARPETA_EXAMEN_MEDICO = "Examen médico"


def obtener_renovaciones(cursor, worker_id):
    """Historial del colaborador, de la mas reciente a la mas antigua."""
    cursor.execute("""
        SELECT id, tipo, activo, fecha_renovacion, fecha_proxima, creado_por, creado_en,
               documento_id
        FROM trabajadores_renovaciones
        WHERE trabajador_id = %s
        ORDER BY creado_en DESC, id DESC
    """, (worker_id,))

    return [
        {
            "id": fila[0],
            "tipo": fila[1],
            "activo": fila[2],
            "fecha_renovacion": str(fila[3]),
            "fecha_proxima": str(fila[4]),
            "creado_por": fila[5],
            "creado_en": fila[6].strftime("%Y-%m-%d %H:%M"),
            "documento_id": fila[7]
        }
        for fila in cursor.fetchall()
    ]


# ---------------------------------------------------------------------------
# Catalogo de activos (combo administrable: para agregar mas sin tocar codigo)
# ---------------------------------------------------------------------------

@renovaciones_bp.route("/api/activos-catalogo")
@login_requerido
def api_listar_activos():
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT id, nombre FROM activos_catalogo ORDER BY nombre")
    activos = [{"id": f[0], "nombre": f[1]} for f in cursor.fetchall()]
    cursor.close()
    conexion.close()
    return jsonify({"activos": activos})


@renovaciones_bp.route("/api/activos-catalogo", methods=["POST"])
@login_requerido
def api_crear_activo():
    datos = request.get_json(silent=True) or {}
    nombre = (datos.get("nombre") or "").strip()

    if not nombre:
        return jsonify({"error": "El nombre del activo es obligatorio"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute(
            "SELECT id FROM activos_catalogo WHERE LOWER(nombre) = LOWER(%s)", (nombre,)
        )
        if cursor.fetchone():
            return jsonify({"error": "Ya existe un activo con ese nombre"}), 400

        cursor.execute("""
            INSERT INTO activos_catalogo (nombre, creado_en)
            VALUES (%s, %s)
            RETURNING id
        """, (nombre, datetime.now()))
        activo_id = cursor.fetchone()[0]
        conexion.commit()
        return jsonify({"ok": True, "id": activo_id, "nombre": nombre}), 201
    except Exception as error:
        conexion.rollback()
        print("ERROR CREANDO ACTIVO:", error)
        return jsonify({"error": "No se pudo crear el activo"}), 500
    finally:
        cursor.close()
        conexion.close()


# ---------------------------------------------------------------------------
# Registrar una renovacion
# ---------------------------------------------------------------------------

@renovaciones_bp.route("/api/trabajadores/<int:worker_id>/renovaciones", methods=["POST"])
@login_requerido
def api_registrar_renovacion(worker_id):
    datos = request.get_json(silent=True) or {}
    tipo = (datos.get("tipo") or "").strip().upper()
    activo = (datos.get("activo") or "").strip()

    if tipo not in TIPOS_RENOVACION:
        return jsonify({"error": "Tipo de renovación no válido"}), 400

    try:
        fecha_renovacion = parsear_fecha(datos.get("fechaRenovacion"))
        fecha_proxima = parsear_fecha(datos.get("fechaProxima"))
    except ValueError:
        return jsonify({"error": "Las fechas no son válidas"}), 400

    if not fecha_renovacion or not fecha_proxima:
        return jsonify({"error": "Ambas fechas son obligatorias"}), 400

    if fecha_proxima < fecha_renovacion:
        return jsonify({"error": "La próxima fecha no puede ser anterior a la de renovación"}), 400

    if tipo == "ACTIVO" and not activo:
        return jsonify({"error": "Selecciona el activo"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT id FROM trabajadores WHERE id = %s", (worker_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Trabajador no encontrado"}), 404

        if tipo == "ACTIVO":
            cursor.execute(
                "SELECT nombre FROM activos_catalogo WHERE LOWER(nombre) = LOWER(%s)", (activo,)
            )
            fila_activo = cursor.fetchone()
            if not fila_activo:
                return jsonify({"error": "Ese activo no existe en el catálogo"}), 400
            activo = fila_activo[0]
        else:
            activo = None

        cursor.execute("""
            INSERT INTO trabajadores_renovaciones (
                trabajador_id, tipo, activo, fecha_renovacion, fecha_proxima,
                creado_por, creado_en
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            worker_id, tipo, activo, fecha_renovacion, fecha_proxima,
            session.get("username"), datetime.now()
        ))
        renovacion_id = cursor.fetchone()[0]
        conexion.commit()
        return jsonify({"ok": True, "id": renovacion_id}), 201
    except Exception as error:
        conexion.rollback()
        print("ERROR REGISTRANDO RENOVACIÓN:", error)
        return jsonify({"error": "No se pudo guardar la renovación"}), 500
    finally:
        cursor.close()
        conexion.close()


# ---------------------------------------------------------------------------
# PDF del examen medico
# ---------------------------------------------------------------------------

def _carpeta_examen_medico(cursor, worker_id):
    """Devuelve la carpeta "Examen médico" del colaborador, creandola si
    todavia no existe."""
    cursor.execute("""
        SELECT id FROM carpetas_documentos
        WHERE trabajador_id = %s AND LOWER(nombre) = LOWER(%s)
    """, (worker_id, CARPETA_EXAMEN_MEDICO))
    fila = cursor.fetchone()
    if fila:
        return fila[0]

    cursor.execute("""
        INSERT INTO carpetas_documentos (trabajador_id, nombre, creado_en)
        VALUES (%s, %s, %s)
        RETURNING id
    """, (worker_id, CARPETA_EXAMEN_MEDICO, datetime.now()))
    return cursor.fetchone()[0]


@renovaciones_bp.route("/api/renovaciones/<int:renovacion_id>/documento", methods=["POST"])
@login_requerido
def api_subir_pdf_renovacion(renovacion_id):
    archivo = request.files.get("archivo")

    if not archivo or not archivo.filename:
        return jsonify({"error": "No se recibió ningún archivo"}), 400
    if not archivo.filename.lower().endswith(".pdf"):
        return jsonify({"error": "El archivo debe ser un PDF"}), 400

    contenido = archivo.read()
    if len(contenido) > TAMANO_MAXIMO_PDF:
        return jsonify({"error": "El archivo supera los 25MB"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("""
            SELECT trabajador_id, tipo, fecha_proxima, documento_id
            FROM trabajadores_renovaciones
            WHERE id = %s
            FOR UPDATE
        """, (renovacion_id,))
        fila = cursor.fetchone()
        if not fila:
            return jsonify({"error": "Renovación no encontrada"}), 404

        worker_id, tipo, fecha_proxima, documento_id = fila
        if tipo != "EMO":
            return jsonify({"error": "Solo el examen médico admite PDF"}), 400
        if documento_id:
            return jsonify({"error": "Este examen ya tiene un PDF"}), 400

        carpeta_id = _carpeta_examen_medico(cursor, worker_id)
        cursor.execute("""
            INSERT INTO documentos (
                trabajador_id, carpeta_id, nombre, archivo_original,
                tipo_mime, contenido, tamano_bytes, subido_en
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            worker_id, carpeta_id, f"EMO (vence {fecha_proxima})", archivo.filename,
            "application/pdf", psycopg2.Binary(contenido), len(contenido), datetime.now()
        ))
        documento_id = cursor.fetchone()[0]

        cursor.execute(
            "UPDATE trabajadores_renovaciones SET documento_id = %s WHERE id = %s",
            (documento_id, renovacion_id)
        )
        conexion.commit()
        return jsonify({"ok": True, "documentoId": documento_id}), 201
    except Exception as error:
        conexion.rollback()
        print("ERROR SUBIENDO PDF DE RENOVACIÓN:", error)
        return jsonify({"error": "No se pudo subir el PDF"}), 500
    finally:
        cursor.close()
        conexion.close()
