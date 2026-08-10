# correo.py
# Envio de correos con un PDF adjunto, via SMTP (Outlook/Office365 u otro
# proveedor compatible con SMTP + STARTTLS). Las credenciales se leen de
# variables de entorno, nunca se escriben en el codigo.
#
# Variables de entorno necesarias:
#   SMTP_HOST      -> ej. smtp.office365.com
#   SMTP_PORT      -> ej. 587
#   SMTP_USER      -> la cuenta de correo completa (ej. admin@empresa.com)
#   SMTP_PASSWORD  -> la contraseña de esa cuenta
#   SMTP_FROM      -> (opcional) remitente a mostrar, si es distinto de SMTP_USER
#   SMTP_FROM_NAME -> (opcional) nombre a mostrar junto al remitente

import os
import smtplib
from email.message import EmailMessage


class ErrorConfiguracionCorreo(Exception):
    """Se lanza cuando faltan variables de entorno de correo. Distinta de
    un error de envio normal, porque si esto falla, NINGUN correo del lote
    se va a poder enviar (no tiene sentido seguir intentando uno por uno)."""
    pass


def _config_smtp():
    host = os.environ.get("SMTP_HOST")
    port = os.environ.get("SMTP_PORT")
    usuario = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")

    faltantes = [
        nombre for nombre, valor in [
            ("SMTP_HOST", host), ("SMTP_PORT", port),
            ("SMTP_USER", usuario), ("SMTP_PASSWORD", password)
        ] if not valor
    ]

    if faltantes:
        raise ErrorConfiguracionCorreo(
            "Falta configurar el envío de correo. Definan estas variables de "
            f"entorno en Railway: {', '.join(faltantes)}."
        )

    return host, int(port), usuario, password


def enviar_correo_con_adjunto(destino, asunto, cuerpo, nombre_archivo, contenido_bytes):
    """Envia un correo con un PDF adjunto. Lanza una excepcion si algo sale
    mal (credenciales, conexion, destino invalido, etc.) -- quien llama a
    esta funcion decide como registrar el error para ese destinatario."""
    host, port, usuario, password = _config_smtp()

    remitente = os.environ.get("SMTP_FROM") or usuario
    nombre_remitente = os.environ.get("SMTP_FROM_NAME")
    encabezado_de = f"{nombre_remitente} <{remitente}>" if nombre_remitente else remitente

    mensaje = EmailMessage()
    mensaje["Subject"] = asunto
    mensaje["From"] = encabezado_de
    mensaje["To"] = destino
    mensaje.set_content(cuerpo)
    mensaje.add_attachment(
        bytes(contenido_bytes),
        maintype="application",
        subtype="pdf",
        filename=nombre_archivo or "boleta.pdf"
    )

    with smtplib.SMTP(host, port, timeout=20) as servidor:
        servidor.starttls()
        servidor.login(usuario, password)
        servidor.send_message(mensaje)
