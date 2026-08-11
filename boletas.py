# boletas.py
# Modulo de boletas de pago:
# - Se crea un "periodo de pago" (ej. "1ra quincena - Agosto 2026")
# - Se sube el PDF de la boleta de cada trabajador para ese periodo
# - Con un clic se envian por correo todas las boletas pendientes del
#   periodo, cada una a su trabajador, con un PDF adjunto distinto.
#
# El envio SIEMPRE se dispara manualmente (nunca automatico/programado):
# es informacion sensible (sueldos) y un envio automatico sin revision
# humana es un riesgo que no vale la pena correr.
#
# El correo se envia via Microsoft Graph, usando el token OAuth que
# maneja microsoft_auth.py (login real de Microsoft + MFA en el celular,
# nunca usuario/contraseña por SMTP).

from datetime import datetime

from flask import Blueprint, request, render_template, jsonify, session, abort, redirect, url_for

from auth import login_requerido
from db import obtener_conexion
from microsoft_auth import obtener_token_valido, estado_conexion
from correo_graph import enviar_correo_con_adjunto_graph

boletas_bp = Blueprint("boletas", __name__)

TAMANO_MAXIMO_PDF = 15 * 1024 * 1024  # 15 MB


def _psycopg2_binary(contenido_bytes):
    import psycopg2
    return psycopg2.Binary(contenido_bytes)


# ==========================================================
# PAGINAS
# ==========================================================

@boletas_bp.route("/boletas")
@login_requerido
def pagina_boletas():
    return render_template("boletas.html", active_page="boletas")


@boletas_bp.route("/boletas/<int:periodo_id>")
@login_requerido
def pagina_periodo(periodo_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("SELECT id, nombre FROM periodos_pago WHERE id = %s", (periodo_id,))
    fila = cursor.fetchone()
    if not fila:
        cursor.close()
        conexion.close()
        abort(404)
    periodo = {"id": fila[0], "nombre": fila[1]}

    cursor.close()
    conexion.close()

    return render_template(
        "boleta_periodo.html",
        periodo=periodo,
        conexion_microsoft=estado_conexion(),
        active_page="boletas"
    )


# ==========================================================
# API: periodos de pago
# ==========================================================

@boletas_bp.route("/api/periodos")
@login_requerido
def api_listar_periodos():
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT
            p.id, p.nombre, p.creado_en,
            COUNT(b.id) FILTER (WHERE b.id IS NOT NULL) AS total_cargadas,
            COUNT(b.id) FILTER (WHERE b.estado_envio = 'ENVIADO') AS total_enviadas,
            COUNT(b.id) FILTER (WHERE b.estado_envio = 'ERROR') AS total_error
        FROM periodos_pago p
        LEFT JOIN boletas_pago b ON b.periodo_id = p.id
        GROUP BY p.id, p.nombre, p.creado_en
        ORDER BY p.creado_en DESC
    """)

    periodos = []
    for fila in cursor.fetchall():
        periodos.append({
            "id": fila[0],
            "nombre": fila[1],
            "creado_en": str(fila[2]),
            "total_cargadas": fila[3],
            "total_enviadas": fila[4],
            "total_error": fila[5]
        })

    cursor.close()
    conexion.close()
    return jsonify({"periodos": periodos})


@boletas_bp.route("/api/periodos", methods=["POST"])
@login_requerido
def api_crear_periodo():
    datos = request.get_json(silent=True) or {}
    nombre = (datos.get("nombre") or "").strip()

    if not nombre:
        return jsonify({"error": "El nombre del periodo es obligatorio"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("""
            INSERT INTO periodos_pago (nombre, creado_por, creado_en)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (nombre, session.get("username"), datetime.now()))
        periodo_id = cursor.fetchone()[0]
        conexion.commit()
        return jsonify({"ok": True, "id": periodo_id}), 201
    except Exception as error:
        conexion.rollback()
        print("ERROR CREANDO PERIODO:", error)
        return jsonify({"error": "No se pudo crear el periodo"}), 500
    finally:
        cursor.close()
        conexion.close()


@boletas_bp.route("/api/periodos/<int:periodo_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_periodo(periodo_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM periodos_pago WHERE id = %s", (periodo_id,))
    eliminado = cursor.rowcount > 0
    conexion.commit()
    cursor.close()
    conexion.close()

    if not eliminado:
        return jsonify({"error": "Periodo no encontrado"}), 404
    return jsonify({"ok": True})


# ==========================================================
# API: trabajadores + boletas de un periodo especifico
# ==========================================================

@boletas_bp.route("/api/periodos/<int:periodo_id>/trabajadores")
@login_requerido
def api_trabajadores_del_periodo(periodo_id):
    """Lista todos los trabajadores activos, junto con el estado de su
    boleta en este periodo especifico (si ya se subio, si ya se envio)."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT
            t.id, t.nombres, t.apellidos, t.email, t.email_corporativo,
            b.id AS boleta_id, b.archivo_nombre, b.correo_destino,
            b.estado_envio, b.error_detalle, b.enviado_en
        FROM trabajadores t
        LEFT JOIN boletas_pago b
            ON b.trabajador_id = t.id AND b.periodo_id = %s
        WHERE t.estado IS DISTINCT FROM 'INACTIVO'
        ORDER BY t.nombres, t.apellidos
    """, (periodo_id,))

    trabajadores = []
    for fila in cursor.fetchall():
        correo_sugerido = fila[4] or fila[3]  # corporativo si existe, si no personal
        trabajadores.append({
            "id": fila[0],
            "nombre": f"{fila[1]} {fila[2]}",
            "email_personal": fila[3],
            "email_corporativo": fila[4],
            "boleta_id": fila[5],
            "archivo_nombre": fila[6],
            "correo_destino": fila[7] or correo_sugerido,
            "estado_envio": fila[8],
            "error_detalle": fila[9],
            "enviado_en": str(fila[10]) if fila[10] else None
        })

    cursor.close()
    conexion.close()
    return jsonify({"trabajadores": trabajadores})


@boletas_bp.route("/api/periodos/<int:periodo_id>/boletas", methods=["POST"])
@login_requerido
def api_subir_boleta(periodo_id):
    trabajador_id = request.form.get("trabajador_id", type=int)
    correo_destino = (request.form.get("correo_destino") or "").strip()
    archivo = request.files.get("archivo")

    if not trabajador_id or not correo_destino:
        return jsonify({"error": "Falta el trabajador o el correo de destino"}), 400

    if not archivo or not archivo.filename:
        return jsonify({"error": "No se recibió ningún archivo"}), 400

    if not archivo.filename.lower().endswith(".pdf"):
        return jsonify({"error": "El archivo debe ser un PDF"}), 400

    contenido = archivo.read()
    if len(contenido) > TAMANO_MAXIMO_PDF:
        return jsonify({"error": "El archivo supera los 15MB"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("""
            INSERT INTO boletas_pago (
                periodo_id, trabajador_id, archivo_nombre, archivo_contenido,
                correo_destino, estado_envio, subido_en
            )
            VALUES (%s, %s, %s, %s, %s, 'PENDIENTE', %s)
            ON CONFLICT (periodo_id, trabajador_id) DO UPDATE SET
                archivo_nombre = EXCLUDED.archivo_nombre,
                archivo_contenido = EXCLUDED.archivo_contenido,
                correo_destino = EXCLUDED.correo_destino,
                estado_envio = 'PENDIENTE',
                error_detalle = NULL,
                enviado_en = NULL,
                subido_en = EXCLUDED.subido_en
            RETURNING id
        """, (
            periodo_id, trabajador_id, archivo.filename,
            _psycopg2_binary(contenido), correo_destino, datetime.now()
        ))
        boleta_id = cursor.fetchone()[0]
        conexion.commit()
        return jsonify({"ok": True, "id": boleta_id})
    except Exception as error:
        conexion.rollback()
        print("ERROR SUBIENDO BOLETA:", error)
        return jsonify({"error": "No se pudo subir la boleta"}), 500
    finally:
        cursor.close()
        conexion.close()


@boletas_bp.route("/api/boletas/<int:boleta_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_boleta(boleta_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM boletas_pago WHERE id = %s", (boleta_id,))
    eliminado = cursor.rowcount > 0
    conexion.commit()
    cursor.close()
    conexion.close()

    if not eliminado:
        return jsonify({"error": "Boleta no encontrada"}), 404
    return jsonify({"ok": True})


# ==========================================================
# Enviar boletas pendientes de un periodo (via Microsoft Graph)
# ==========================================================

def _enviar_boletas_periodo(periodo_id):
    """Envia todas las boletas pendientes de un periodo. Asume que ya se
    verifico que hay un token utilizable -- si por alguna razon ya no lo
    hay al momento de enviar (ej. se revoco en Microsoft justo en el medio),
    se corta el lote entero, igual que antes se hacia si faltaba la
    configuracion de SMTP."""
    access_token = obtener_token_valido()
    if not access_token:
        return {"enviadas": 0, "con_error": 0, "sin_token": True}

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("SELECT nombre FROM periodos_pago WHERE id = %s", (periodo_id,))
    fila_periodo = cursor.fetchone()
    nombre_periodo = fila_periodo[0] if fila_periodo else "tu boleta de pago"

    cursor.execute("""
        SELECT b.id, b.archivo_nombre, b.archivo_contenido, b.correo_destino,
               t.nombres, t.apellidos
        FROM boletas_pago b
        JOIN trabajadores t ON t.id = b.trabajador_id
        WHERE b.periodo_id = %s AND b.estado_envio != 'ENVIADO'
    """, (periodo_id,))
    pendientes = cursor.fetchall()

    enviadas = 0
    con_error = 0

    for boleta_id, archivo_nombre, contenido, correo_destino, nombres, apellidos in pendientes:
        if not correo_destino:
            cursor.execute("""
                UPDATE boletas_pago SET estado_envio = 'ERROR', error_detalle = %s
                WHERE id = %s
            """, ("No hay correo de destino configurado", boleta_id))
            con_error += 1
            continue

        try:
            enviar_correo_con_adjunto_graph(
                access_token=access_token,
                destino=correo_destino,
                asunto=f"Boleta de pago - {nombre_periodo}",
                cuerpo=(
                    f"Hola {nombres},\n\n"
                    f"Adjuntamos tu boleta de pago correspondiente a {nombre_periodo}.\n\n"
                    f"Ante cualquier consulta sobre tu boleta, por favor comunícate con administración.\n\n"
                    f"Saludos."
                ),
                nombre_archivo=archivo_nombre,
                contenido_bytes=contenido
            )
            cursor.execute("""
                UPDATE boletas_pago SET estado_envio = 'ENVIADO', error_detalle = NULL, enviado_en = %s
                WHERE id = %s
            """, (datetime.now(), boleta_id))
            enviadas += 1

        except Exception as error:
            cursor.execute("""
                UPDATE boletas_pago SET estado_envio = 'ERROR', error_detalle = %s
                WHERE id = %s
            """, (str(error), boleta_id))
            con_error += 1

    conexion.commit()
    cursor.close()
    conexion.close()

    return {"enviadas": enviadas, "con_error": con_error, "sin_token": False}


@boletas_bp.route("/boletas/<int:periodo_id>/enviar")
@login_requerido
def enviar_boletas_periodo(periodo_id):
    """Esto es una navegacion de pagina real (no una llamada AJAX), a
    proposito: si hace falta iniciar sesion en Microsoft, el navegador
    tiene que poder seguir la redireccion de verdad hasta login.microsoftonline.com,
    algo que un fetch() en JavaScript no puede hacer."""
    access_token = obtener_token_valido()

    if not access_token:
        # Guardamos que accion retomar apenas vuelva del login, para que
        # el envio se complete solo sin que la persona tenga que volver
        # a presionar "Enviar" una segunda vez.
        session["ms_next_action"] = {"tipo": "enviar_periodo", "periodo_id": periodo_id}
        return redirect(url_for("microsoft_auth.iniciar_login_microsoft"))

    resultado = _enviar_boletas_periodo(periodo_id)
    return redirect(url_for(
        "boletas.pagina_periodo", periodo_id=periodo_id,
        enviadas=resultado["enviadas"], con_error=resultado["con_error"]
    ))
