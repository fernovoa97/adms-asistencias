# usuarios.py
# Gestion de usuarios del sistema (solo Administracion): crear, cambiar
# rol o contrasena y eliminar. Siempre debe quedar al menos un usuario de
# Administracion, y nadie puede eliminarse a si mismo.

import re

from flask import Blueprint, g, jsonify, render_template, request
from werkzeug.security import generate_password_hash

from auth import ROL_ADMIN, ROLES, login_requerido
from db import obtener_conexion

usuarios_bp = Blueprint("usuarios", __name__)

LARGO_MINIMO_CLAVE = 6
PATRON_USUARIO = re.compile(r"[A-Za-z0-9._-]{3,40}")


def _validar_clave(clave):
    if len(clave) < LARGO_MINIMO_CLAVE:
        raise ValueError(f"La contraseña debe tener al menos {LARGO_MINIMO_CLAVE} caracteres")


def _otros_admins(cursor, usuario_id):
    cursor.execute("SELECT COUNT(*) FROM usuarios WHERE rol = %s AND id <> %s", (ROL_ADMIN, usuario_id))
    return cursor.fetchone()[0]


@usuarios_bp.route("/usuarios")
@login_requerido
def pagina_usuarios():
    return render_template("usuarios.html", roles=ROLES, active_page="usuarios")


@usuarios_bp.route("/api/usuarios")
@login_requerido
def api_listar_usuarios():
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT id, username, rol FROM usuarios ORDER BY rol, LOWER(username)")
    usuarios = [
        {"id": f[0], "username": f[1], "rol": f[2], "rolNombre": ROLES.get(f[2], f[2]),
         "esYo": f[0] == g.usuario["id"]}
        for f in cursor.fetchall()
    ]
    cursor.close()
    conexion.close()
    return jsonify({"usuarios": usuarios, "roles": ROLES})


@usuarios_bp.route("/api/usuarios", methods=["POST"])
@login_requerido
def api_crear_usuario():
    datos = request.get_json(silent=True) or {}
    username = (datos.get("username") or "").strip()
    clave = datos.get("password") or ""
    rol = datos.get("rol")
    try:
        if not PATRON_USUARIO.fullmatch(username):
            raise ValueError("El usuario debe tener de 3 a 40 caracteres: letras, números, punto, guion o guion bajo (sin espacios)")
        _validar_clave(clave)
        if rol not in ROLES:
            raise ValueError("Elige un rol")
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT 1 FROM usuarios WHERE LOWER(username) = LOWER(%s)", (username,))
        if cursor.fetchone():
            return jsonify({"error": f"Ya existe el usuario {username}"}), 409
        cursor.execute(
            "INSERT INTO usuarios (username, password_hash, rol) VALUES (%s, %s, %s) RETURNING id",
            (username, generate_password_hash(clave), rol)
        )
        usuario_id = cursor.fetchone()[0]
        conexion.commit()
        return jsonify({"ok": True, "id": usuario_id}), 201
    except Exception as error:
        conexion.rollback()
        print("ERROR CREANDO USUARIO:", error)
        return jsonify({"error": "No se pudo crear el usuario"}), 500
    finally:
        cursor.close()
        conexion.close()


@usuarios_bp.route("/api/usuarios/<int:usuario_id>", methods=["PUT"])
@login_requerido
def api_editar_usuario(usuario_id):
    """Cambia el rol y/o la contrasena (la contrasena solo si viene)."""
    datos = request.get_json(silent=True) or {}
    rol = datos.get("rol")
    clave = datos.get("password") or ""
    try:
        if rol is not None and rol not in ROLES:
            raise ValueError("Elige un rol")
        if clave:
            _validar_clave(clave)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT rol FROM usuarios WHERE id = %s", (usuario_id,))
        fila = cursor.fetchone()
        if not fila:
            return jsonify({"error": "Usuario no encontrado"}), 404
        if rol and rol != ROL_ADMIN and fila[0] == ROL_ADMIN and _otros_admins(cursor, usuario_id) == 0:
            return jsonify({"error": "Debe quedar al menos un usuario de Administración"}), 400

        if rol:
            cursor.execute("UPDATE usuarios SET rol = %s WHERE id = %s", (rol, usuario_id))
        if clave:
            cursor.execute("UPDATE usuarios SET password_hash = %s WHERE id = %s",
                           (generate_password_hash(clave), usuario_id))
        conexion.commit()
        return jsonify({"ok": True})
    except Exception as error:
        conexion.rollback()
        print("ERROR EDITANDO USUARIO:", error)
        return jsonify({"error": "No se pudo guardar el usuario"}), 500
    finally:
        cursor.close()
        conexion.close()


@usuarios_bp.route("/api/usuarios/<int:usuario_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_usuario(usuario_id):
    if usuario_id == g.usuario["id"]:
        return jsonify({"error": "No puedes eliminar tu propio usuario"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT rol FROM usuarios WHERE id = %s", (usuario_id,))
        fila = cursor.fetchone()
        if not fila:
            return jsonify({"error": "Usuario no encontrado"}), 404
        if fila[0] == ROL_ADMIN and _otros_admins(cursor, usuario_id) == 0:
            return jsonify({"error": "Debe quedar al menos un usuario de Administración"}), 400
        cursor.execute("DELETE FROM usuarios WHERE id = %s", (usuario_id,))
        conexion.commit()
        return jsonify({"ok": True})
    finally:
        cursor.close()
        conexion.close()
