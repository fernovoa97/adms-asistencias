# proveedores.py
# Registro de proveedores para las ordenes de compra: RUC (unico), razon
# social y direccion. Se alimenta solo al guardar una orden de compra y
# tambien se puede administrar a mano. Las ordenes ya emitidas guardan su
# propia copia de los datos del proveedor, asi que editar aqui no las cambia.

from datetime import datetime
import re

import psycopg2
from flask import Blueprint, jsonify, render_template, request

from auth import acceso_compras, login_requerido
from db import obtener_conexion

proveedores_bp = Blueprint("proveedores", __name__)


def limpiar_ruc(valor):
    return re.sub(r"\s", "", valor or "")


def registrar_proveedor(cursor, ruc, nombre, direccion, actualizar=True):
    """Guarda el proveedor de una orden de compra. Si el RUC ya existe y
    `actualizar` es True, actualiza la razon social y la direccion (una
    direccion vacia no borra la registrada)."""
    accion = """
        DO UPDATE SET nombre = EXCLUDED.nombre,
                      direccion = COALESCE(NULLIF(EXCLUDED.direccion, ''), proveedores.direccion),
                      actualizado_en = EXCLUDED.creado_en
    """ if actualizar else "DO NOTHING"
    cursor.execute(f"""
        INSERT INTO proveedores (ruc, nombre, direccion, creado_en)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (ruc) {accion}
    """, (ruc, nombre, direccion, datetime.now()))


def _fila_a_proveedor(f):
    return {"id": f[0], "ruc": f[1], "nombre": f[2], "direccion": f[3] or "", "ordenes": f[4]}


def _leer_proveedor(datos):
    ruc = limpiar_ruc(datos.get("ruc"))
    nombre = (datos.get("nombre") or "").strip()
    if not re.fullmatch(r"\d{11}", ruc):
        raise ValueError("El RUC debe tener 11 dígitos")
    if not nombre:
        raise ValueError("La razón social es obligatoria")
    return ruc, nombre, (datos.get("direccion") or "").strip()


@proveedores_bp.route("/ordenes-compra/proveedores")
@acceso_compras
def pagina_proveedores():
    return render_template("proveedores.html", active_page="proveedores")


@proveedores_bp.route("/api/proveedores")
@acceso_compras
def api_listar_proveedores():
    """Busqueda por RUC o razon social. `limite` corto para el buscador del
    formulario; sin el, la lista completa de la pagina de proveedores."""
    busqueda = (request.args.get("q") or "").strip()
    try:
        limite = min(int(request.args.get("limite") or 1000), 1000)
    except ValueError:
        limite = 1000
    filtro, parametros = "", []
    if busqueda:
        patron = f"%{busqueda}%"
        filtro = "WHERE p.ruc ILIKE %s OR p.nombre ILIKE %s"
        parametros = [patron, patron]

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(f"""
        SELECT p.id, p.ruc, p.nombre, p.direccion,
               (SELECT COUNT(*) FROM ordenes_compra o WHERE o.proveedor_ruc = p.ruc)
        FROM proveedores p {filtro}
        ORDER BY LOWER(p.nombre), p.ruc
        LIMIT %s
    """, parametros + [limite])
    proveedores = [_fila_a_proveedor(f) for f in cursor.fetchall()]
    cursor.close()
    conexion.close()
    return jsonify({"proveedores": proveedores})


@proveedores_bp.route("/api/proveedores/ruc/<ruc>")
@acceso_compras
def api_proveedor_por_ruc(ruc):
    ruc = limpiar_ruc(ruc)
    if not re.fullmatch(r"\d{11}", ruc):
        return jsonify({"proveedor": None})
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT id, ruc, nombre, direccion, 0 FROM proveedores WHERE ruc = %s", (ruc,))
    fila = cursor.fetchone()
    cursor.close()
    conexion.close()
    return jsonify({"proveedor": _fila_a_proveedor(fila) if fila else None})


@proveedores_bp.route("/api/proveedores", methods=["POST"])
@acceso_compras
def api_crear_proveedor():
    try:
        ruc, nombre, direccion = _leer_proveedor(request.get_json(silent=True) or {})
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("""
            INSERT INTO proveedores (ruc, nombre, direccion, creado_en)
            VALUES (%s, %s, %s, %s) RETURNING id
        """, (ruc, nombre, direccion, datetime.now()))
        proveedor_id = cursor.fetchone()[0]
        conexion.commit()
        return jsonify({"ok": True, "id": proveedor_id}), 201
    except psycopg2.errors.UniqueViolation:
        conexion.rollback()
        return jsonify({"error": f"Ya existe un proveedor con el RUC {ruc}"}), 409
    finally:
        cursor.close()
        conexion.close()


@proveedores_bp.route("/api/proveedores/<int:proveedor_id>", methods=["PUT"])
@acceso_compras
def api_editar_proveedor(proveedor_id):
    try:
        ruc, nombre, direccion = _leer_proveedor(request.get_json(silent=True) or {})
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("""
            UPDATE proveedores SET ruc = %s, nombre = %s, direccion = %s, actualizado_en = %s
            WHERE id = %s
        """, (ruc, nombre, direccion, datetime.now(), proveedor_id))
        if cursor.rowcount == 0:
            conexion.rollback()
            return jsonify({"error": "Proveedor no encontrado"}), 404
        conexion.commit()
        return jsonify({"ok": True})
    except psycopg2.errors.UniqueViolation:
        conexion.rollback()
        return jsonify({"error": f"Ya existe un proveedor con el RUC {ruc}"}), 409
    finally:
        cursor.close()
        conexion.close()


@proveedores_bp.route("/api/proveedores/<int:proveedor_id>", methods=["DELETE"])
@login_requerido  # eliminar: solo Administracion
def api_eliminar_proveedor(proveedor_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM proveedores WHERE id = %s", (proveedor_id,))
    eliminado = cursor.rowcount > 0
    conexion.commit()
    cursor.close()
    conexion.close()
    if not eliminado:
        return jsonify({"error": "Proveedor no encontrado"}), 404
    return jsonify({"ok": True})
