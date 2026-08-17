# vacaciones.py
# Modulo de vacaciones:
# - Acumulado: se calcula solo, 2.5 dias por cada mes completo trabajado
#   desde la fecha de ingreso. Se puede reemplazar por un valor manual si
#   hace falta corregirlo (ej. un trabajador tuvo licencia sin goce que
#   pauso la acumulacion, o se negocio un ajuste puntual).
# - Tomadas: no es un numero suelto editable a mano -- es la suma de un
#   pequeño registro (fecha + cantidad de dias + nota), para poder ver
#   despues CUANDO se tomo cada periodo, no solo un total.
# - Saldo: acumulado - tomadas.

from datetime import date, datetime, timedelta

from flask import Blueprint, request, render_template, jsonify, abort, Response

from auth import login_requerido
from db import obtener_conexion

vacaciones_bp = Blueprint("vacaciones", __name__)

DIAS_POR_MES = 2.5
TAMANO_MAXIMO_PDF = 15 * 1024 * 1024  # 15 MB


def _psycopg2_binary(contenido_bytes):
    import psycopg2
    return psycopg2.Binary(contenido_bytes)


def obtener_rangos_vacaciones(cursor, trabajador_id=None):
    """Convierte cada registro de vacaciones_tomadas (fecha de inicio +
    cantidad de dias) en un rango (fecha_inicio, fecha_fin) inclusive.
    Si se pasa trabajador_id, devuelve solo la lista de rangos de ese
    trabajador; si no, devuelve un diccionario {trabajador_id: [rangos]}
    con los de TODOS los trabajadores (para no hacer una consulta por
    persona cuando se necesita para todos, como en Resumen)."""
    if trabajador_id is not None:
        cursor.execute(
            "SELECT fecha, dias FROM vacaciones_tomadas WHERE trabajador_id = %s",
            (trabajador_id,)
        )
        rangos = []
        for fecha_inicio, dias in cursor.fetchall():
            dias_enteros = max(1, round(float(dias)))
            fecha_fin = fecha_inicio + timedelta(days=dias_enteros - 1)
            rangos.append((fecha_inicio, fecha_fin))
        return rangos

    cursor.execute("SELECT trabajador_id, fecha, dias FROM vacaciones_tomadas")
    mapa = {}
    for t_id, fecha_inicio, dias in cursor.fetchall():
        dias_enteros = max(1, round(float(dias)))
        fecha_fin = fecha_inicio + timedelta(days=dias_enteros - 1)
        mapa.setdefault(t_id, []).append((fecha_inicio, fecha_fin))
    return mapa


def fecha_en_vacaciones(rangos, fecha):
    """rangos: lista de (fecha_inicio, fecha_fin). True si 'fecha' cae
    dentro de alguno de esos rangos (inclusive ambos extremos)."""
    return any(inicio <= fecha <= fin for inicio, fin in rangos)


def _meses_cumplidos(fecha_ingreso, fecha_referencia=None):
    """Cuantos meses COMPLETOS pasaron desde la fecha de ingreso hasta hoy
    (o la fecha de referencia que se le pase). Si el dia del mes actual
    todavia no llega al dia de ingreso, ese mes no cuenta como cumplido."""
    if not fecha_ingreso:
        return 0

    fecha_referencia = fecha_referencia or date.today()
    if fecha_ingreso > fecha_referencia:
        return 0

    meses = (fecha_referencia.year - fecha_ingreso.year) * 12 + (fecha_referencia.month - fecha_ingreso.month)
    if fecha_referencia.day < fecha_ingreso.day:
        meses -= 1

    return max(meses, 0)


def _calcular_vacaciones(cursor, trabajador_id, fecha_ingreso):
    meses = _meses_cumplidos(fecha_ingreso)
    acumulado_automatico = round(meses * DIAS_POR_MES, 2)

    cursor.execute(
        "SELECT dias_acumulados_manual FROM vacaciones_ajustes WHERE trabajador_id = %s",
        (trabajador_id,)
    )
    fila_ajuste = cursor.fetchone()
    ajuste_manual = float(fila_ajuste[0]) if fila_ajuste and fila_ajuste[0] is not None else None

    acumulado = ajuste_manual if ajuste_manual is not None else acumulado_automatico

    cursor.execute(
        "SELECT COALESCE(SUM(dias), 0) FROM vacaciones_tomadas WHERE trabajador_id = %s",
        (trabajador_id,)
    )
    tomadas = float(cursor.fetchone()[0])

    return {
        "mesesCumplidos": meses,
        "acumuladoAutomatico": acumulado_automatico,
        "ajusteManual": ajuste_manual,
        "acumulado": acumulado,
        "tomadas": tomadas,
        "saldo": round(acumulado - tomadas, 2)
    }


# ==========================================================
# PAGINAS
# ==========================================================

@vacaciones_bp.route("/vacaciones")
@login_requerido
def pagina_vacaciones():
    return render_template("vacaciones.html", active_page="vacaciones")


@vacaciones_bp.route("/vacaciones/<int:trabajador_id>")
@login_requerido
def pagina_vacaciones_detalle(trabajador_id):
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
    return render_template("vacaciones_detalle.html", trabajador=trabajador, active_page="vacaciones")


# ==========================================================
# API: listado (resumen de todos los trabajadores activos)
# ==========================================================

@vacaciones_bp.route("/api/vacaciones")
@login_requerido
def api_listar_vacaciones():
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT id, nombres, apellidos, fecha_ingreso
        FROM trabajadores
        WHERE estado IS DISTINCT FROM 'INACTIVO'
        ORDER BY nombres, apellidos
    """)
    filas = cursor.fetchall()

    resultado = []
    for trabajador_id, nombres, apellidos, fecha_ingreso in filas:
        calculo = _calcular_vacaciones(cursor, trabajador_id, fecha_ingreso)
        resultado.append({
            "id": trabajador_id,
            "nombre": f"{nombres} {apellidos}",
            "fechaIngreso": str(fecha_ingreso) if fecha_ingreso else None,
            **calculo
        })

    cursor.close()
    conexion.close()
    return jsonify({"trabajadores": resultado})


# ==========================================================
# API: detalle de un trabajador
# ==========================================================

@vacaciones_bp.route("/api/vacaciones/<int:trabajador_id>")
@login_requerido
def api_detalle_vacaciones(trabajador_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute(
        "SELECT id, nombres, apellidos, fecha_ingreso FROM trabajadores WHERE id = %s",
        (trabajador_id,)
    )
    fila = cursor.fetchone()
    if not fila:
        cursor.close()
        conexion.close()
        return jsonify({"error": "Trabajador no encontrado"}), 404

    _, nombres, apellidos, fecha_ingreso = fila
    calculo = _calcular_vacaciones(cursor, trabajador_id, fecha_ingreso)

    cursor.execute("""
        SELECT id, fecha, dias, observacion
        FROM vacaciones_tomadas
        WHERE trabajador_id = %s
        ORDER BY fecha DESC, id DESC
    """, (trabajador_id,))
    filas_tomadas = cursor.fetchall()

    tomadas_lista = []
    for periodo_id, fecha, dias, observacion in filas_tomadas:
        cursor.execute("""
            SELECT id, archivo_nombre
            FROM vacaciones_tomadas_archivos
            WHERE periodo_id = %s
            ORDER BY subido_en
        """, (periodo_id,))
        archivos = [{"id": a[0], "nombre": a[1]} for a in cursor.fetchall()]

        tomadas_lista.append({
            "id": periodo_id, "fecha": str(fecha), "dias": float(dias),
            "observacion": observacion or "", "archivos": archivos
        })

    cursor.close()
    conexion.close()

    return jsonify({
        "trabajador": {
            "id": trabajador_id,
            "nombre": f"{nombres} {apellidos}",
            "fechaIngreso": str(fecha_ingreso) if fecha_ingreso else None
        },
        "calculo": calculo,
        "tomadas": tomadas_lista
    })


# ==========================================================
# API: ajuste manual del acumulado
# ==========================================================

@vacaciones_bp.route("/api/vacaciones/<int:trabajador_id>/ajuste", methods=["POST"])
@login_requerido
def api_guardar_ajuste(trabajador_id):
    """Si diasAcumuladosManual viene con un numero, ese valor reemplaza al
    calculo automatico. Si viene null/vacio, se borra el ajuste y vuelve a
    calcularse solo desde la fecha de ingreso."""
    datos = request.get_json(silent=True) or {}
    valor = datos.get("diasAcumuladosManual", None)

    if valor is not None:
        try:
            valor = float(valor)
        except (TypeError, ValueError):
            return jsonify({"error": "El ajuste debe ser un número"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("""
            INSERT INTO vacaciones_ajustes (trabajador_id, dias_acumulados_manual, actualizado_en)
            VALUES (%s, %s, %s)
            ON CONFLICT (trabajador_id) DO UPDATE SET
                dias_acumulados_manual = EXCLUDED.dias_acumulados_manual,
                actualizado_en = EXCLUDED.actualizado_en
        """, (trabajador_id, valor, datetime.now()))
        conexion.commit()
        return jsonify({"ok": True})
    except Exception as error:
        conexion.rollback()
        print("ERROR GUARDANDO AJUSTE DE VACACIONES:", error)
        return jsonify({"error": "No se pudo guardar el ajuste"}), 500
    finally:
        cursor.close()
        conexion.close()


# ==========================================================
# API: registro de dias tomados
# ==========================================================

@vacaciones_bp.route("/api/vacaciones/<int:trabajador_id>/tomadas", methods=["POST"])
@login_requerido
def api_agregar_tomada(trabajador_id):
    datos = request.get_json(silent=True) or {}
    fecha = (datos.get("fecha") or "").strip()
    observacion = (datos.get("observacion") or "").strip()

    try:
        dias = float(datos.get("dias"))
    except (TypeError, ValueError):
        return jsonify({"error": "La cantidad de días es obligatoria y debe ser un número"}), 400

    if not fecha:
        return jsonify({"error": "La fecha es obligatoria"}), 400
    if dias <= 0:
        return jsonify({"error": "La cantidad de días debe ser mayor a cero"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT id FROM trabajadores WHERE id = %s", (trabajador_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Trabajador no encontrado"}), 404

        cursor.execute("""
            INSERT INTO vacaciones_tomadas (trabajador_id, fecha, dias, observacion, creado_en)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (trabajador_id, fecha, dias, observacion, datetime.now()))
        registro_id = cursor.fetchone()[0]
        conexion.commit()
        return jsonify({"ok": True, "id": registro_id}), 201
    except Exception as error:
        conexion.rollback()
        print("ERROR AGREGANDO DIAS TOMADOS:", error)
        return jsonify({"error": "No se pudo guardar el registro"}), 500
    finally:
        cursor.close()
        conexion.close()


@vacaciones_bp.route("/api/vacaciones/tomadas/<int:registro_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_tomada(registro_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM vacaciones_tomadas WHERE id = %s", (registro_id,))
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

@vacaciones_bp.route("/api/vacaciones/tomadas/<int:periodo_id>/archivos", methods=["POST"])
@login_requerido
def api_subir_archivo_vacaciones(periodo_id):
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
        cursor.execute("SELECT id FROM vacaciones_tomadas WHERE id = %s", (periodo_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Periodo no encontrado"}), 404

        cursor.execute("""
            INSERT INTO vacaciones_tomadas_archivos (periodo_id, archivo_nombre, archivo_contenido, subido_en)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (periodo_id, archivo.filename, _psycopg2_binary(contenido), datetime.now()))
        archivo_id = cursor.fetchone()[0]
        conexion.commit()
        return jsonify({"ok": True, "id": archivo_id}), 201
    except Exception as error:
        conexion.rollback()
        print("ERROR SUBIENDO SUSTENTO DE VACACIONES:", error)
        return jsonify({"error": "No se pudo subir el archivo"}), 500
    finally:
        cursor.close()
        conexion.close()


@vacaciones_bp.route("/api/vacaciones/archivos/<int:archivo_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_archivo_vacaciones(archivo_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM vacaciones_tomadas_archivos WHERE id = %s", (archivo_id,))
    eliminado = cursor.rowcount > 0
    conexion.commit()
    cursor.close()
    conexion.close()

    if not eliminado:
        return jsonify({"error": "Archivo no encontrado"}), 404
    return jsonify({"ok": True})


@vacaciones_bp.route("/documentos-vacaciones/<int:archivo_id>")
@login_requerido
def servir_archivo_vacaciones(archivo_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        "SELECT archivo_nombre, archivo_contenido FROM vacaciones_tomadas_archivos WHERE id = %s",
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
