# ajustes.py
# Modulo de Ajustes: feriados (aplican a todos) y justificaciones de
# tardanza (por trabajador y fecha especifica), y configuracion del panel de
# asistencia (hora de entrada, umbral y tipos de justificacion con su color).

import re
from datetime import datetime, timedelta

from flask import Blueprint, request, render_template, jsonify, session

from auth import login_requerido
from db import obtener_conexion
from reglas_asistencia import formatear_hms

ajustes_bp = Blueprint("ajustes", __name__)

COLOR_POR_DEFECTO = "#e4e4de"


def obtener_config_asistencia(cursor):
    """Configuracion vigente del panel de asistencia."""
    cursor.execute("SELECT hora_entrada, umbral_semanal_seg FROM config_asistencia WHERE id = 1")
    hora_entrada, umbral = cursor.fetchone()
    return {"hora_entrada": hora_entrada, "umbral_semanal_seg": umbral}


def _color_valido(color):
    return isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color) is not None


@ajustes_bp.route("/ajustes")
@login_requerido
def pagina_ajustes():
    return render_template("ajustes.html", active_page="ajustes")


# ---------------------------------------------------------------------------
# Configuracion del panel de asistencia
# ---------------------------------------------------------------------------

@ajustes_bp.route("/api/asistencia/config")
@login_requerido
def api_obtener_config_asistencia():
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    config = obtener_config_asistencia(cursor)
    cursor.close()
    conexion.close()
    return jsonify({
        "horaEntrada": config["hora_entrada"].strftime("%H:%M:%S"),
        "umbralSemanal": formatear_hms(config["umbral_semanal_seg"])
    })


@ajustes_bp.route("/api/asistencia/config", methods=["PUT"])
@login_requerido
def api_guardar_config_asistencia():
    datos = request.get_json(silent=True) or {}

    try:
        hora_entrada = datetime.strptime((datos.get("horaEntrada") or "").strip(), "%H:%M:%S").time()
        umbral = datetime.strptime((datos.get("umbralSemanal") or "").strip(), "%H:%M:%S").time()
    except ValueError:
        return jsonify({"error": "Usa el formato hh:mm:ss en la hora de entrada y el umbral"}), 400

    umbral_seg = umbral.hour * 3600 + umbral.minute * 60 + umbral.second

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        "UPDATE config_asistencia SET hora_entrada = %s, umbral_semanal_seg = %s WHERE id = 1",
        (hora_entrada, umbral_seg)
    )
    conexion.commit()
    cursor.close()
    conexion.close()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Feriados
# ---------------------------------------------------------------------------

@ajustes_bp.route("/api/feriados", methods=["GET"])
@login_requerido
def api_listar_feriados():
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT fecha, descripcion FROM feriados ORDER BY fecha DESC")
    feriados = [{"fecha": str(f[0]), "descripcion": f[1]} for f in cursor.fetchall()]
    cursor.close()
    conexion.close()
    return jsonify({"feriados": feriados})


@ajustes_bp.route("/api/feriados", methods=["POST"])
@login_requerido
def api_crear_feriado():
    datos = request.get_json(silent=True) or {}
    fecha = (datos.get("fecha") or "").strip()
    descripcion = (datos.get("descripcion") or "").strip()

    if not fecha:
        return jsonify({"error": "La fecha es obligatoria"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("""
            INSERT INTO feriados (fecha, descripcion, creado_en)
            VALUES (%s, %s, %s)
            ON CONFLICT (fecha) DO UPDATE SET descripcion = EXCLUDED.descripcion
        """, (fecha, descripcion, datetime.now()))
        conexion.commit()
        return jsonify({"ok": True})
    except Exception as error:
        conexion.rollback()
        print("ERROR AL CREAR FERIADO:", error)
        return jsonify({"error": "No se pudo guardar el feriado"}), 500
    finally:
        cursor.close()
        conexion.close()


@ajustes_bp.route("/api/feriados/<fecha>", methods=["DELETE"])
@login_requerido
def api_eliminar_feriado(fecha):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM feriados WHERE fecha = %s", (fecha,))
    eliminado = cursor.rowcount > 0
    conexion.commit()
    cursor.close()
    conexion.close()

    if not eliminado:
        return jsonify({"error": "Feriado no encontrado"}), 404
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Catalogo de motivos / tipos de justificacion (combo administrable)
# ---------------------------------------------------------------------------

@ajustes_bp.route("/api/motivos-justificacion")
@login_requerido
def api_listar_motivos():
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("""
        SELECT id, nombre, color, es_falta FROM motivos_justificacion
        ORDER BY orden, nombre
    """)
    motivos = [
        {"id": f[0], "nombre": f[1], "color": f[2], "esFalta": f[3]}
        for f in cursor.fetchall()
    ]
    cursor.close()
    conexion.close()
    return jsonify({"motivos": motivos})


@ajustes_bp.route("/api/motivos-justificacion", methods=["POST"])
@login_requerido
def api_crear_motivo():
    datos = request.get_json(silent=True) or {}
    nombre = (datos.get("nombre") or "").strip()
    color = datos.get("color", COLOR_POR_DEFECTO)
    es_falta = datos.get("esFalta") is True

    if not nombre:
        return jsonify({"error": "El nombre del motivo es obligatorio"}), 400
    if not _color_valido(color):
        return jsonify({"error": "El color no es válido"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT id FROM motivos_justificacion WHERE LOWER(nombre) = LOWER(%s)", (nombre,))
        if cursor.fetchone():
            return jsonify({"error": "Ya existe un motivo con ese nombre"}), 400

        cursor.execute("""
            INSERT INTO motivos_justificacion (nombre, color, es_falta, creado_en)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (nombre, color, es_falta, datetime.now()))
        motivo_id = cursor.fetchone()[0]
        conexion.commit()
        return jsonify({"ok": True, "id": motivo_id, "nombre": nombre}), 201
    except Exception as error:
        conexion.rollback()
        print("ERROR CREANDO MOTIVO:", error)
        return jsonify({"error": "No se pudo crear el motivo"}), 500
    finally:
        cursor.close()
        conexion.close()


@ajustes_bp.route("/api/motivos-justificacion/<int:motivo_id>", methods=["PUT"])
@login_requerido
def api_editar_motivo(motivo_id):
    datos = request.get_json(silent=True) or {}
    nombre = (datos.get("nombre") or "").strip()
    color = datos.get("color")
    es_falta = datos.get("esFalta") is True

    if not nombre:
        return jsonify({"error": "El nombre es obligatorio"}), 400
    if not _color_valido(color):
        return jsonify({"error": "El color no es válido"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute(
            "SELECT 1 FROM motivos_justificacion WHERE LOWER(nombre) = LOWER(%s) AND id <> %s",
            (nombre, motivo_id)
        )
        if cursor.fetchone():
            return jsonify({"error": "Ya existe un tipo con ese nombre"}), 400

        cursor.execute(
            "UPDATE motivos_justificacion SET nombre = %s, color = %s, es_falta = %s WHERE id = %s",
            (nombre, color, es_falta, motivo_id)
        )
        if cursor.rowcount == 0:
            return jsonify({"error": "Tipo no encontrado"}), 404

        # Las justificaciones guardan el nombre como texto: si no se
        # actualiza aqui, seguirian mostrando el nombre anterior.
        cursor.execute(
            "UPDATE ajustes_asistencia SET motivo = %s WHERE tipo_id = %s",
            (nombre, motivo_id)
        )
        conexion.commit()
        return jsonify({"ok": True})
    except Exception as error:
        conexion.rollback()
        print("ERROR EDITANDO MOTIVO:", error)
        return jsonify({"error": "No se pudo guardar el tipo"}), 500
    finally:
        cursor.close()
        conexion.close()


@ajustes_bp.route("/api/motivos-justificacion/<int:motivo_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_motivo(motivo_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM ajustes_asistencia WHERE tipo_id = %s", (motivo_id,))
        en_uso = cursor.fetchone()[0]
        if en_uso:
            return jsonify({
                "error": f"No se puede eliminar: lo usan {en_uso} justificación(es). Puedes renombrarlo."
            }), 409

        cursor.execute("DELETE FROM motivos_justificacion WHERE id = %s", (motivo_id,))
        if cursor.rowcount == 0:
            return jsonify({"error": "Tipo no encontrado"}), 404
        conexion.commit()
        return jsonify({"ok": True})
    finally:
        cursor.close()
        conexion.close()


# ---------------------------------------------------------------------------
# Justificaciones (ajustes por trabajador y fecha)
# ---------------------------------------------------------------------------

@ajustes_bp.route("/api/ajustes/buscar-trabajador")
@login_requerido
def api_buscar_trabajador_para_ajuste():
    """Reutiliza la misma logica de busqueda del modulo de personal, para
    no depender de otra ruta ni duplicar demasiado codigo."""
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"results": []})

    patron = f"%{q}%"
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("""
        SELECT id, nombres, apellidos, dni, codigo_empleado
        FROM trabajadores
        WHERE (nombres || ' ' || apellidos) ILIKE %s
           OR (apellidos || ' ' || nombres) ILIKE %s
           OR dni ILIKE %s
           OR codigo_empleado ILIKE %s
        ORDER BY apellidos, nombres
        LIMIT 20
    """, (patron, patron, patron, patron))
    columnas = ["id", "nombres", "apellidos", "dni", "codigo_empleado"]
    resultados = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
    cursor.close()
    conexion.close()
    return jsonify({"results": resultados})


@ajustes_bp.route("/api/ajustes/trabajador/<int:trabajador_id>")
@login_requerido
def api_listar_ajustes_trabajador(trabajador_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("""
        SELECT id, fecha, motivo, creado_por, creado_en
        FROM ajustes_asistencia
        WHERE trabajador_id = %s
        ORDER BY fecha DESC
    """, (trabajador_id,))
    columnas = ["id", "fecha", "motivo", "creado_por", "creado_en"]
    ajustes = []
    for fila in cursor.fetchall():
        a = dict(zip(columnas, fila))
        a["fecha"] = str(a["fecha"])
        a["creado_en"] = str(a["creado_en"])
        ajustes.append(a)
    cursor.close()
    conexion.close()
    return jsonify({"ajustes": ajustes})


@ajustes_bp.route("/api/ajustes")
@login_requerido
def api_listar_todos_los_ajustes():
    """Todas las justificaciones de todos los trabajadores, para verlas de
    un vistazo sin tener que buscar persona por persona (igual que ya se
    puede con los feriados)."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("""
        SELECT a.id, a.fecha, a.motivo, a.creado_por, a.trabajador_id,
               t.nombres, t.apellidos, a.creado_en, a.observacion
        FROM ajustes_asistencia a
        JOIN trabajadores t ON t.id = a.trabajador_id
        ORDER BY a.fecha DESC
    """)
    ajustes = [
        {
            "id": fila[0],
            "fecha": str(fila[1]),
            "motivo": fila[2],
            "creado_por": fila[3],
            "trabajadorId": fila[4],
            "trabajadorNombre": f"{fila[6]} {fila[5]}",
            "creadoEn": fila[7].strftime("%Y-%m-%d %H:%M") if fila[7] else None,
            "observacion": fila[8]
        }
        for fila in cursor.fetchall()
    ]
    cursor.close()
    conexion.close()
    return jsonify({"ajustes": ajustes})


@ajustes_bp.route("/api/ajustes", methods=["POST"])
@login_requerido
def api_crear_ajuste():
    datos = request.get_json(silent=True) or {}
    trabajador_id = datos.get("trabajadorId")
    fecha = (datos.get("fecha") or "").strip()
    motivo = (datos.get("motivo") or "").strip()
    observacion = (datos.get("observacion") or "").strip() or None

    if not trabajador_id or not fecha or not motivo:
        return jsonify({"error": "Trabajador, fecha y motivo son obligatorios"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("""
            INSERT INTO ajustes_asistencia (trabajador_id, fecha, motivo, tipo_id, observacion, creado_por, creado_en)
            VALUES (%s, %s, %s, (SELECT id FROM motivos_justificacion WHERE nombre = %s), %s, %s, %s)
            ON CONFLICT (trabajador_id, fecha)
            DO UPDATE SET motivo = EXCLUDED.motivo, tipo_id = EXCLUDED.tipo_id, observacion = EXCLUDED.observacion,
                          creado_por = EXCLUDED.creado_por, creado_en = EXCLUDED.creado_en
        """, (trabajador_id, fecha, motivo, motivo, observacion, session.get("username"), datetime.now()))
        conexion.commit()
        return jsonify({"ok": True})
    except Exception as error:
        conexion.rollback()
        print("ERROR AL CREAR AJUSTE:", error)
        return jsonify({"error": "No se pudo guardar la justificación"}), 500
    finally:
        cursor.close()
        conexion.close()


@ajustes_bp.route("/api/ajustes/masivo", methods=["POST"])
@login_requerido
def api_crear_ajuste_masivo():
    """Aplica la misma justificacion a VARIOS trabajadores a la vez, para
    todos los dias de lunes a viernes dentro de un rango de fechas -- para
    no tener que justificar uno por uno cuando, por ejemplo, un grupo se
    va varios dias a una conferencia."""
    datos = request.get_json(silent=True) or {}
    trabajador_ids = datos.get("trabajadorIds") or []
    fecha_inicio_str = (datos.get("fechaInicio") or "").strip()
    fecha_fin_str = (datos.get("fechaFin") or "").strip()
    motivo = (datos.get("motivo") or "").strip()
    observacion = (datos.get("observacion") or "").strip() or None

    if not trabajador_ids:
        return jsonify({"error": "Selecciona al menos un trabajador"}), 400
    if not fecha_inicio_str or not fecha_fin_str:
        return jsonify({"error": "La fecha de inicio y de fin son obligatorias"}), 400
    if not motivo:
        return jsonify({"error": "El motivo es obligatorio"}), 400

    try:
        fecha_inicio = datetime.strptime(fecha_inicio_str, "%Y-%m-%d").date()
        fecha_fin = datetime.strptime(fecha_fin_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Las fechas no son válidas"}), 400

    if fecha_fin < fecha_inicio:
        return jsonify({"error": "La fecha de fin no puede ser anterior a la de inicio"}), 400

    # Solo los dias de lunes a viernes dentro del rango -- los fines de
    # semana no tienen evaluacion de tardanza, no hace falta justificarlos.
    dias = []
    dia_actual = fecha_inicio
    while dia_actual <= fecha_fin:
        if dia_actual.weekday() < 5:
            dias.append(dia_actual)
        dia_actual += timedelta(days=1)

    if not dias:
        return jsonify({"error": "El rango elegido no tiene ningún día de lunes a viernes"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        total_registros = 0
        for trabajador_id in trabajador_ids:
            for dia in dias:
                cursor.execute("""
                    INSERT INTO ajustes_asistencia (trabajador_id, fecha, motivo, tipo_id, observacion, creado_por, creado_en)
                    VALUES (%s, %s, %s, (SELECT id FROM motivos_justificacion WHERE nombre = %s), %s, %s, %s)
                    ON CONFLICT (trabajador_id, fecha)
                    DO UPDATE SET motivo = EXCLUDED.motivo, tipo_id = EXCLUDED.tipo_id, observacion = EXCLUDED.observacion,
                                  creado_por = EXCLUDED.creado_por, creado_en = EXCLUDED.creado_en
                """, (trabajador_id, dia, motivo, motivo, observacion, session.get("username"), datetime.now()))
                total_registros += 1

        conexion.commit()
        return jsonify({
            "ok": True,
            "totalTrabajadores": len(trabajador_ids),
            "totalDias": len(dias),
            "totalRegistros": total_registros
        })
    except Exception as error:
        conexion.rollback()
        print("ERROR AL CREAR AJUSTE MASIVO:", error)
        return jsonify({"error": "No se pudo guardar la justificación"}), 500
    finally:
        cursor.close()
        conexion.close()


@ajustes_bp.route("/api/ajustes", methods=["DELETE"])
@login_requerido
def api_eliminar_ajustes():
    """Elimina varias justificaciones juntas: todos los dias de una franja."""
    datos = request.get_json(silent=True) or {}
    ids = datos.get("ids")

    if (not isinstance(ids, list) or not ids
            or not all(type(i) is int for i in ids)):
        return jsonify({"error": "No se indicaron justificaciones válidas"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM ajustes_asistencia WHERE id = ANY(%s)", (ids,))
    eliminados = cursor.rowcount
    conexion.commit()
    cursor.close()
    conexion.close()

    if not eliminados:
        return jsonify({"error": "Justificación no encontrada"}), 404
    return jsonify({"ok": True, "eliminados": eliminados})


@ajustes_bp.route("/api/ajustes/<int:ajuste_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_ajuste(ajuste_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM ajustes_asistencia WHERE id = %s", (ajuste_id,))
    eliminado = cursor.rowcount > 0
    conexion.commit()
    cursor.close()
    conexion.close()

    if not eliminado:
        return jsonify({"error": "Justificación no encontrada"}), 404
    return jsonify({"ok": True})
