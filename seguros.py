# seguros.py
# Seguros de cada colaborador (SCTR, FOLA, Vida Ley, EPS) y sus personas
# adicionales / dependientes. La edad del dependiente no se guarda: se
# calcula al leer a partir de su fecha de nacimiento.

from datetime import datetime

from flask import Blueprint, request, jsonify, session

from auth import login_requerido
from db import obtener_conexion
from validaciones import calcular_edad, hoy_local, parsear_fecha

seguros_bp = Blueprint("seguros", __name__)

TIPOS_SEGURO = ("SCTR", "FOLA", "Vida Ley", "EPS")
PARENTESCOS = ("Cónyuge", "Hijo/a")


def obtener_seguros(cursor, worker_id):
    cursor.execute("""
        SELECT id, tipo, fecha_afiliacion, creado_por, creado_en
        FROM seguros
        WHERE trabajador_id = %s
        ORDER BY fecha_afiliacion DESC, id DESC
    """, (worker_id,))

    seguros = [
        {
            "id": fila[0],
            "tipo": fila[1],
            "fecha_afiliacion": str(fila[2]),
            "creado_por": fila[3],
            "creado_en": fila[4].strftime("%Y-%m-%d %H:%M"),
            "dependientes": []
        }
        for fila in cursor.fetchall()
    ]

    if seguros:
        por_id = {s["id"]: s for s in seguros}
        cursor.execute("""
            SELECT id, seguro_id, parentesco, nombre_completo, fecha_nacimiento
            FROM seguros_dependientes
            WHERE seguro_id = ANY(%s)
            ORDER BY id
        """, (list(por_id),))

        for fila in cursor.fetchall():
            por_id[fila[1]]["dependientes"].append({
                "id": fila[0],
                "parentesco": fila[2],
                "nombre_completo": fila[3],
                "fecha_nacimiento": str(fila[4]),
                "edad": calcular_edad(fila[4])
            })

    return seguros


def _validar_seguro(datos):
    """Devuelve (valores, error): si hay error, valores es None."""
    tipo = (datos.get("tipo") or "").strip()
    if tipo not in TIPOS_SEGURO:
        return None, "Selecciona un tipo de seguro válido"

    try:
        fecha_afiliacion = parsear_fecha(datos.get("fechaAfiliacion"))
    except ValueError:
        return None, "La fecha de afiliación no es válida"
    if not fecha_afiliacion:
        return None, "La fecha de afiliación es obligatoria"

    dependientes_crudos = datos.get("dependientes") or []
    if not isinstance(dependientes_crudos, list):
        return None, "La lista de dependientes no es válida"

    dependientes = []
    for dependiente in dependientes_crudos:
        if not isinstance(dependiente, dict):
            return None, "La lista de dependientes no es válida"

        parentesco = (dependiente.get("parentesco") or "").strip()
        nombre = (dependiente.get("nombreCompleto") or "").strip()

        if parentesco not in PARENTESCOS:
            return None, "Selecciona el parentesco de cada dependiente"
        if not nombre:
            return None, "Escribe el nombre completo de cada dependiente"

        try:
            fecha_nacimiento = parsear_fecha(dependiente.get("fechaNacimiento"))
        except ValueError:
            return None, f"La fecha de nacimiento de {nombre} no es válida"
        if not fecha_nacimiento:
            return None, f"Indica la fecha de nacimiento de {nombre}"
        if fecha_nacimiento > hoy_local():
            return None, f"La fecha de nacimiento de {nombre} no puede ser futura"

        dependientes.append((parentesco, nombre, fecha_nacimiento))

    return {
        "tipo": tipo,
        "fecha_afiliacion": fecha_afiliacion,
        "dependientes": dependientes
    }, None


def _guardar_dependientes(cursor, seguro_id, dependientes):
    for parentesco, nombre, fecha_nacimiento in dependientes:
        cursor.execute("""
            INSERT INTO seguros_dependientes (
                seguro_id, parentesco, nombre_completo, fecha_nacimiento, creado_en
            )
            VALUES (%s, %s, %s, %s, %s)
        """, (seguro_id, parentesco, nombre, fecha_nacimiento, datetime.now()))


@seguros_bp.route("/api/trabajadores/<int:worker_id>/seguros", methods=["POST"])
@login_requerido
def api_crear_seguro(worker_id):
    valores, error = _validar_seguro(request.get_json(silent=True) or {})
    if error:
        return jsonify({"error": error}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT id FROM trabajadores WHERE id = %s", (worker_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Trabajador no encontrado"}), 404

        cursor.execute("""
            INSERT INTO seguros (trabajador_id, tipo, fecha_afiliacion, creado_por, creado_en)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (
            worker_id, valores["tipo"], valores["fecha_afiliacion"],
            session.get("username"), datetime.now()
        ))
        seguro_id = cursor.fetchone()[0]
        _guardar_dependientes(cursor, seguro_id, valores["dependientes"])

        conexion.commit()
        return jsonify({"ok": True, "id": seguro_id}), 201
    except Exception as error_bd:
        conexion.rollback()
        print("ERROR CREANDO SEGURO:", error_bd)
        return jsonify({"error": "No se pudo guardar el seguro"}), 500
    finally:
        cursor.close()
        conexion.close()


@seguros_bp.route("/api/seguros/<int:seguro_id>", methods=["PUT"])
@login_requerido
def api_actualizar_seguro(seguro_id):
    """Reemplaza el seguro completo: el formulario siempre manda la lista
    entera de dependientes."""
    valores, error = _validar_seguro(request.get_json(silent=True) or {})
    if error:
        return jsonify({"error": error}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute(
            "UPDATE seguros SET tipo = %s, fecha_afiliacion = %s WHERE id = %s",
            (valores["tipo"], valores["fecha_afiliacion"], seguro_id)
        )
        if cursor.rowcount == 0:
            conexion.rollback()
            return jsonify({"error": "Seguro no encontrado"}), 404

        cursor.execute("DELETE FROM seguros_dependientes WHERE seguro_id = %s", (seguro_id,))
        _guardar_dependientes(cursor, seguro_id, valores["dependientes"])

        conexion.commit()
        return jsonify({"ok": True})
    except Exception as error_bd:
        conexion.rollback()
        print("ERROR ACTUALIZANDO SEGURO:", error_bd)
        return jsonify({"error": "No se pudo actualizar el seguro"}), 500
    finally:
        cursor.close()
        conexion.close()


@seguros_bp.route("/api/seguros/<int:seguro_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_seguro(seguro_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM seguros WHERE id = %s", (seguro_id,))
    eliminado = cursor.rowcount > 0
    conexion.commit()
    cursor.close()
    conexion.close()

    if not eliminado:
        return jsonify({"error": "Seguro no encontrado"}), 404
    return jsonify({"ok": True})
