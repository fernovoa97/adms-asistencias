# correo_graph.py
# Envio de correo con un PDF adjunto via Microsoft Graph (POST /me/sendMail),
# usando el access_token obtenido por el login OAuth de microsoft_auth.py.
#
# A diferencia del SMTP, esto nunca maneja usuario/contraseña -- solo un
# token de acceso de corta duracion que ya viene autorizado.

import base64

import requests

GRAPH_SENDMAIL_URL = "https://graph.microsoft.com/v1.0/me/sendMail"


class ErrorEnvioGraph(Exception):
    """El envio via Microsoft Graph fallo (token invalido, destino
    rechazado, limite de tamaño, etc.)."""
    pass


def enviar_correo_con_adjunto_graph(access_token, destino, asunto, cuerpo,
                                     nombre_archivo, contenido_bytes):
    adjunto_b64 = base64.b64encode(bytes(contenido_bytes)).decode("ascii")

    payload = {
        "message": {
            "subject": asunto,
            "body": {"contentType": "Text", "content": cuerpo},
            "toRecipients": [{"emailAddress": {"address": destino}}],
            "attachments": [{
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": nombre_archivo or "boleta.pdf",
                "contentType": "application/pdf",
                "contentBytes": adjunto_b64
            }]
        },
        "saveToSentItems": "true"
    }

    resp = requests.post(
        GRAPH_SENDMAIL_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=30
    )

    # Graph responde 202 Accepted (sin cuerpo) cuando el envio se aceptó.
    if resp.status_code != 202:
        detalle = resp.text[:400] if resp.text else f"código {resp.status_code}"
        raise ErrorEnvioGraph(f"Microsoft Graph rechazó el envío: {detalle}")
