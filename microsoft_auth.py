# microsoft_auth.py
# Login OAuth 2.0 (Authorization Code flow) contra Microsoft Entra ID.
#
# Flujo:
#   1. /auth/microsoft/iniciar redirige al login real de Microsoft.
#   2. La persona ingresa su correo, contraseña y aprueba el MFA en su
#      celular -- todo eso ocurre en la pagina de Microsoft, esta app
#      nunca ve ni guarda esa contraseña ni el MFA.
#   3. Microsoft redirige de vuelta a /auth/microsoft/callback con un
#      "code" temporal.
#   4. El servidor (no el navegador) canjea ese code por un access_token
#      y un refresh_token, y los guarda.
#   5. Mientras el refresh_token siga vigente, los envios siguientes no
#      vuelven a pedir login: se renueva el access_token en silencio.
#
# Variables de entorno requeridas:
#   MS_TENANT_ID     -> Directory (tenant) ID de Microsoft Entra
#   MS_CLIENT_ID     -> Application (client) ID de la app registrada
#   MS_CLIENT_SECRET -> Client secret generado para esa app
#   MS_REDIRECT_URI  -> URL publica exacta de /auth/microsoft/callback
#                        (debe coincidir EXACTO con la registrada en Azure)

import os
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
from flask import Blueprint, request, redirect, session, url_for

from auth import login_requerido
from db import obtener_conexion

microsoft_auth_bp = Blueprint("microsoft_auth", __name__)

AUTHORITY = "https://login.microsoftonline.com"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# offline_access es lo que permite recibir un refresh_token (sin el, cada
# access_token expiraria en ~1 hora y habria que hacer login de nuevo).
SCOPES = "offline_access Mail.Send User.Read"


class ErrorConfiguracionMicrosoft(Exception):
    """Faltan variables de entorno para poder usar el login de Microsoft."""
    pass


def _config():
    tenant_id = os.environ.get("MS_TENANT_ID")
    client_id = os.environ.get("MS_CLIENT_ID")
    client_secret = os.environ.get("MS_CLIENT_SECRET")
    redirect_uri = os.environ.get("MS_REDIRECT_URI")

    faltantes = [
        nombre for nombre, valor in [
            ("MS_TENANT_ID", tenant_id), ("MS_CLIENT_ID", client_id),
            ("MS_CLIENT_SECRET", client_secret), ("MS_REDIRECT_URI", redirect_uri)
        ] if not valor
    ]

    if faltantes:
        raise ErrorConfiguracionMicrosoft(
            "Falta configurar el login de Microsoft. Definan estas variables "
            f"de entorno en Railway: {', '.join(faltantes)}."
        )

    return tenant_id, client_id, client_secret, redirect_uri


# ==========================================================
# Guardar / leer / renovar el token (una sola fila en la BD)
# ==========================================================

def _guardar_token(access_token, refresh_token, expires_in, cuenta_correo=None):
    # Restamos 60 segundos de margen para no usar un token que vence
    # justo en medio de un envio.
    expira_en = datetime.now() + timedelta(seconds=int(expires_in) - 60)

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("""
        INSERT INTO microsoft_oauth_token (id, access_token, refresh_token, cuenta_correo, expira_en, actualizado_en)
        VALUES (1, %s, %s, COALESCE(%s, (SELECT cuenta_correo FROM microsoft_oauth_token WHERE id = 1)), %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            access_token = EXCLUDED.access_token,
            refresh_token = EXCLUDED.refresh_token,
            cuenta_correo = COALESCE(EXCLUDED.cuenta_correo, microsoft_oauth_token.cuenta_correo),
            expira_en = EXCLUDED.expira_en,
            actualizado_en = EXCLUDED.actualizado_en
    """, (access_token, refresh_token, cuenta_correo, expira_en, datetime.now()))
    conexion.commit()
    cursor.close()
    conexion.close()


def _leer_token_guardado():
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("""
        SELECT access_token, refresh_token, cuenta_correo, expira_en
        FROM microsoft_oauth_token WHERE id = 1
    """)
    fila = cursor.fetchone()
    cursor.close()
    conexion.close()

    if not fila:
        return None
    return {
        "access_token": fila[0], "refresh_token": fila[1],
        "cuenta_correo": fila[2], "expira_en": fila[3]
    }


def estado_conexion():
    """Para mostrar en pantalla si hay una cuenta conectada, sin forzar
    ninguna renovacion de token (solo lectura)."""
    guardado = _leer_token_guardado()
    if not guardado:
        return {"conectado": False, "cuenta_correo": None}
    return {"conectado": True, "cuenta_correo": guardado["cuenta_correo"]}


def obtener_token_valido():
    """Devuelve un access_token listo para usar, renovandolo en silencio
    con el refresh_token si ya vencio. Devuelve None si no hay ninguna
    sesion guardada, o si la renovacion tambien fallo (en ese caso hace
    falta iniciar sesion de nuevo)."""
    guardado = _leer_token_guardado()
    if not guardado:
        return None

    if guardado["expira_en"] > datetime.now():
        return guardado["access_token"]

    try:
        tenant_id, client_id, client_secret, _ = _config()
    except ErrorConfiguracionMicrosoft:
        return None

    try:
        resp = requests.post(
            f"{AUTHORITY}/{tenant_id}/oauth2/v2.0/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": guardado["refresh_token"],
                "scope": SCOPES
            },
            timeout=15
        )
        resp.raise_for_status()
        datos = resp.json()
    except Exception as error:
        print("ERROR RENOVANDO TOKEN DE MICROSOFT:", error)
        return None

    # Microsoft casi siempre devuelve un refresh_token nuevo -- si no
    # viene, nos quedamos con el que ya teniamos.
    nuevo_refresh = datos.get("refresh_token", guardado["refresh_token"])
    _guardar_token(datos["access_token"], nuevo_refresh, datos["expires_in"])
    return datos["access_token"]


# ==========================================================
# Rutas del login
# ==========================================================

@microsoft_auth_bp.route("/auth/microsoft/iniciar")
@login_requerido
def iniciar_login_microsoft():
    try:
        tenant_id, client_id, _, redirect_uri = _config()
    except ErrorConfiguracionMicrosoft as error:
        return str(error), 500

    estado = secrets.token_urlsafe(24)
    session["ms_oauth_state"] = estado

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": SCOPES,
        "state": estado
    }
    url_autorizacion = f"{AUTHORITY}/{tenant_id}/oauth2/v2.0/authorize?" + urlencode(params)
    return redirect(url_autorizacion)


@microsoft_auth_bp.route("/auth/microsoft/callback")
@login_requerido
def callback_microsoft():
    error = request.args.get("error")
    if error:
        descripcion = request.args.get("error_description", error)
        return f"No se pudo conectar la cuenta de Microsoft: {descripcion}", 400

    codigo = request.args.get("code")
    estado_recibido = request.args.get("state")
    estado_guardado = session.pop("ms_oauth_state", None)

    if not codigo:
        return "Falta el código de autorización en la respuesta de Microsoft.", 400

    if not estado_recibido or estado_recibido != estado_guardado:
        return "La solicitud expiró o no es válida. Intenta conectar la cuenta de nuevo.", 400

    try:
        tenant_id, client_id, client_secret, redirect_uri = _config()
    except ErrorConfiguracionMicrosoft as error_config:
        return str(error_config), 500

    try:
        resp = requests.post(
            f"{AUTHORITY}/{tenant_id}/oauth2/v2.0/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "authorization_code",
                "code": codigo,
                "redirect_uri": redirect_uri,
                "scope": SCOPES
            },
            timeout=15
        )
        resp.raise_for_status()
        datos = resp.json()
    except Exception as error_token:
        print("ERROR CANJEANDO CODIGO DE MICROSOFT:", error_token)
        return "No se pudo completar la conexión con Microsoft. Intenta de nuevo.", 500

    cuenta_correo = _obtener_correo_de_la_cuenta(datos["access_token"])
    _guardar_token(datos["access_token"], datos["refresh_token"], datos["expires_in"], cuenta_correo)

    siguiente = session.pop("ms_next_action", None)
    if siguiente and siguiente.get("tipo") == "enviar_periodo":
        from boletas import _enviar_boletas_periodo  # import tardio: evita ciclo entre modulos
        periodo_id = siguiente["periodo_id"]
        resultado = _enviar_boletas_periodo(periodo_id)
        return redirect(url_for(
            "boletas.pagina_periodo", periodo_id=periodo_id,
            enviadas=resultado["enviadas"], con_error=resultado["con_error"]
        ))

    return redirect(url_for("boletas.pagina_boletas"))


def _obtener_correo_de_la_cuenta(access_token):
    """Solo para mostrar en pantalla que cuenta quedo conectada. Si falla
    por lo que sea, no es grave -- simplemente no se muestra el correo."""
    try:
        resp = requests.get(
            f"{GRAPH_BASE}/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )
        resp.raise_for_status()
        datos = resp.json()
        return datos.get("mail") or datos.get("userPrincipalName")
    except Exception:
        return None
