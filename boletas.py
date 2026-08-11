# boletas.py
# Modulo de boletas de pago:
# - Se crea un "periodo de pago" (ej. "1ra quincena - Agosto 2026")
# - Se sube uno o varios PDFs por trabajador para ese periodo
# - Se elige a que correo(s) del trabajador se le manda (personal,
#   corporativo, o ambos)
# - El envio real por correo NO lo hace este servidor: lo hace un script
#   que corre en una computadora con Outlook de escritorio instalado y
#   con sesion iniciada (usa win32com). Ese script se conecta a esta API
#   para pedir las boletas pendientes de un periodo (con sus PDFs) y,
#   despues de enviarlas via Outlook, le avisa a este servidor el
#   resultado de cada una.

from datetime import datetime
import base64

from flask import Blueprint, request, render_template, jsonify, session, abort

from auth import login_requerido
from db import obtener_conexion

boletas_bp = Blueprint("boletas", __name__)

TAMANO_MAXIMO_PDF = 15 * 1024 * 1024  # 15 MB por archivo

ESTADOS_VALIDOS = ("PENDIENTE", "ENVIADO", "ERROR")


def _psycopg2_binary(contenido_bytes):
    import psycopg2
    return psycopg2.Binary(contenido_bytes)


def _correo_sugerido(email_personal, email_corporativo):
    """Por defecto se sugiere mandar a AMBOS correos si el trabajador
    tiene los dos registrados."""
    correos = [c for c in (email_corporativo, email_personal) if c]
    return ";".join(correos)


def _obtener_o_crear_boleta(cursor, periodo_id, trabajador_id, correo_destino=None):
    """Devuelve el id de la boleta (fila 'contenedora') de este trabajador
    en este periodo, creandola si todavia no existe. Si se pasa
    correo_destino y la boleta ya existia, NO lo pisa (para eso esta
    api_actualizar_correo, que es explicito)."""
    cursor.execute(
        "SELECT id FROM boletas_pago WHERE periodo_id = %s AND trabajador_id = %s",
        (periodo_id, trabajador_id)
    )
    fila = cursor.fetchone()
    if fila:
        return fila[0]

    if correo_destino is None:
        cursor.execute("""
            SELECT email, email_corporativo FROM trabajadores WHERE id = %s
        """, (trabajador_id,))
        fila_trabajador = cursor.fetchone()
        if fila_trabajador:
            correo_destino = _correo_sugerido(fila_trabajador[0], fila_trabajador[1])

    cursor.execute("""
        INSERT INTO boletas_pago (periodo_id, trabajador_id, correo_destino, estado_envio, subido_en)
        VALUES (%s, %s, %s, 'PENDIENTE', %s)
        RETURNING id
    """, (periodo_id, trabajador_id, correo_destino, datetime.now()))
    return cursor.fetchone()[0]


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
    boleta en este periodo especifico: sus archivos PDF, a que correo(s)
    se le va a mandar, y si ya se envio."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT
            t.id, t.nombres, t.apellidos, t.email, t.email_corporativo,
            b.id AS boleta_id, b.correo_destino,
            b.estado_envio, b.error_detalle, b.enviado_en
        FROM trabajadores t
        LEFT JOIN boletas_pago b
            ON b.trabajador_id = t.id AND b.periodo_id = %s
        WHERE t.estado IS DISTINCT FROM 'INACTIVO'
        ORDER BY t.nombres, t.apellidos
    """, (periodo_id,))
    filas_trabajadores = cursor.fetchall()

    # Archivos de todas las boletas de este periodo, de una sola consulta
    cursor.execute("""
        SELECT a.boleta_id, a.id, a.archivo_nombre
        FROM boletas_pago_archivos a
        JOIN boletas_pago b ON b.id = a.boleta_id
        WHERE b.periodo_id = %s
        ORDER BY a.subido_en
    """, (periodo_id,))
    archivos_por_boleta = {}
    for boleta_id, archivo_id, archivo_nombre in cursor.fetchall():
        archivos_por_boleta.setdefault(boleta_id, []).append(
            {"id": archivo_id, "nombre": archivo_nombre}
        )

    trabajadores = []
    for fila in filas_trabajadores:
        (t_id, nombres, apellidos, email, email_corp,
         boleta_id, correo_destino, estado_envio, error_detalle, enviado_en) = fila

        correo_final = correo_destino if correo_destino is not None else _correo_sugerido(email, email_corp)

        trabajadores.append({
            "id": t_id,
            "nombre": f"{nombres} {apellidos}",
            "email_personal": email,
            "email_corporativo": email_corp,
            "boleta_id": boleta_id,
            "archivos": archivos_por_boleta.get(boleta_id, []),
            "correo_destino": correo_final,
            "estado_envio": estado_envio,
            "error_detalle": error_detalle,
            "enviado_en": str(enviado_en) if enviado_en else None
        })

    cursor.close()
    conexion.close()
    return jsonify({"trabajadores": trabajadores})


@boletas_bp.route("/api/periodos/<int:periodo_id>/boletas", methods=["POST"])
@login_requerido
def api_subir_boleta(periodo_id):
    """Agrega uno o mas PDFs a la boleta de un trabajador en este periodo.
    Si la boleta no existia, se crea (con el correo sugerido por defecto,
    a menos que se mande uno explicito). Los archivos se ACUMULAN, no
    reemplazan a los que ya hubiera."""
    trabajador_id = request.form.get("trabajador_id", type=int)
    correo_destino = (request.form.get("correo_destino") or "").strip() or None
    archivos = [a for a in request.files.getlist("archivos") if a and a.filename]

    if not trabajador_id:
        return jsonify({"error": "Falta el trabajador"}), 400

    if not archivos:
        return jsonify({"error": "No se recibió ningún archivo"}), 400

    for archivo in archivos:
        if not archivo.filename.lower().endswith(".pdf"):
            return jsonify({"error": f'"{archivo.filename}" no es un PDF'}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        boleta_id = _obtener_o_crear_boleta(cursor, periodo_id, trabajador_id, correo_destino)

        # Si se estaba reintentando un envio que dio error, al agregar un
        # archivo nuevo lo volvemos a dejar en Pendiente.
        cursor.execute("""
            UPDATE boletas_pago
            SET estado_envio = 'PENDIENTE', error_detalle = NULL, enviado_en = NULL
            WHERE id = %s
        """, (boleta_id,))

        for archivo in archivos:
            contenido = archivo.read()
            if len(contenido) > TAMANO_MAXIMO_PDF:
                conexion.rollback()
                return jsonify({"error": f'"{archivo.filename}" supera los 15MB'}), 400

            cursor.execute("""
                INSERT INTO boletas_pago_archivos (boleta_id, archivo_nombre, archivo_contenido, subido_en)
                VALUES (%s, %s, %s, %s)
            """, (boleta_id, archivo.filename, _psycopg2_binary(contenido), datetime.now()))

        conexion.commit()
        return jsonify({"ok": True, "id": boleta_id})
    except Exception as error:
        conexion.rollback()
        print("ERROR SUBIENDO BOLETA:", error)
        return jsonify({"error": "No se pudo subir la boleta"}), 500
    finally:
        cursor.close()
        conexion.close()


@boletas_bp.route("/api/periodos/<int:periodo_id>/correo", methods=["POST"])
@login_requerido
def api_actualizar_correo(periodo_id):
    """Cambia a que correo(s) se le va a mandar la boleta a un trabajador
    (se llama cuando se marcan/desmarcan los checkboxes de Personal /
    Corporativo). No toca los archivos ya subidos."""
    datos = request.get_json(silent=True) or {}
    trabajador_id = datos.get("trabajadorId")
    correo_destino = (datos.get("correoDestino") or "").strip()

    if not trabajador_id:
        return jsonify({"error": "Falta el trabajador"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        boleta_id = _obtener_o_crear_boleta(cursor, periodo_id, trabajador_id, correo_destino)
        cursor.execute(
            "UPDATE boletas_pago SET correo_destino = %s WHERE id = %s",
            (correo_destino, boleta_id)
        )
        conexion.commit()
        return jsonify({"ok": True})
    except Exception as error:
        conexion.rollback()
        print("ERROR ACTUALIZANDO CORREO:", error)
        return jsonify({"error": "No se pudo actualizar el correo"}), 500
    finally:
        cursor.close()
        conexion.close()


@boletas_bp.route("/api/boletas/<int:boleta_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_boleta(boleta_id):
    """Elimina la boleta completa (todos sus archivos, por el ON DELETE
    CASCADE)."""
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


@boletas_bp.route("/api/boletas/<int:boleta_id>/archivos/<int:archivo_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_archivo(boleta_id, archivo_id):
    """Elimina UN solo PDF de una boleta, dejando los demas intactos."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        "DELETE FROM boletas_pago_archivos WHERE id = %s AND boleta_id = %s",
        (archivo_id, boleta_id)
    )
    eliminado = cursor.rowcount > 0
    conexion.commit()
    cursor.close()
    conexion.close()

    if not eliminado:
        return jsonify({"error": "Archivo no encontrado"}), 404
    return jsonify({"ok": True})


# ==========================================================
# API usada por el script local de envio (Outlook + win32com)
# ==========================================================

@boletas_bp.route("/api/periodos/<int:periodo_id>/pendientes")
@login_requerido
def api_boletas_pendientes(periodo_id):
    """Devuelve las boletas de este periodo que todavia no se marcaron
    como ENVIADO, con TODOS sus PDFs incluidos en base64, para que el
    script local (con Outlook) las descargue y las mande."""
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
        SELECT b.id, b.correo_destino, t.nombres, t.apellidos
        FROM boletas_pago b
        JOIN trabajadores t ON t.id = b.trabajador_id
        WHERE b.periodo_id = %s AND b.estado_envio != 'ENVIADO'
        ORDER BY t.nombres, t.apellidos
    """, (periodo_id,))
    filas_boletas = cursor.fetchall()

    pendientes = []
    for boleta_id, correo_destino, nombres, apellidos in filas_boletas:
        cursor.execute("""
            SELECT archivo_nombre, archivo_contenido
            FROM boletas_pago_archivos
            WHERE boleta_id = %s
            ORDER BY subido_en
        """, (boleta_id,))
        archivos = [
            {
                "nombre": nombre_archivo,
                "contenido_base64": base64.b64encode(bytes(contenido)).decode("ascii")
            }
            for nombre_archivo, contenido in cursor.fetchall()
        ]

        pendientes.append({
            "id": boleta_id,
            "nombre_trabajador": f"{nombres} {apellidos}",
            "correo_destino": correo_destino,
            "archivos": archivos,
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
