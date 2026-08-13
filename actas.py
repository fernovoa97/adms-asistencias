# actas.py
# Modulo de actas de entrega: se crea un "acta" (ej. "Dia del trabajador")
# con uno o mas items (ej. "Gift card", "Canasta"), y se lleva el control
# de a quien se le entrego cada item, con su fecha de entrega. Los items
# que se marcan como "requiere devolucion" (pensado para equipos,
# herramientas, uniformes, etc.) tambien permiten registrar la fecha en
# que se devolvieron -- tipicamente cuando el trabajador es cesado.
#
# A diferencia de otros modulos (boletas, resumen), aca se muestran TODOS
# los trabajadores, incluidos los inactivos: un trabajador cesado sigue
# siendo relevante para este control hasta que devuelva lo que tenia
# pendiente.

from datetime import datetime

from flask import Blueprint, request, render_template, jsonify, session, abort

from auth import login_requerido
from db import obtener_conexion

actas_bp = Blueprint("actas", __name__)


# ==========================================================
# PAGINAS
# ==========================================================

@actas_bp.route("/actas")
@login_requerido
def pagina_actas():
    return render_template("actas.html", active_page="actas")


@actas_bp.route("/actas/<int:acta_id>")
@login_requerido
def pagina_acta_detalle(acta_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("SELECT id, nombre, descripcion FROM actas_entrega WHERE id = %s", (acta_id,))
    fila = cursor.fetchone()
    if not fila:
        cursor.close()
        conexion.close()
        abort(404)
    acta = {"id": fila[0], "nombre": fila[1], "descripcion": fila[2]}

    cursor.close()
    conexion.close()

    return render_template("acta_detalle.html", acta=acta, active_page="actas")


# ==========================================================
# API: actas
# ==========================================================

@actas_bp.route("/api/actas")
@login_requerido
def api_listar_actas():
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT
            a.id, a.nombre, a.descripcion, a.creado_en,
            COUNT(DISTINCT i.id) AS total_items,
            COUNT(DISTINCT r.trabajador_id) FILTER (WHERE r.entregado) AS trabajadores_con_entrega
        FROM actas_entrega a
        LEFT JOIN actas_entrega_items i ON i.acta_id = a.id
        LEFT JOIN actas_entrega_registros r ON r.item_id = i.id
        GROUP BY a.id, a.nombre, a.descripcion, a.creado_en
        ORDER BY a.creado_en DESC
    """)

    actas = []
    for fila in cursor.fetchall():
        actas.append({
            "id": fila[0],
            "nombre": fila[1],
            "descripcion": fila[2],
            "creado_en": str(fila[3]),
            "total_items": fila[4],
            "trabajadores_con_entrega": fila[5]
        })

    cursor.close()
    conexion.close()
    return jsonify({"actas": actas})


@actas_bp.route("/api/actas", methods=["POST"])
@login_requerido
def api_crear_acta():
    datos = request.get_json(silent=True) or {}
    nombre = (datos.get("nombre") or "").strip()
    descripcion = (datos.get("descripcion") or "").strip()
    items = datos.get("items") or []

    if not nombre:
        return jsonify({"error": "El nombre del acta es obligatorio"}), 400

    items_limpios = [
        {"nombre": (it.get("nombre") or "").strip(), "requiereDevolucion": bool(it.get("requiereDevolucion"))}
        for it in items
        if (it.get("nombre") or "").strip()
    ]
    if not items_limpios:
        return jsonify({"error": "Agrega al menos un ítem (ej. Gift card, Canasta)"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("""
            INSERT INTO actas_entrega (nombre, descripcion, creado_por, creado_en)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (nombre, descripcion, session.get("username"), datetime.now()))
        acta_id = cursor.fetchone()[0]

        for orden, item in enumerate(items_limpios):
            cursor.execute("""
                INSERT INTO actas_entrega_items (acta_id, nombre, requiere_devolucion, orden)
                VALUES (%s, %s, %s, %s)
            """, (acta_id, item["nombre"], item["requiereDevolucion"], orden))

        conexion.commit()
        return jsonify({"ok": True, "id": acta_id}), 201
    except Exception as error:
        conexion.rollback()
        print("ERROR CREANDO ACTA:", error)
        return jsonify({"error": "No se pudo crear el acta"}), 500
    finally:
        cursor.close()
        conexion.close()


@actas_bp.route("/api/actas/<int:acta_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_acta(acta_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM actas_entrega WHERE id = %s", (acta_id,))
    eliminado = cursor.rowcount > 0
    conexion.commit()
    cursor.close()
    conexion.close()

    if not eliminado:
        return jsonify({"error": "Acta no encontrada"}), 404
    return jsonify({"ok": True})


# ==========================================================
# API: items de un acta
# ==========================================================

@actas_bp.route("/api/actas/<int:acta_id>/items", methods=["POST"])
@login_requerido
def api_agregar_item(acta_id):
    datos = request.get_json(silent=True) or {}
    nombre = (datos.get("nombre") or "").strip()
    requiere_devolucion = bool(datos.get("requiereDevolucion"))

    if not nombre:
        return jsonify({"error": "El nombre del ítem es obligatorio"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT id FROM actas_entrega WHERE id = %s", (acta_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Acta no encontrada"}), 404

        cursor.execute("SELECT COALESCE(MAX(orden), -1) + 1 FROM actas_entrega_items WHERE acta_id = %s", (acta_id,))
        siguiente_orden = cursor.fetchone()[0]

        cursor.execute("""
            INSERT INTO actas_entrega_items (acta_id, nombre, requiere_devolucion, orden)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (acta_id, nombre, requiere_devolucion, siguiente_orden))
        item_id = cursor.fetchone()[0]

        conexion.commit()
        return jsonify({"ok": True, "id": item_id}), 201
    except Exception as error:
        conexion.rollback()
        print("ERROR AGREGANDO ITEM:", error)
        return jsonify({"error": "No se pudo agregar el ítem"}), 500
    finally:
        cursor.close()
        conexion.close()


@actas_bp.route("/api/actas/<int:acta_id>/items/<int:item_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_item(acta_id, item_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        "DELETE FROM actas_entrega_items WHERE id = %s AND acta_id = %s",
        (item_id, acta_id)
    )
    eliminado = cursor.rowcount > 0
    conexion.commit()
    cursor.close()
    conexion.close()

    if not eliminado:
        return jsonify({"error": "Ítem no encontrado"}), 404
    return jsonify({"ok": True})


# ==========================================================
# API: tabla completa (trabajadores x items) y guardar un registro
# ==========================================================

@actas_bp.route("/api/actas/<int:acta_id>/tabla")
@login_requerido
def api_tabla_acta(acta_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("SELECT id, nombre, descripcion FROM actas_entrega WHERE id = %s", (acta_id,))
    fila_acta = cursor.fetchone()
    if not fila_acta:
        cursor.close()
        conexion.close()
        return jsonify({"error": "Acta no encontrada"}), 404
    acta = {"id": fila_acta[0], "nombre": fila_acta[1], "descripcion": fila_acta[2]}

    cursor.execute("""
        SELECT id, nombre, requiere_devolucion
        FROM actas_entrega_items
        WHERE acta_id = %s
        ORDER BY orden, id
    """, (acta_id,))
    items = [
        {"id": f[0], "nombre": f[1], "requiereDevolucion": f[2]}
        for f in cursor.fetchall()
    ]

    # Todos los trabajadores, activos e inactivos -- aca si importa ver a
    # los inactivos, porque puede que todavia tengan algo pendiente de
    # devolver.
    cursor.execute("""
        SELECT id, nombres, apellidos, estado
        FROM trabajadores
        ORDER BY (estado = 'INACTIVO'), nombres, apellidos
    """)
    trabajadores_base = [
        {"id": f[0], "nombre": f"{f[1]} {f[2]}", "estado": f[3] or "ACTIVO"}
        for f in cursor.fetchall()
    ]

    cursor.execute("""
        SELECT r.item_id, r.trabajador_id, r.entregado, r.fecha_entrega, r.fecha_devolucion
        FROM actas_entrega_registros r
        JOIN actas_entrega_items i ON i.id = r.item_id
        WHERE i.acta_id = %s
    """, (acta_id,))
    registros_map = {}
    for item_id, trabajador_id, entregado, fecha_entrega, fecha_devolucion in cursor.fetchall():
        registros_map[(item_id, trabajador_id)] = {
            "entregado": entregado,
            "fechaEntrega": str(fecha_entrega) if fecha_entrega else None,
            "fechaDevolucion": str(fecha_devolucion) if fecha_devolucion else None
        }

    cursor.close()
    conexion.close()

    trabajadores = []
    for t in trabajadores_base:
        registros_por_item = {}
        for item in items:
            registro = registros_map.get((item["id"], t["id"]))
            registros_por_item[item["id"]] = registro or {
                "entregado": False, "fechaEntrega": None, "fechaDevolucion": None
            }
        trabajadores.append({**t, "registros": registros_por_item})

    return jsonify({"acta": acta, "items": items, "trabajadores": trabajadores})


@actas_bp.route("/api/actas/<int:acta_id>/registro", methods=["POST"])
@login_requerido
def api_guardar_registro(acta_id):
    """Guarda (o actualiza) el estado de un item para un trabajador:
    si se entrego, con que fecha, y si corresponde, la fecha de
    devolucion."""
    datos = request.get_json(silent=True) or {}
    item_id = datos.get("itemId")
    trabajador_id = datos.get("trabajadorId")
    entregado = bool(datos.get("entregado"))
    fecha_entrega = (datos.get("fechaEntrega") or "").strip() or None
    fecha_devolucion = (datos.get("fechaDevolucion") or "").strip() or None

    if not item_id or not trabajador_id:
        return jsonify({"error": "Falta el ítem o el trabajador"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("""
            INSERT INTO actas_entrega_registros (
                item_id, trabajador_id, entregado, fecha_entrega, fecha_devolucion, actualizado_en
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (item_id, trabajador_id) DO UPDATE SET
                entregado = EXCLUDED.entregado,
                fecha_entrega = EXCLUDED.fecha_entrega,
                fecha_devolucion = EXCLUDED.fecha_devolucion,
                actualizado_en = EXCLUDED.actualizado_en
        """, (item_id, trabajador_id, entregado, fecha_entrega, fecha_devolucion, datetime.now()))
        conexion.commit()
        return jsonify({"ok": True})
    except Exception as error:
        conexion.rollback()
        print("ERROR GUARDANDO REGISTRO DE ACTA:", error)
        return jsonify({"error": "No se pudo guardar el registro"}), 500
    finally:
        cursor.close()
        conexion.close()
