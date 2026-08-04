# auth.py
# Login / logout basado en sesion de Flask, y un decorador para proteger
# las rutas que requieren haber iniciado sesion.

from functools import wraps
from flask import Blueprint, request, session, redirect, url_for, render_template
from werkzeug.security import check_password_hash

from db import obtener_conexion

auth_bp = Blueprint("auth", __name__)


def login_requerido(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if not session.get("usuario_id"):
            return redirect(url_for("auth.login"))
        return vista(*args, **kwargs)
    return envoltura


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute(
            "SELECT id, password_hash FROM usuarios WHERE LOWER(username) = LOWER(%s)",
            (username,)
        )
        fila = cursor.fetchone()
        cursor.close()
        conexion.close()

        if fila and check_password_hash(fila[1], password):
            session["usuario_id"] = fila[0]
            session["username"] = username
            siguiente = request.args.get("next") or url_for("inicio")
            return redirect(siguiente)

        error = "Usuario o contraseña incorrectos"

    return render_template("login.html", error=error)


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
