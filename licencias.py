# licencias.py
# Modulo de licencias: permisos de UNAS HORAS dentro de un dia (a
# diferencia de Descansos medicos, que son dias completos). Ejemplo tipico:
# licencia de medio dia por cita medica (08:00 a 13:00).
# - Cada licencia tiene fecha, hora de inicio, hora de fin, un motivo
#   opcional, y uno o mas documentos de sustento (PDF).
# - El listado principal muestra el total de HORAS de licencia acumuladas
#   en un año especifico (por defecto el actual), con navegacion para ver
#   años anteriores -- mismo patron que Descansos medicos.

from datetime import date, datetime

from flask import Blueprint, request, render_template, jsonify, abort, Response

from auth import login_requerido
from db import obtener_conexion

licencias_bp = Blueprint("licencias", __name__)

TAMANO_MAXIMO_PDF = 15 * 1024 * 1024  # 15 MB


def _psycopg2_binary(contenido_bytes):
    import psycopg2
    return psycopg2.Binary(contenido_bytes)


def _horas_del_permiso(hora_inicio, hora_fin):
    minutos = (hora_fin.hour * 60 + hora_fin.minute) - (hora_inicio.hour * 60 + hora_inicio.minute)
    return round(minutos / 60, 2)


# ==========================================================
# PAGINAS
# ==========================================================

@licencias_bp.route("/licencias")
@login_requerido
def pagina_licencias():
    return render_template("licencias.html", active_page="licencias")


@licencias_bp.route("/licencias/<int:trabajador_id>")
@login_requerido
def pagina_licencia_detalle(trabajador_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        "SELECT id, nombres, apellidos FROM trabajadores WHERE id = %s", (trabajador_id,)
    )
    fila = cursor.fetchone()
    cursor.close()
    conexion.close()

    if not fila:
        abort(404)

    trabajador = {"id": fila[0], "nombre": f"{fila[1]} {fila[2]}"}
    return render_template("licencia_detalle.html", trabajador=trabajador, active_page="licencias")


# ==========================================================
# API: listado (total de horas del año, para todos los trabajadores activos)
# ==========================================================

@licencias_bp.route("/api/licencias")
@login_requerido
def api_listar_licencias():
    anio = request.args.get("anio", type=int) or date.today().year

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT id, nombres, apellidos
        FROM trabajadores
        WHERE estado IS DISTINCT FROM 'INACTIVO'
        ORDER BY nombres, apellidos
    """)
    trabajadores = cursor.fetchall()

    resultado = []
    for trabajador_id, nombres, apellidos in trabajadores:
        cursor.execute("""
            SELECT hora_inicio, hora_fin
            FROM licencias
            WHERE trabajador_id = %s AND EXTRACT(YEAR FROM fecha) = %s
        """, (trabajador_id, anio))
        filas_permiso = cursor.fetchall()

        total_horas = sum(_horas_del_permiso(hi, hf) for hi, hf in filas_permiso)

        resultado.append({
            "id": trabajador_id,
            "nombre": f"{nombres} {apellidos}",
            "totalHoras": round(total_horas, 2),
            "totalLicencias": len(filas_permiso)
        })

    cursor.close()
    conexion.close()
    return jsonify({"anio": anio, "trabajadores": resultado})


# ==========================================================
# API: detalle de un trabajador (todas sus licencias, cualquier año)
# ==========================================================

@licencias_bp.route("/api/licencias/<int:trabajador_id>")
@login_requerido
def api_detalle_licencias(trabajador_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute(
        "SELECT id, nombres, apellidos FROM trabajadores WHERE id = %s",
        (trabajador_id,)
    )
    fila = cursor.fetchone()
    if not fila:
        cursor.close()
        conexion.close()
        return jsonify({"error": "Trabajador no encontrado"}), 404

    cursor.execute("""
        SELECT id, fecha, hora_inicio, hora_fin, motivo
        FROM licencias
        WHERE trabajador_id = %s
        ORDER BY fecha DESC, hora_inicio DESC, id DESC
    """, (trabajador_id,))
    filas_licencias = cursor.fetchall()

    licencias_lista = []
    for licencia_id, fecha, hora_inicio, hora_fin, motivo in filas_licencias:
        cursor.execute("""
            SELECT id, archivo_nombre
            FROM licencias_archivos
            WHERE licencia_id = %s
            ORDER BY subido_en
        """, (licencia_id,))
        archivos = [{"id": a[0], "nombre": a[1]} for a in cursor.fetchall()]

        licencias_lista.append({
            "id": licencia_id,
            "fecha": str(fecha),
            "horaInicio": hora_inicio.strftime("%H:%M"),
            "horaFin": hora_fin.strftime("%H:%M"),
            "horas": _horas_del_permiso(hora_inicio, hora_fin),
            "motivo": motivo or "",
            "archivos": archivos
        })

    cursor.close()
    conexion.close()

    return jsonify({
        "trabajador": {"id": fila[0], "nombre": f"{fila[1]} {fila[2]}"},
        "licencias": licencias_lista
    })


# ==========================================================
# API: agregar / eliminar una licencia
# ==========================================================

@licencias_bp.route("/api/licencias/<int:trabajador_id>", methods=["POST"])
@login_requerido
def api_agregar_licencia(trabajador_id):
    datos = request.get_json(silent=True) or {}
    fecha_str = (datos.get("fecha") or "").strip()
    hora_inicio_str = (datos.get("horaInicio") or "").strip()
    hora_fin_str = (datos.get("horaFin") or "").strip()
    motivo = (datos.get("motivo") or "").strip()

    if not fecha_str or not hora_inicio_str or not hora_fin_str:
        return jsonify({"error": "La fecha, hora de inicio y hora de fin son obligatorias"}), 400

    try:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        hora_inicio = datetime.strptime(hora_inicio_str, "%H:%M").time()
        hora_fin = datetime.strptime(hora_fin_str, "%H:%M").time()
    except ValueError:
        return jsonify({"error": "La fecha o las horas no son válidas"}), 400

    if hora_fin <= hora_inicio:
        return jsonify({"error": "La hora de fin debe ser posterior a la hora de inicio"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT id FROM trabajadores WHERE id = %s", (trabajador_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Trabajador no encontrado"}), 404

        cursor.execute("""
            INSERT INTO licencias (trabajador_id, fecha, hora_inicio, hora_fin, motivo, creado_en)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (trabajador_id, fecha, hora_inicio, hora_fin, motivo, datetime.now()))
        licencia_id = cursor.fetchone()[0]
        conexion.commit()
        return jsonify({"ok": True, "id": licencia_id, "horas": _horas_del_permiso(hora_inicio, hora_fin)}), 201
    except Exception as error:
        conexion.rollback()
        print("ERROR AGREGANDO LICENCIA:", error)
        return jsonify({"error": "No se pudo guardar la licencia"}), 500
    finally:
        cursor.close()
        conexion.close()


@licencias_bp.route("/api/licencias/registro/<int:licencia_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_licencia(licencia_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM licencias WHERE id = %s", (licencia_id,))
    eliminado = cursor.rowcount > 0
    conexion.commit()
    cursor.close()
    conexion.close()

    if not eliminado:
        return jsonify({"error": "Registro no encontrado"}), 404
    return jsonify({"ok": True})


# ==========================================================
# API: documentos de sustento por licencia
# ==========================================================

@licencias_bp.route("/api/licencias/registro/<int:licencia_id>/archivos", methods=["POST"])
@login_requerido
def api_subir_archivo_licencia(licencia_id):
    archivo = request.files.get("archivo")

    if not archivo or not archivo.filename:
        return jsonify({"error": "No se recibió ningún archivo"}), 400

    if not archivo.filename.lower().endswith(".pdf"):
        return jsonify({"error": "El archivo debe ser un PDF"}), 400

    contenido = archivo.read()
    if len(contenido) > TAMANO_MAXIMO_PDF:
        return jsonify({"error": "El archivo supera los 15MB"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT id FROM licencias WHERE id = %s", (licencia_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Licencia no encontrada"}), 404

        cursor.execute("""
            INSERT INTO licencias_archivos (licencia_id, archivo_nombre, archivo_contenido, subido_en)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (licencia_id, archivo.filename, _psycopg2_binary(contenido), datetime.now()))
        archivo_id = cursor.fetchone()[0]
        conexion.commit()
        return jsonify({"ok": True, "id": archivo_id}), 201
    except Exception as error:
        conexion.rollback()
        print("ERROR SUBIENDO SUSTENTO DE LICENCIA:", error)
        return jsonify({"error": "No se pudo subir el archivo"}), 500
    finally:
        cursor.close()
        conexion.close()


@licencias_bp.route("/api/licencias/archivos/<int:archivo_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_archivo_licencia(archivo_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM licencias_archivos WHERE id = %s", (archivo_id,))
    eliminado = cursor.rowcount > 0
    conexion.commit()
    cursor.close()
    conexion.close()

    if not eliminado:
        return jsonify({"error": "Archivo no encontrado"}), 404
    return jsonify({"ok": True})


@licencias_bp.route("/documentos-licencias/<int:archivo_id>")
@login_requerido
def servir_archivo_licencia(archivo_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        "SELECT archivo_nombre, archivo_contenido FROM licencias_archivos WHERE id = %s",
        (archivo_id,)
    )
    fila = cursor.fetchone()
    cursor.close()
    conexion.close()

    if not fila:
        abort(404)

    nombre, contenido = fila
    return Response(
        bytes(contenido),
        mimetype="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}"'}
    )
