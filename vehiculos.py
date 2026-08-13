# vehiculos.py
# Modulo de vehiculos de la empresa (propios o alquilados):
# - Datos generales, tipo de adquisicion, conductor asignado
# - Carpeta de documentos con tipo libre (SOAT, revision tecnica, tarjeta
#   de propiedad, etc.), cada uno con su propio PDF y fecha de
#   vencimiento -- el sistema calcula solo cuanto falta para que expire.

from datetime import date, datetime

from flask import Blueprint, request, render_template, jsonify, Response, abort

from auth import login_requerido
from db import obtener_conexion

vehiculos_bp = Blueprint("vehiculos", __name__)

TAMANO_MAXIMO_PDF = 15 * 1024 * 1024  # 15 MB
DIAS_ALERTA_POR_VENCER = 30

ESTADOS_VEHICULO = ("ACTIVO", "MANTENIMIENTO", "VENDIDO", "BAJA")
TIPOS_ADQUISICION = ("COMPRA", "ALQUILER")


def _psycopg2_binary(contenido_bytes):
    import psycopg2
    return psycopg2.Binary(contenido_bytes)


def _estado_documento(fecha_vencimiento):
    """Calcula el estado de un documento segun su fecha de vencimiento:
    vencido / por_vencer (30 dias o menos) / vigente / sin_fecha."""
    if not fecha_vencimiento:
        return {"estado": "sin_fecha", "diasRestantes": None}

    dias_restantes = (fecha_vencimiento - date.today()).days

    if dias_restantes < 0:
        estado = "vencido"
    elif dias_restantes <= DIAS_ALERTA_POR_VENCER:
        estado = "por_vencer"
    else:
        estado = "vigente"

    return {"estado": estado, "diasRestantes": dias_restantes}


def _documento_a_dict(fila):
    doc_id, tipo, fecha_venc, archivo_nombre, subido_en = fila
    resultado = {
        "id": doc_id,
        "tipo": tipo,
        "fechaVencimiento": str(fecha_venc) if fecha_venc else None,
        "archivoNombre": archivo_nombre,
        "subidoEn": str(subido_en)
    }
    resultado.update(_estado_documento(fecha_venc))
    return resultado


# ==========================================================
# PAGINAS
# ==========================================================

@vehiculos_bp.route("/vehiculos")
@login_requerido
def pagina_vehiculos():
    return render_template("vehiculos.html", active_page="vehiculos")


@vehiculos_bp.route("/vehiculos/<int:vehiculo_id>")
@login_requerido
def pagina_vehiculo_detalle(vehiculo_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT id, placa FROM vehiculos WHERE id = %s", (vehiculo_id,))
    fila = cursor.fetchone()
    cursor.close()
    conexion.close()

    if not fila:
        abort(404)

    return render_template(
        "vehiculo_detalle.html",
        vehiculo={"id": fila[0], "placa": fila[1]},
        active_page="vehiculos"
    )


# ==========================================================
# API: listado y creacion
# ==========================================================

@vehiculos_bp.route("/api/vehiculos")
@login_requerido
def api_listar_vehiculos():
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT
            v.id, v.placa, v.marca, v.modelo, v.tipo, v.tipo_adquisicion, v.estado,
            t.nombres, t.apellidos
        FROM vehiculos v
        LEFT JOIN trabajadores t ON t.id = v.conductor_id
        ORDER BY (v.estado = 'BAJA'), v.placa
    """)
    filas_vehiculos = cursor.fetchall()

    vehiculos = []
    for fila in filas_vehiculos:
        (v_id, placa, marca, modelo, tipo, tipo_adq, estado, cond_nombres, cond_apellidos) = fila

        # El documento "mas urgente" del vehiculo, para mostrar un solo
        # indicador en la lista (el resto se ve en el detalle).
        cursor.execute("""
            SELECT tipo, fecha_vencimiento
            FROM vehiculos_documentos
            WHERE vehiculo_id = %s AND fecha_vencimiento IS NOT NULL
            ORDER BY fecha_vencimiento ASC
            LIMIT 1
        """, (v_id,))
        fila_doc = cursor.fetchone()

        documento_urgente = None
        if fila_doc:
            doc_tipo, doc_fecha = fila_doc
            estado_doc = _estado_documento(doc_fecha)
            documento_urgente = {
                "tipo": doc_tipo,
                "fechaVencimiento": str(doc_fecha),
                **estado_doc
            }

        vehiculos.append({
            "id": v_id,
            "placa": placa,
            "marca": marca,
            "modelo": modelo,
            "tipo": tipo,
            "tipoAdquisicion": tipo_adq,
            "estado": estado,
            "conductor": f"{cond_nombres} {cond_apellidos}" if cond_nombres else None,
            "documentoUrgente": documento_urgente
        })

    cursor.close()
    conexion.close()
    return jsonify({"vehiculos": vehiculos})


@vehiculos_bp.route("/api/vehiculos", methods=["POST"])
@login_requerido
def api_crear_vehiculo():
    datos = request.get_json(silent=True) or {}
    placa = (datos.get("placa") or "").strip().upper()

    if not placa:
        return jsonify({"error": "La placa es obligatoria"}), 400

    tipo_adquisicion = (datos.get("tipoAdquisicion") or "COMPRA").strip().upper()
    if tipo_adquisicion not in TIPOS_ADQUISICION:
        tipo_adquisicion = "COMPRA"

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT id FROM vehiculos WHERE placa = %s", (placa,))
        if cursor.fetchone():
            return jsonify({"error": "Ya existe un vehículo con esa placa"}), 400

        cursor.execute("""
            INSERT INTO vehiculos (
                placa, marca, modelo, anio, color, tipo, tipo_adquisicion,
                fecha_adquisicion, conductor_id, estado,
                alquiler_proveedor, alquiler_fecha_fin, observaciones, creado_en
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVO', %s, %s, %s, %s)
            RETURNING id
        """, (
            placa,
            (datos.get("marca") or "").strip(),
            (datos.get("modelo") or "").strip(),
            datos.get("anio") or None,
            (datos.get("color") or "").strip(),
            (datos.get("tipo") or "").strip(),
            tipo_adquisicion,
            datos.get("fechaAdquisicion") or None,
            datos.get("conductorId") or None,
            (datos.get("alquilerProveedor") or "").strip() or None,
            datos.get("alquilerFechaFin") or None,
            (datos.get("observaciones") or "").strip(),
            datetime.now()
        ))
        vehiculo_id = cursor.fetchone()[0]
        conexion.commit()
        return jsonify({"ok": True, "id": vehiculo_id}), 201
    except Exception as error:
        conexion.rollback()
        print("ERROR CREANDO VEHÍCULO:", error)
        return jsonify({"error": "No se pudo crear el vehículo"}), 500
    finally:
        cursor.close()
        conexion.close()


# ==========================================================
# API: detalle, edicion y eliminacion
# ==========================================================

@vehiculos_bp.route("/api/vehiculos/<int:vehiculo_id>")
@login_requerido
def api_detalle_vehiculo(vehiculo_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT
            v.id, v.placa, v.marca, v.modelo, v.anio, v.color, v.tipo,
            v.tipo_adquisicion, v.fecha_adquisicion, v.conductor_id,
            v.estado, v.alquiler_proveedor, v.alquiler_fecha_fin, v.observaciones,
            t.nombres, t.apellidos
        FROM vehiculos v
        LEFT JOIN trabajadores t ON t.id = v.conductor_id
        WHERE v.id = %s
    """, (vehiculo_id,))
    fila = cursor.fetchone()

    if not fila:
        cursor.close()
        conexion.close()
        return jsonify({"error": "Vehículo no encontrado"}), 404

    (v_id, placa, marca, modelo, anio, color, tipo, tipo_adq, fecha_adq,
     conductor_id, estado, alquiler_prov, alquiler_fin, observaciones,
     cond_nombres, cond_apellidos) = fila

    vehiculo = {
        "id": v_id, "placa": placa, "marca": marca, "modelo": modelo,
        "anio": anio, "color": color, "tipo": tipo,
        "tipoAdquisicion": tipo_adq,
        "fechaAdquisicion": str(fecha_adq) if fecha_adq else None,
        "conductorId": conductor_id,
        "conductorNombre": f"{cond_nombres} {cond_apellidos}" if cond_nombres else None,
        "estado": estado,
        "alquilerProveedor": alquiler_prov,
        "alquilerFechaFin": str(alquiler_fin) if alquiler_fin else None,
        "observaciones": observaciones
    }

    cursor.execute("""
        SELECT id, tipo, fecha_vencimiento, archivo_nombre, subido_en
        FROM vehiculos_documentos
        WHERE vehiculo_id = %s
        ORDER BY fecha_vencimiento IS NULL, fecha_vencimiento DESC, subido_en DESC
    """, (vehiculo_id,))
    documentos = [_documento_a_dict(f) for f in cursor.fetchall()]

    cursor.close()
    conexion.close()

    return jsonify({"vehiculo": vehiculo, "documentos": documentos})


@vehiculos_bp.route("/api/vehiculos/<int:vehiculo_id>", methods=["PUT"])
@login_requerido
def api_actualizar_vehiculo(vehiculo_id):
    datos = request.get_json(silent=True) or {}
    placa = (datos.get("placa") or "").strip().upper()

    if not placa:
        return jsonify({"error": "La placa es obligatoria"}), 400

    estado = (datos.get("estado") or "ACTIVO").strip().upper()
    if estado not in ESTADOS_VEHICULO:
        estado = "ACTIVO"

    tipo_adquisicion = (datos.get("tipoAdquisicion") or "COMPRA").strip().upper()
    if tipo_adquisicion not in TIPOS_ADQUISICION:
        tipo_adquisicion = "COMPRA"

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute(
            "SELECT id FROM vehiculos WHERE placa = %s AND id <> %s", (placa, vehiculo_id)
        )
        if cursor.fetchone():
            return jsonify({"error": "Esa placa ya pertenece a otro vehículo"}), 400

        cursor.execute("""
            UPDATE vehiculos SET
                placa = %s, marca = %s, modelo = %s, anio = %s, color = %s, tipo = %s,
                tipo_adquisicion = %s, fecha_adquisicion = %s, conductor_id = %s,
                estado = %s, alquiler_proveedor = %s, alquiler_fecha_fin = %s,
                observaciones = %s
            WHERE id = %s
        """, (
            placa,
            (datos.get("marca") or "").strip(),
            (datos.get("modelo") or "").strip(),
            datos.get("anio") or None,
            (datos.get("color") or "").strip(),
            (datos.get("tipo") or "").strip(),
            tipo_adquisicion,
            datos.get("fechaAdquisicion") or None,
            datos.get("conductorId") or None,
            estado,
            (datos.get("alquilerProveedor") or "").strip() or None,
            datos.get("alquilerFechaFin") or None,
            (datos.get("observaciones") or "").strip(),
            vehiculo_id
        ))

        if cursor.rowcount == 0:
            conexion.rollback()
            return jsonify({"error": "Vehículo no encontrado"}), 404

        conexion.commit()
        return jsonify({"ok": True})
    except Exception as error:
        conexion.rollback()
        print("ERROR ACTUALIZANDO VEHÍCULO:", error)
        return jsonify({"error": "No se pudo actualizar el vehículo"}), 500
    finally:
        cursor.close()
        conexion.close()


@vehiculos_bp.route("/api/vehiculos/<int:vehiculo_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_vehiculo(vehiculo_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM vehiculos WHERE id = %s", (vehiculo_id,))
    eliminado = cursor.rowcount > 0
    conexion.commit()
    cursor.close()
    conexion.close()

    if not eliminado:
        return jsonify({"error": "Vehículo no encontrado"}), 404
    return jsonify({"ok": True})


# ==========================================================
# API: documentos del vehiculo
# ==========================================================

@vehiculos_bp.route("/api/vehiculos/<int:vehiculo_id>/documentos", methods=["POST"])
@login_requerido
def api_subir_documento(vehiculo_id):
    tipo = (request.form.get("tipo") or "").strip()
    fecha_vencimiento = (request.form.get("fechaVencimiento") or "").strip() or None
    archivo = request.files.get("archivo")

    if not tipo:
        return jsonify({"error": "Indica el tipo de documento (ej. SOAT, Revisión técnica)"}), 400

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
        cursor.execute("SELECT id FROM vehiculos WHERE id = %s", (vehiculo_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Vehículo no encontrado"}), 404

        cursor.execute("""
            INSERT INTO vehiculos_documentos (
                vehiculo_id, tipo, fecha_vencimiento, archivo_nombre, archivo_contenido, subido_en
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            vehiculo_id, tipo, fecha_vencimiento, archivo.filename,
            _psycopg2_binary(contenido), datetime.now()
        ))
        doc_id = cursor.fetchone()[0]
        conexion.commit()
        return jsonify({"ok": True, "id": doc_id}), 201
    except Exception as error:
        conexion.rollback()
        print("ERROR SUBIENDO DOCUMENTO DE VEHÍCULO:", error)
        return jsonify({"error": "No se pudo subir el documento"}), 500
    finally:
        cursor.close()
        conexion.close()


@vehiculos_bp.route("/api/vehiculos/documentos/<int:doc_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_documento(doc_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM vehiculos_documentos WHERE id = %s", (doc_id,))
    eliminado = cursor.rowcount > 0
    conexion.commit()
    cursor.close()
    conexion.close()

    if not eliminado:
        return jsonify({"error": "Documento no encontrado"}), 404
    return jsonify({"ok": True})


@vehiculos_bp.route("/documentos-vehiculo/<int:doc_id>")
@login_requerido
def servir_documento_vehiculo(doc_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        "SELECT archivo_nombre, archivo_contenido FROM vehiculos_documentos WHERE id = %s",
        (doc_id,)
    )
    fila = cursor.fetchone()
    cursor.close()
    conexion.close()

    if not fila:
        abort(404)

    nombre, contenido = fila
    return Response(
        bytes(contenido),
        mimetype="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}"'}
    )
