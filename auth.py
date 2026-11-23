# auth.py
# Login / logout basado en sesion de Flask, roles de usuario y decoradores
# para proteger las rutas.
#
# Roles:
#   admin     -> Administracion: ve todo el sistema.
#   logistica -> Logistica: solo el modulo de ordenes de compra.
#
# El rol se lee de la BD en cada peticion protegida (no se confia en la
# sesion), asi un cambio de rol o la eliminacion del usuario se aplica al
# instante y no hace falta que vuelva a iniciar sesion.

from functools import wraps
from urllib.parse import urlparse

from flask import Blueprint, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from db import obtener_conexion

auth_bp = Blueprint("auth", __name__)

ROL_ADMIN = "admin"
ROL_LOGISTICA = "logistica"
ROLES = {ROL_ADMIN: "Administración", ROL_LOGISTICA: "Logística"}


def _cargar_usuario():
    """Deja en g el usuario de la sesion (id, nombre y rol) o None si no hay
    sesion o el usuario ya no existe."""
    if "usuario" in g:
        return g.usuario
    g.usuario = None
    usuario_id = session.get("usuario_id")
    if usuario_id:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute("SELECT id, username, rol FROM usuarios WHERE id = %s", (usuario_id,))
        fila = cursor.fetchone()
        cursor.close()
        conexion.close()
        if fila:
            g.usuario = {"id": fila[0], "username": fila[1], "rol": fila[2]}
        else:
            session.clear()
    return g.usuario


def _es_api():
    return request.path.startswith("/api/")


def _sin_sesion():
    if _es_api():
        return jsonify({"error": "Tu sesión expiró. Vuelve a iniciar sesión."}), 401
    pagina_login = "auth.login_compras" if request.path.startswith("/ordenes-compra") else "auth.login"
    return redirect(url_for(pagina_login, next=request.full_path.rstrip("?")))


def _sin_permiso():
    if _es_api():
        return jsonify({"error": "No tienes permiso para esta acción"}), 403
    return redirect(url_for("ordenes_compra.pagina_ordenes_compra"))


def login_requerido(vista):
    """Solo Administracion. Es el decorador de todo el sistema salvo el
    modulo de compras: un usuario de Logistica que entre a cualquier otra
    pagina vuelve a las ordenes de compra (o recibe 403 en la API)."""
    @wraps(vista)
    def envoltura(*args, **kwargs):
        usuario = _cargar_usuario()
        if not usuario:
            return _sin_sesion()
        if usuario["rol"] != ROL_ADMIN:
            return _sin_permiso()
        return vista(*args, **kwargs)
    return envoltura


def acceso_compras(vista):
    """Modulo de ordenes de compra: Administracion y Logistica."""
    @wraps(vista)
    def envoltura(*args, **kwargs):
        usuario = _cargar_usuario()
        if not usuario:
            return _sin_sesion()
        if usuario["rol"] not in (ROL_ADMIN, ROL_LOGISTICA):
            return _sin_permiso()
        return vista(*args, **kwargs)
    return envoltura


@auth_bp.app_context_processor
def _usuario_en_plantillas():
    usuario = g.get("usuario")
    return {
        "usuario_actual": usuario,
        "es_admin": bool(usuario and usuario["rol"] == ROL_ADMIN),
    }


def _destino_seguro(destino):
    """Solo rutas internas ('/algo'), para que ?next= no pueda mandar a
    otro sitio."""
    if not destino or not destino.startswith("/") or destino.startswith("//"):
        return None
    if urlparse(destino).netloc:
        return None
    return destino


def _pagina_inicio(rol):
    if rol == ROL_ADMIN:
        return url_for("inicio")
    return url_for("ordenes_compra.pagina_ordenes_compra")


def _procesar_login(plantilla_compras):
    error = None
    siguiente = _destino_seguro(request.args.get("next"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute(
            "SELECT id, username, password_hash, rol FROM usuarios WHERE LOWER(username) = LOWER(%s)",
            (username,)
        )
        fila = cursor.fetchone()
        cursor.close()
        conexion.close()

        if fila and check_password_hash(fila[2], password):
            session.clear()
            session["usuario_id"] = fila[0]
            session["username"] = fila[1]
            if plantilla_compras:
                destino_por_defecto = url_for("ordenes_compra.pagina_ordenes_compra")
            else:
                destino_por_defecto = _pagina_inicio(fila[3])
            return redirect(siguiente or destino_por_defecto)

        error = "Usuario o contraseña incorrectos"

    return render_template("login.html", error=error, modo_compras=plantilla_compras,
                           siguiente=siguiente)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    return _procesar_login(plantilla_compras=False)


@auth_bp.route("/compras", methods=["GET", "POST"])
def login_compras():
    """Link para Logistica: login con la marca del modulo de compras, que
    lleva directo a las ordenes de compra."""
    usuario = _cargar_usuario()
    if usuario and request.method == "GET":
        return redirect(url_for("ordenes_compra.pagina_ordenes_compra"))
    return _procesar_login(plantilla_compras=True)


@auth_bp.route("/logout")
def logout():
    usuario = _cargar_usuario()
    volver_a_compras = bool(usuario and usuario["rol"] == ROL_LOGISTICA)
    session.clear()
    return redirect(url_for("auth.login_compras" if volver_a_compras else "auth.login"))
