# descansos_medicos.py
# Modulo de descansos medicos (parecido a Vacaciones, pero por AÑO en vez
# de acumulado continuo desde la fecha de ingreso):
# - Se registra cada periodo de descanso medico con su fecha de inicio y
#   fecha de fin (como viene en el certificado medico); los dias se
#   calculan solos (inclusive ambos extremos).
# - El listado principal muestra el total de dias acumulados en un año
#   especifico (por defecto el actual), con navegacion para ver años
#   anteriores.
# - El detalle de cada trabajador muestra TODOS sus periodos (de
#   cualquier año), para tener el historial completo a la mano.

from datetime import date, datetime

from flask import Blueprint, request, render_template, jsonify, abort, Response

from auth import login_requerido
from db import obtener_conexion

descansos_medicos_bp = Blueprint("descansos_medicos", __name__)

TAMANO_MAXIMO_PDF = 15 * 1024 * 1024  # 15 MB


def _psycopg2_binary(contenido_bytes):
    import psycopg2
    return psycopg2.Binary(contenido_bytes)


def _dias_del_periodo(fecha_inicio, fecha_fin):
    return (fecha_fin - fecha_inicio).days + 1


# ==========================================================
# PAGINAS
# ==========================================================

@descansos_medicos_bp.route("/descansos-medicos")
@login_requerido
def pagina_descansos_medicos():
    return render_template("descansos_medicos.html", active_page="descansos_medicos")


@descansos_medicos_bp.route("/descansos-medicos/<int:trabajador_id>")
@login_requerido
def pagina_descanso_medico_detalle(trabajador_id):
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
    return render_template(
        "descanso_medico_detalle.html", trabajador=trabajador, active_page="descansos_medicos"
    )


# ==========================================================
# API: listado (total del año, para todos los trabajadores activos)
# ==========================================================

@descansos_medicos_bp.route("/api/descansos-medicos")
@login_requerido
def api_listar_descansos_medicos():
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
            SELECT COALESCE(SUM(dias), 0), COUNT(*)
            FROM descansos_medicos
            WHERE trabajador_id = %s AND EXTRACT(YEAR FROM fecha_inicio) = %s
        """, (trabajador_id, anio))
        total_dias, total_periodos = cursor.fetchone()
        resultado.append({
            "id": trabajador_id,
            "nombre": f"{nombres} {apellidos}",
            "totalDias": int(total_dias),
            "totalPeriodos": total_periodos
        })

    cursor.close()
    conexion.close()
    return jsonify({"anio": anio, "trabajadores": resultado})


# ==========================================================
# API: detalle de un trabajador (todos sus periodos, cualquier año)
# ==========================================================

@descansos_medicos_bp.route("/api/descansos-medicos/<int:trabajador_id>")
@login_requerido
def api_detalle_descansos_medicos(trabajador_id):
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
        SELECT id, fecha_inicio, fecha_fin, dias, observacion
        FROM descansos_medicos
        WHERE trabajador_id = %s
        ORDER BY fecha_inicio DESC, id DESC
    """, (trabajador_id,))
    filas_periodos = cursor.fetchall()

    periodos = []
    for periodo_id, fecha_inicio, fecha_fin, dias, observacion in filas_periodos:
        cursor.execute("""
            SELECT id, archivo_nombre
            FROM descansos_medicos_archivos
            WHERE periodo_id = %s
            ORDER BY subido_en
        """, (periodo_id,))
        archivos = [{"id": a[0], "nombre": a[1]} for a in cursor.fetchall()]

        periodos.append({
            "id": periodo_id, "fechaInicio": str(fecha_inicio), "fechaFin": str(fecha_fin),
            "dias": dias, "observacion": observacion or "", "archivos": archivos
        })

    cursor.close()
    conexion.close()

    return jsonify({
        "trabajador": {"id": fila[0], "nombre": f"{fila[1]} {fila[2]}"},
        "periodos": periodos
    })


# ==========================================================
# API: agregar / eliminar un periodo
# ==========================================================

@descansos_medicos_bp.route("/api/descansos-medicos/<int:trabajador_id>/periodos", methods=["POST"])
@login_requerido
def api_agregar_periodo(trabajador_id):
    datos = request.get_json(silent=True) or {}
    fecha_inicio_str = (datos.get("fechaInicio") or "").strip()
    fecha_fin_str = (datos.get("fechaFin") or "").strip()
    observacion = (datos.get("observacion") or "").strip()

    if not fecha_inicio_str or not fecha_fin_str:
        return jsonify({"error": "La fecha de inicio y de fin son obligatorias"}), 400

    try:
        fecha_inicio = datetime.strptime(fecha_inicio_str, "%Y-%m-%d").date()
        fecha_fin = datetime.strptime(fecha_fin_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Las fechas no son válidas"}), 400

    if fecha_fin < fecha_inicio:
        return jsonify({"error": "La fecha de fin no puede ser anterior a la de inicio"}), 400

    dias = _dias_del_periodo(fecha_inicio, fecha_fin)

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT id FROM trabajadores WHERE id = %s", (trabajador_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Trabajador no encontrado"}), 404

        cursor.execute("""
            INSERT INTO descansos_medicos (trabajador_id, fecha_inicio, fecha_fin, dias, observacion, creado_en)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (trabajador_id, fecha_inicio, fecha_fin, dias, observacion, datetime.now()))
        registro_id = cursor.fetchone()[0]
        conexion.commit()
        return jsonify({"ok": True, "id": registro_id, "dias": dias}), 201
    except Exception as error:
        conexion.rollback()
        print("ERROR AGREGANDO DESCANSO MÉDICO:", error)
        return jsonify({"error": "No se pudo guardar el periodo"}), 500
    finally:
        cursor.close()
        conexion.close()


@descansos_medicos_bp.route("/api/descansos-medicos/periodos/<int:registro_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_periodo(registro_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM descansos_medicos WHERE id = %s", (registro_id,))
    eliminado = cursor.rowcount > 0
    conexion.commit()
    cursor.close()
    conexion.close()

    if not eliminado:
        return jsonify({"error": "Registro no encontrado"}), 404
    return jsonify({"ok": True})


# ==========================================================
# API: documentos de sustento por periodo
# ==========================================================

@descansos_medicos_bp.route("/api/descansos-medicos/periodos/<int:periodo_id>/archivos", methods=["POST"])
@login_requerido
def api_subir_archivo_descanso(periodo_id):
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
        cursor.execute("SELECT id FROM descansos_medicos WHERE id = %s", (periodo_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Periodo no encontrado"}), 404

        cursor.execute("""
            INSERT INTO descansos_medicos_archivos (periodo_id, archivo_nombre, archivo_contenido, subido_en)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (periodo_id, archivo.filename, _psycopg2_binary(contenido), datetime.now()))
        archivo_id = cursor.fetchone()[0]
        conexion.commit()
        return jsonify({"ok": True, "id": archivo_id}), 201
    except Exception as error:
        conexion.rollback()
        print("ERROR SUBIENDO SUSTENTO DE DESCANSO MÉDICO:", error)
        return jsonify({"error": "No se pudo subir el archivo"}), 500
    finally:
        cursor.close()
        conexion.close()


@descansos_medicos_bp.route("/api/descansos-medicos/archivos/<int:archivo_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_archivo_descanso(archivo_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM descansos_medicos_archivos WHERE id = %s", (archivo_id,))
    eliminado = cursor.rowcount > 0
    conexion.commit()
    cursor.close()
    conexion.close()

    if not eliminado:
        return jsonify({"error": "Archivo no encontrado"}), 404
    return jsonify({"ok": True})


@descansos_medicos_bp.route("/documentos-descansos-medicos/<int:archivo_id>")
@login_requerido
def servir_archivo_descanso(archivo_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        "SELECT archivo_nombre, archivo_contenido FROM descansos_medicos_archivos WHERE id = %s",
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
