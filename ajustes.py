# ajustes.py
# Modulo de Ajustes: feriados (aplican a todos) y justificaciones de
# tardanza (por trabajador y fecha especifica).

from datetime import datetime

from flask import Blueprint, request, render_template, jsonify, session

from auth import login_requerido
from db import obtener_conexion

ajustes_bp = Blueprint("ajustes", __name__)


@ajustes_bp.route("/ajustes")
@login_requerido
def pagina_ajustes():
    return render_template("ajustes.html", active_page="ajustes")


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
# Catalogo de motivos de justificacion (combo administrable)
# ---------------------------------------------------------------------------

@ajustes_bp.route("/api/motivos-justificacion")
@login_requerido
def api_listar_motivos():
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT id, nombre FROM motivos_justificacion ORDER BY nombre")
    motivos = [{"id": f[0], "nombre": f[1]} for f in cursor.fetchall()]
    cursor.close()
    conexion.close()
    return jsonify({"motivos": motivos})


@ajustes_bp.route("/api/motivos-justificacion", methods=["POST"])
@login_requerido
def api_crear_motivo():
    datos = request.get_json(silent=True) or {}
    nombre = (datos.get("nombre") or "").strip()

    if not nombre:
        return jsonify({"error": "El nombre del motivo es obligatorio"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT id FROM motivos_justificacion WHERE nombre ILIKE %s", (nombre,))
        if cursor.fetchone():
            return jsonify({"error": "Ya existe un motivo con ese nombre"}), 400

        cursor.execute("""
            INSERT INTO motivos_justificacion (nombre, creado_en)
            VALUES (%s, %s)
            RETURNING id
        """, (nombre, datetime.now()))
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
           OR dni ILIKE %s
           OR codigo_empleado ILIKE %s
        ORDER BY nombres
        LIMIT 20
    """, (patron, patron, patron))
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
               t.nombres, t.apellidos
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
            "trabajadorNombre": f"{fila[5]} {fila[6]}"
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

    if not trabajador_id or not fecha or not motivo:
        return jsonify({"error": "Trabajador, fecha y motivo son obligatorios"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("""
            INSERT INTO ajustes_asistencia (trabajador_id, fecha, motivo, creado_por, creado_en)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (trabajador_id, fecha)
            DO UPDATE SET motivo = EXCLUDED.motivo, creado_por = EXCLUDED.creado_por, creado_en = EXCLUDED.creado_en
        """, (trabajador_id, fecha, motivo, session.get("username"), datetime.now()))
        conexion.commit()
        return jsonify({"ok": True})
    except Exception as error:
        conexion.rollback()
        print("ERROR AL CREAR AJUSTE:", error)
        return jsonify({"error": "No se pudo guardar la justificación"}), 500
    finally:
        cursor.close()
        conexion.close()


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
