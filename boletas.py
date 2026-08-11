# boletas.py
# Modulo de boletas de pago:
# - Se crea un "periodo de pago" (ej. "1ra quincena - Agosto 2026")
# - Se sube el PDF de la boleta de cada trabajador para ese periodo
# - El envio real por correo NO lo hace este servidor: lo hace un script
#   que corre en una computadora con Outlook de escritorio instalado y
#   con sesion iniciada (usa win32com, igual que el script original).
#   Ese script se conecta a esta API para pedir las boletas pendientes de
#   un periodo (con el PDF incluido) y, despues de enviarlas via Outlook,
#   le avisa a este servidor el resultado de cada una.
#
# Por que asi: el servidor esta en Railway (Linux, sin Outlook de
# escritorio posible), y no hay forma de automatizar el envio "desde la
# nube" sin un admin de Microsoft 365 disponible para habilitar OAuth.
# Esta app se queda con la parte de administrar (periodos, PDFs, estados)
# y delega el envio en si a la maquina que sí tiene Outlook.

from datetime import datetime
import base64

from flask import Blueprint, request, render_template, jsonify, session, abort

from auth import login_requerido
from db import obtener_conexion

boletas_bp = Blueprint("boletas", __name__)

TAMANO_MAXIMO_PDF = 15 * 1024 * 1024  # 15 MB

ESTADOS_VALIDOS = ("PENDIENTE", "ENVIADO", "ERROR")


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

    return render_template("boleta_periodo.html", periodo=periodo, active_page="boletas")


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
# (usado por la pagina web para armar la tabla)
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
# API usada por el script local de envio (Outlook + win32com)
# ==========================================================

@boletas_bp.route("/api/periodos/<int:periodo_id>/pendientes")
@login_requerido
def api_boletas_pendientes(periodo_id):
    """Devuelve las boletas de este periodo que todavia no se marcaron
    como ENVIADO, con el PDF incluido en base64, para que el script local
    (con Outlook) las descargue y las mande."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("SELECT nombre FROM periodos_pago WHERE id = %s", (periodo_id,))
    fila_periodo = cursor.fetchone()
    if not fila_periodo:
        cursor.close()
        conexion.close()
        return jsonify({"error": "Periodo no encontrado"}), 404
    nombre_periodo = fila_periodo[0]

    cursor.execute("""
        SELECT b.id, b.archivo_nombre, b.archivo_contenido, b.correo_destino,
               t.nombres, t.apellidos
        FROM boletas_pago b
        JOIN trabajadores t ON t.id = b.trabajador_id
        WHERE b.periodo_id = %s AND b.estado_envio != 'ENVIADO'
        ORDER BY t.nombres, t.apellidos
    """, (periodo_id,))

    pendientes = []
    for boleta_id, archivo_nombre, contenido, correo_destino, nombres, apellidos in cursor.fetchall():
        pendientes.append({
            "id": boleta_id,
            "nombre_trabajador": f"{nombres} {apellidos}",
            "correo_destino": correo_destino,
            "archivo_nombre": archivo_nombre,
            "archivo_base64": base64.b64encode(bytes(contenido)).decode("ascii"),
            "periodo_nombre": nombre_periodo
        })

    cursor.close()
    conexion.close()

    return jsonify({"periodo_nombre": nombre_periodo, "pendientes": pendientes})


@boletas_bp.route("/api/boletas/<int:boleta_id>/estado", methods=["POST"])
@login_requerido
def api_actualizar_estado_boleta(boleta_id):
    """El script local llama esto despues de intentar enviar cada boleta
    por Outlook, para avisar si funciono o no."""
    datos = request.get_json(silent=True) or {}
    estado = (datos.get("estado") or "").strip().upper()
    detalle = (datos.get("detalle") or "").strip() or None

    if estado not in ESTADOS_VALIDOS:
        return jsonify({"error": f"Estado inválido. Debe ser uno de: {', '.join(ESTADOS_VALIDOS)}"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("""
            UPDATE boletas_pago SET
                estado_envio = %s,
                error_detalle = %s,
                enviado_en = %s
            WHERE id = %s
        """, (
            estado,
            detalle if estado == "ERROR" else None,
            datetime.now() if estado == "ENVIADO" else None,
            boleta_id
        ))

        if cursor.rowcount == 0:
            conexion.rollback()
            return jsonify({"error": "Boleta no encontrada"}), 404

        conexion.commit()
        return jsonify({"ok": True})
    except Exception as error:
        conexion.rollback()
        print("ERROR ACTUALIZANDO ESTADO DE BOLETA:", error)
        return jsonify({"error": "No se pudo actualizar el estado"}), 500
    finally:
        cursor.close()
        conexion.close()
