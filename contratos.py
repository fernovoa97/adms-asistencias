# contratos.py
# Registro general de contratos de la empresa: laborales, inmuebles, seguros,
# servicios y comerciales, con sus adendas, cierre manual y alertas.
#
# El estado nunca se guarda, se calcula al leer:
#   finalizado  -> se cerro manualmente
#   vencido     -> paso la fecha de fin sin cierre
#   por_vencer  -> faltan 90 dias o menos
#   vigente     -> el resto (incluye contratos sin fecha de fin)

from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
import re

import psycopg2
from flask import Blueprint, abort, jsonify, render_template, request, send_file, session

from auth import login_requerido
from db import obtener_conexion
from validaciones import hoy_local, parsear_fecha

contratos_bp = Blueprint("contratos", __name__)

TAMANO_MAXIMO_PDF = 25 * 1024 * 1024  # 25 MB
DIAS_POR_VENCER = 90
TRAMOS_ALERTA = (30, 60, 90)
MONEDAS = ("PEN", "USD")
TIPOS_ADENDA = ("Ampliación", "Modificación", "Renovación")
TIPOS_ADENDA_CON_FECHA = ("Ampliación", "Renovación")

MODULOS = {
    "laborales": {
        "nombre": "Contratos laborales",
        "area": "RR. HH.",
        "descripcion": "Personal administrativo, operativo y destacado en mina.",
        "categorias": ["Personal administrativo", "Personal operativo", "Personal destacado en mina"]
    },
    "inmuebles": {
        "nombre": "Alquileres e inmuebles",
        "area": "Administración",
        "descripcion": "Megacentro, almacenes, cocheras y otros espacios.",
        "categorias": ["Megacentro", "Almacén", "Cochera", "Otro espacio"]
    },
    "seguros": {
        "nombre": "Seguros y pólizas",
        "area": "Administración",
        "descripcion": "SCTR Salud, SCTR Pensión, Vida Ley, EPS y seguros vehiculares.",
        "categorias": ["SCTR Salud", "SCTR Pensión", "Vida Ley", "EPS", "Seguro vehicular"]
    },
    "servicios": {
        "nombre": "Servicios y proveedores",
        "area": "Logística",
        "descripcion": "Transporte, mantenimiento, logística, servicios externos y terceros.",
        "categorias": ["Transporte", "Mantenimiento", "Logística", "Servicios externos", "Terceros"]
    },
    "comerciales": {
        "nombre": "Contratos comerciales",
        "area": "Ventas",
        "descripcion": "Clientes, acuerdos comerciales y contratos de operaciones mineras.",
        "categorias": ["Cliente", "Acuerdo comercial", "Operaciones mineras"]
    }
}

ADENDA_FORMALIZADA = "a.fecha_suscripcion IS NOT NULL AND a.archivo_contenido IS NOT NULL"

SELECT_CONTRATO = f"""
    SELECT c.id, c.numero, c.modulo, c.categoria, c.contraparte_nombre, c.contraparte_ruc,
           c.objeto, c.fecha_suscripcion, c.inicio_vigencia, c.fin_vigencia, c.importe,
           c.moneda, c.responsable, c.trabajador_id, c.archivo_nombre, c.fecha_cierre,
           c.motivo_cierre, c.cerrado_por,
           (
               SELECT a.nuevo_fin FROM contratos_adendas a
               WHERE a.contrato_id = c.id AND a.nuevo_fin IS NOT NULL AND {ADENDA_FORMALIZADA}
               ORDER BY a.numero DESC LIMIT 1
           ) AS fin_adenda,
           (
               SELECT COUNT(*) FROM contratos_adendas a
               WHERE a.contrato_id = c.id AND NOT ({ADENDA_FORMALIZADA})
           ) AS adendas_pendientes
    FROM contratos c
"""


def estado_contrato(fecha_cierre, fin_vigencia, hoy=None):
    """Devuelve (estado, dias_restantes)."""
    if fecha_cierre:
        return "finalizado", None
    if not fin_vigencia:
        return "vigente", None

    dias = (fin_vigencia - (hoy or hoy_local())).days
    if dias < 0:
        return "vencido", dias
    if dias <= DIAS_POR_VENCER:
        return "por_vencer", dias
    return "vigente", dias


def tramo_alerta(dias):
    """30, 60 o 90: el primer tramo en el que caen los dias restantes."""
    return next(tramo for tramo in TRAMOS_ALERTA if dias <= tramo)


def _fecha_str(valor):
    return str(valor) if valor else None


def _contrato_a_dict(fila):
    (c_id, numero, modulo, categoria, nombre, ruc, objeto, suscripcion, inicio, fin,
     importe, moneda, responsable, trabajador_id, archivo, cierre, motivo, cerrado_por,
     fin_adenda, adendas_pendientes) = fila

    fin_efectivo = fin_adenda or fin
    estado, dias = estado_contrato(cierre, fin_efectivo)

    return {
        "id": c_id,
        "numero": numero,
        "modulo": modulo,
        "moduloNombre": MODULOS[modulo]["nombre"],
        "categoria": categoria,
        "contraparteNombre": nombre,
        "contraparteRuc": ruc,
        "objeto": objeto,
        "fechaSuscripcion": _fecha_str(suscripcion),
        "inicioVigencia": str(inicio),
        "finVigencia": _fecha_str(fin),
        "finEfectivo": _fecha_str(fin_efectivo),
        "importe": float(importe) if importe is not None else None,
        "moneda": moneda,
        "responsable": responsable,
        "trabajadorId": trabajador_id,
        "tieneDocumento": bool(archivo),
        "documentoNombre": archivo,
        "fechaCierre": _fecha_str(cierre),
        "motivoCierre": motivo,
        "cerradoPor": cerrado_por,
        "adendasPendientes": adendas_pendientes,
        "estado": estado,
        "diasRestantes": dias
    }


def _listar_contratos(cursor):
    cursor.execute(SELECT_CONTRATO + " ORDER BY c.id DESC")
    return [_contrato_a_dict(f) for f in cursor.fetchall()]


def _obtener_contrato(cursor, contrato_id):
    cursor.execute(SELECT_CONTRATO + " WHERE c.id = %s", (contrato_id,))
    fila = cursor.fetchone()
    return _contrato_a_dict(fila) if fila else None


def _validar_contrato(datos, modulo):
    """Devuelve (valores, error): si hay error, valores es None."""
    categoria = (datos.get("categoria") or "").strip()
    nombre = (datos.get("contraparteNombre") or "").strip()
    ruc = (datos.get("contraparteRuc") or "").strip()
    objeto = (datos.get("objeto") or "").strip()
    responsable = (datos.get("responsable") or "").strip()
    moneda = (datos.get("moneda") or "PEN").strip().upper()

    if categoria not in MODULOS[modulo]["categorias"]:
        return None, "Selecciona una categoría válida"
    if not nombre:
        return None, "La empresa o contraparte es obligatoria"
    if ruc and not re.fullmatch(r"\d{11}", ruc):
        return None, "El RUC debe tener 11 dígitos"
    if not objeto:
        return None, "El objeto del contrato es obligatorio"
    if not responsable:
        return None, "El responsable interno es obligatorio"
    if moneda not in MONEDAS:
        return None, "Moneda no válida"

    try:
        suscripcion = parsear_fecha(datos.get("fechaSuscripcion"))
        inicio = parsear_fecha(datos.get("inicioVigencia"))
        fin = parsear_fecha(datos.get("finVigencia"))
    except ValueError:
        return None, "Las fechas no son válidas"

    if not inicio:
        return None, "El inicio de vigencia es obligatorio"
    if fin and fin < inicio:
        return None, "El fin de vigencia no puede ser anterior al inicio"

    importe = None
    importe_crudo = str(datos.get("importe") or "").strip()
    if importe_crudo:
        try:
            importe = Decimal(importe_crudo)
        except InvalidOperation:
            return None, "El importe no es válido"
        if not importe.is_finite() or importe < 0 or importe >= Decimal("1e12"):
            return None, "El importe no es válido"

    trabajador_id = None
    if modulo == "laborales" and datos.get("trabajadorId"):
        try:
            trabajador_id = int(datos.get("trabajadorId"))
        except (TypeError, ValueError):
            return None, "Trabajador no válido"

    return {
        "categoria": categoria, "nombre": nombre, "ruc": ruc or None, "objeto": objeto,
        "suscripcion": suscripcion, "inicio": inicio, "fin": fin, "importe": importe,
        "moneda": moneda, "responsable": responsable, "trabajador_id": trabajador_id
    }, None


def _leer_pdf():
    """Devuelve (nombre, contenido, error) del archivo recibido."""
    archivo = request.files.get("archivo")
    if not archivo or not archivo.filename:
        return None, None, "No se recibió ningún archivo"
    if not archivo.filename.lower().endswith(".pdf"):
        return None, None, "El archivo debe ser un PDF"
    contenido = archivo.read()
    if len(contenido) > TAMANO_MAXIMO_PDF:
        return None, None, "El archivo supera los 25MB"
    return archivo.filename, contenido, None


# ==========================================================
# PAGINAS
# ==========================================================

def _config_js():
    return {
        "modulos": MODULOS,
        "ordenModulos": list(MODULOS),  # jsonify ordena las claves alfabeticamente
        "tiposAdenda": TIPOS_ADENDA,
        "tiposAdendaConFecha": TIPOS_ADENDA_CON_FECHA
    }


@contratos_bp.route("/contratos")
@login_requerido
def pagina_resumen_contratos():
    return render_template("contratos_resumen.html", active_page="contratos_resumen", config=_config_js())


@contratos_bp.route("/contratos/modulo/<modulo>")
@login_requerido
def pagina_modulo_contratos(modulo):
    if modulo not in MODULOS:
        abort(404)
    return render_template(
        "contratos_modulo.html", active_page=f"contratos_{modulo}",
        modulo=modulo, info=MODULOS[modulo], config=_config_js()
    )


@contratos_bp.route("/contratos/finalizados")
@login_requerido
def pagina_contratos_finalizados():
    return render_template(
        "contratos_modulo.html", active_page="contratos_finalizados",
        modulo=None,
        info={"nombre": "Contratos finalizados", "area": None,
              "descripcion": "Historial y documentación de contratos concluidos."},
        config=_config_js()
    )


@contratos_bp.route("/contratos/adendas")
@login_requerido
def pagina_adendas():
    return render_template("contratos_adendas.html", active_page="contratos_adendas")


@contratos_bp.route("/contratos/<int:contrato_id>")
@login_requerido
def pagina_contrato_detalle(contrato_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("SELECT numero, modulo FROM contratos WHERE id = %s", (contrato_id,))
    fila = cursor.fetchone()
    cursor.close()
    conexion.close()

    if not fila:
        abort(404)

    return render_template(
        "contrato_detalle.html", active_page=f"contratos_{fila[1]}",
        contrato_id=contrato_id, numero=fila[0], config=_config_js()
    )


# ==========================================================
# API: resumen y alertas
# ==========================================================

def _adendas_pendientes(cursor):
    cursor.execute(f"""
        SELECT a.id, a.numero, a.tipo, a.fecha_suscripcion, a.archivo_nombre,
               c.id, c.numero, c.contraparte_nombre
        FROM contratos_adendas a
        JOIN contratos c ON c.id = a.contrato_id
        WHERE c.fecha_cierre IS NULL AND NOT ({ADENDA_FORMALIZADA})
        ORDER BY a.creado_en
    """)
    pendientes = []
    for fila in cursor.fetchall():
        falta = []
        if not fila[3]:
            falta.append("firma")
        if not fila[4]:
            falta.append("PDF")
        pendientes.append({
            "id": fila[0], "numero": fila[1], "tipo": fila[2], "falta": falta,
            "contratoId": fila[5], "contratoNumero": fila[6], "contraparte": fila[7]
        })
    return pendientes


@contratos_bp.route("/api/contratos/resumen")
@login_requerido
def api_resumen_contratos():
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    contratos = _listar_contratos(cursor)
    adendas = _adendas_pendientes(cursor)
    cursor.close()
    conexion.close()

    conteo_vacio = {"vigente": 0, "por_vencer": 0, "vencido": 0, "finalizado": 0}
    totales = dict(conteo_vacio)
    por_modulo = {clave: dict(conteo_vacio) for clave in MODULOS}

    proximos = {str(tramo): [] for tramo in TRAMOS_ALERTA}
    polizas, documentacion, vencidos = [], [], []

    for c in contratos:
        totales[c["estado"]] += 1
        por_modulo[c["modulo"]][c["estado"]] += 1

        if c["estado"] == "finalizado":
            continue

        if c["estado"] == "vencido":
            vencidos.append(c)
        elif c["estado"] == "por_vencer":
            if c["modulo"] == "seguros":
                polizas.append(c)
            else:
                proximos[str(tramo_alerta(c["diasRestantes"]))].append(c)

        pendiente = []
        if not c["fechaSuscripcion"]:
            pendiente.append("sin firma")
        if not c["tieneDocumento"]:
            pendiente.append("sin PDF")
        if pendiente:
            documentacion.append({**c, "pendiente": pendiente})

    for lista in (*proximos.values(), polizas, vencidos):
        lista.sort(key=lambda c: c["diasRestantes"])

    return jsonify({
        "totales": totales,
        "porModulo": por_modulo,
        "alertas": {
            "proximos": proximos,
            "polizas": polizas,
            "documentacion": documentacion,
            "adendas": adendas,
            "vencidos": vencidos
        }
    })


# ==========================================================
# API: contratos
# ==========================================================

@contratos_bp.route("/api/contratos")
@login_requerido
def api_listar_contratos():
    modulo = request.args.get("modulo")
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    contratos = _listar_contratos(cursor)
    cursor.close()
    conexion.close()

    if modulo:
        contratos = [c for c in contratos if c["modulo"] == modulo]
    return jsonify({"contratos": contratos})


@contratos_bp.route("/api/contratos/laborales-sin-ficha")
@login_requerido
def api_laborales_sin_ficha():
    """Colaboradores activos con contrato en su ficha personal que todavia no
    tienen ficha en este registro."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("""
        SELECT t.id, t.apellidos, t.nombres, t.cargo, t.tipo_contrato,
               t.fecha_ingreso, t.fecha_fin_contrato, t.fecha_renovacion
        FROM trabajadores t
        WHERE t.estado IS DISTINCT FROM 'INACTIVO'
          AND (t.tipo_contrato IS NOT NULL OR t.fecha_fin_contrato IS NOT NULL)
          AND NOT EXISTS (SELECT 1 FROM contratos c WHERE c.trabajador_id = t.id)
        ORDER BY t.apellidos, t.nombres
    """)
    trabajadores = [
        {
            "id": f[0], "nombre": f"{f[1]} {f[2]}", "cargo": f[3], "tipoContrato": f[4],
            "fechaIngreso": _fecha_str(f[5]), "fechaFin": _fecha_str(f[6]),
            "fechaRenovacion": _fecha_str(f[7])
        }
        for f in cursor.fetchall()
    ]
    cursor.close()
    conexion.close()
    return jsonify({"trabajadores": trabajadores})


@contratos_bp.route("/api/contratos", methods=["POST"])
@login_requerido
def api_crear_contrato():
    datos = request.get_json(silent=True) or {}
    modulo = (datos.get("modulo") or "").strip()

    if modulo not in MODULOS:
        return jsonify({"error": "Módulo no válido"}), 400

    v, error = _validar_contrato(datos, modulo)
    if error:
        return jsonify({"error": error}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        # El numero sale del propio id, asi es correlativo y no se repite
        # aunque dos personas registren contratos a la vez.
        cursor.execute("SELECT nextval(pg_get_serial_sequence('contratos', 'id'))")
        contrato_id = cursor.fetchone()[0]

        cursor.execute("""
            INSERT INTO contratos (
                id, numero, modulo, categoria, contraparte_nombre, contraparte_ruc, objeto,
                fecha_suscripcion, inicio_vigencia, fin_vigencia, importe, moneda,
                responsable, trabajador_id, creado_por, creado_en
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            contrato_id, f"CTR-{contrato_id:05d}", modulo, v["categoria"], v["nombre"], v["ruc"],
            v["objeto"], v["suscripcion"], v["inicio"], v["fin"], v["importe"], v["moneda"],
            v["responsable"], v["trabajador_id"], session.get("username"), datetime.now()
        ))
        conexion.commit()
        return jsonify({"ok": True, "id": contrato_id}), 201
    except psycopg2.errors.ForeignKeyViolation:
        conexion.rollback()
        return jsonify({"error": "Trabajador no encontrado"}), 400
    except Exception as error_bd:
        conexion.rollback()
        print("ERROR CREANDO CONTRATO:", error_bd)
        return jsonify({"error": "No se pudo crear el contrato"}), 500
    finally:
        cursor.close()
        conexion.close()


@contratos_bp.route("/api/contratos/<int:contrato_id>")
@login_requerido
def api_detalle_contrato(contrato_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    contrato = _obtener_contrato(cursor, contrato_id)

    if not contrato:
        cursor.close()
        conexion.close()
        return jsonify({"error": "Contrato no encontrado"}), 404

    cursor.execute("""
        SELECT id, numero, tipo, descripcion, fecha_suscripcion, nuevo_fin, archivo_nombre, creado_en
        FROM contratos_adendas
        WHERE contrato_id = %s
        ORDER BY numero DESC
    """, (contrato_id,))
    adendas = [
        {
            "id": f[0], "numero": f[1], "tipo": f[2], "descripcion": f[3],
            "fechaSuscripcion": _fecha_str(f[4]), "nuevoFin": _fecha_str(f[5]),
            "tieneDocumento": bool(f[6]), "formalizada": bool(f[4] and f[6]),
            "creadoEn": f[7].strftime("%Y-%m-%d %H:%M")
        }
        for f in cursor.fetchall()
    ]

    cursor.close()
    conexion.close()
    return jsonify({"contrato": contrato, "adendas": adendas})


def _contrato_abierto(cursor, contrato_id):
    """Bloquea la fila y devuelve (None, codigo) si no se puede modificar, o
    (modulo, None) si esta abierto."""
    cursor.execute(
        "SELECT modulo, fecha_cierre FROM contratos WHERE id = %s FOR UPDATE", (contrato_id,)
    )
    fila = cursor.fetchone()
    if not fila:
        return None, ("Contrato no encontrado", 404)
    if fila[1]:
        return None, ("El contrato está finalizado; reábrelo para modificarlo", 400)
    return fila[0], None


@contratos_bp.route("/api/contratos/<int:contrato_id>", methods=["PUT"])
@login_requerido
def api_actualizar_contrato(contrato_id):
    datos = request.get_json(silent=True) or {}
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        modulo, problema = _contrato_abierto(cursor, contrato_id)
        if problema:
            return jsonify({"error": problema[0]}), problema[1]

        v, error = _validar_contrato(datos, modulo)
        if error:
            return jsonify({"error": error}), 400

        cursor.execute("""
            UPDATE contratos SET
                categoria = %s, contraparte_nombre = %s, contraparte_ruc = %s, objeto = %s,
                fecha_suscripcion = %s, inicio_vigencia = %s, fin_vigencia = %s, importe = %s,
                moneda = %s, responsable = %s, trabajador_id = %s
            WHERE id = %s
        """, (
            v["categoria"], v["nombre"], v["ruc"], v["objeto"], v["suscripcion"], v["inicio"],
            v["fin"], v["importe"], v["moneda"], v["responsable"], v["trabajador_id"], contrato_id
        ))
        conexion.commit()
        return jsonify({"ok": True, "id": contrato_id})
    except psycopg2.errors.ForeignKeyViolation:
        conexion.rollback()
        return jsonify({"error": "Trabajador no encontrado"}), 400
    except Exception as error_bd:
        conexion.rollback()
        print("ERROR ACTUALIZANDO CONTRATO:", error_bd)
        return jsonify({"error": "No se pudo actualizar el contrato"}), 500
    finally:
        cursor.close()
        conexion.close()


@contratos_bp.route("/api/contratos/<int:contrato_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_contrato(contrato_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM contratos WHERE id = %s", (contrato_id,))
    eliminado = cursor.rowcount > 0
    conexion.commit()
    cursor.close()
    conexion.close()

    if not eliminado:
        return jsonify({"error": "Contrato no encontrado"}), 404
    return jsonify({"ok": True})


@contratos_bp.route("/api/contratos/<int:contrato_id>/cerrar", methods=["POST"])
@login_requerido
def api_cerrar_contrato(contrato_id):
    datos = request.get_json(silent=True) or {}
    try:
        fecha_cierre = parsear_fecha(datos.get("fechaCierre"))
    except ValueError:
        return jsonify({"error": "La fecha de cierre no es válida"}), 400

    if not fecha_cierre:
        return jsonify({"error": "La fecha de cierre es obligatoria"}), 400
    if fecha_cierre > hoy_local():
        return jsonify({"error": "La fecha de cierre no puede ser futura"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        _, problema = _contrato_abierto(cursor, contrato_id)
        if problema:
            return jsonify({"error": problema[0]}), problema[1]

        cursor.execute("""
            UPDATE contratos SET fecha_cierre = %s, motivo_cierre = %s, cerrado_por = %s
            WHERE id = %s
        """, (
            fecha_cierre, (datos.get("motivo") or "").strip() or None,
            session.get("username"), contrato_id
        ))
        conexion.commit()
        return jsonify({"ok": True})
    except Exception as error_bd:
        conexion.rollback()
        print("ERROR CERRANDO CONTRATO:", error_bd)
        return jsonify({"error": "No se pudo cerrar el contrato"}), 500
    finally:
        cursor.close()
        conexion.close()


@contratos_bp.route("/api/contratos/<int:contrato_id>/reabrir", methods=["POST"])
@login_requerido
def api_reabrir_contrato(contrato_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("""
        UPDATE contratos SET fecha_cierre = NULL, motivo_cierre = NULL, cerrado_por = NULL
        WHERE id = %s
    """, (contrato_id,))
    encontrado = cursor.rowcount > 0
    conexion.commit()
    cursor.close()
    conexion.close()

    if not encontrado:
        return jsonify({"error": "Contrato no encontrado"}), 404
    return jsonify({"ok": True})


@contratos_bp.route("/api/contratos/<int:contrato_id>/documento", methods=["POST"])
@login_requerido
def api_subir_documento_contrato(contrato_id):
    nombre, contenido, error = _leer_pdf()
    if error:
        return jsonify({"error": error}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        "UPDATE contratos SET archivo_nombre = %s, archivo_contenido = %s WHERE id = %s",
        (nombre, psycopg2.Binary(contenido), contrato_id)
    )
    encontrado = cursor.rowcount > 0
    conexion.commit()
    cursor.close()
    conexion.close()

    if not encontrado:
        return jsonify({"error": "Contrato no encontrado"}), 404
    return jsonify({"ok": True}), 201


@contratos_bp.route("/documentos-contrato/<int:contrato_id>")
@login_requerido
def servir_documento_contrato(contrato_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        "SELECT archivo_nombre, archivo_contenido FROM contratos WHERE id = %s", (contrato_id,)
    )
    fila = cursor.fetchone()
    cursor.close()
    conexion.close()

    if not fila or not fila[1]:
        abort(404)
    return send_file(BytesIO(bytes(fila[1])), mimetype="application/pdf", download_name=fila[0])


# ==========================================================
# API: adendas
# ==========================================================

def _validar_adenda(datos):
    tipo = (datos.get("tipo") or "").strip()
    descripcion = (datos.get("descripcion") or "").strip()

    if tipo not in TIPOS_ADENDA:
        return None, "Selecciona el tipo de adenda"
    if not descripcion:
        return None, "Describe el cambio de la adenda"

    try:
        fecha_suscripcion = parsear_fecha(datos.get("fechaSuscripcion"))
        nuevo_fin = parsear_fecha(datos.get("nuevoFin"))
    except ValueError:
        return None, "Las fechas no son válidas"

    if tipo in TIPOS_ADENDA_CON_FECHA and not nuevo_fin:
        return None, "Indica el nuevo fin de vigencia"

    return {
        "tipo": tipo, "descripcion": descripcion,
        "fecha_suscripcion": fecha_suscripcion, "nuevo_fin": nuevo_fin
    }, None


@contratos_bp.route("/api/contratos/adendas")
@login_requerido
def api_listar_adendas():
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("""
        SELECT a.id, a.numero, a.tipo, a.descripcion, a.fecha_suscripcion, a.nuevo_fin,
               a.archivo_nombre, c.id, c.numero, c.contraparte_nombre, c.modulo
        FROM contratos_adendas a
        JOIN contratos c ON c.id = a.contrato_id
        ORDER BY a.creado_en DESC, a.id DESC
    """)
    adendas = [
        {
            "id": f[0], "numero": f[1], "tipo": f[2], "descripcion": f[3],
            "fechaSuscripcion": _fecha_str(f[4]), "nuevoFin": _fecha_str(f[5]),
            "tieneDocumento": bool(f[6]), "formalizada": bool(f[4] and f[6]),
            "contratoId": f[7], "contratoNumero": f[8], "contraparte": f[9],
            "moduloNombre": MODULOS[f[10]]["nombre"]
        }
        for f in cursor.fetchall()
    ]
    cursor.close()
    conexion.close()
    return jsonify({"adendas": adendas})


@contratos_bp.route("/api/contratos/<int:contrato_id>/adendas", methods=["POST"])
@login_requerido
def api_crear_adenda(contrato_id):
    v, error = _validar_adenda(request.get_json(silent=True) or {})
    if error:
        return jsonify({"error": error}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        _, problema = _contrato_abierto(cursor, contrato_id)
        if problema:
            return jsonify({"error": problema[0]}), problema[1]

        cursor.execute("""
            INSERT INTO contratos_adendas (
                contrato_id, numero, tipo, descripcion, fecha_suscripcion, nuevo_fin,
                creado_por, creado_en
            )
            VALUES (
                %s,
                (SELECT COALESCE(MAX(numero), 0) + 1 FROM contratos_adendas WHERE contrato_id = %s),
                %s, %s, %s, %s, %s, %s
            )
            RETURNING id
        """, (
            contrato_id, contrato_id, v["tipo"], v["descripcion"], v["fecha_suscripcion"],
            v["nuevo_fin"], session.get("username"), datetime.now()
        ))
        adenda_id = cursor.fetchone()[0]
        conexion.commit()
        return jsonify({"ok": True, "id": adenda_id}), 201
    except Exception as error_bd:
        conexion.rollback()
        print("ERROR CREANDO ADENDA:", error_bd)
        return jsonify({"error": "No se pudo crear la adenda"}), 500
    finally:
        cursor.close()
        conexion.close()


@contratos_bp.route("/api/contratos/adendas/<int:adenda_id>", methods=["PUT"])
@login_requerido
def api_actualizar_adenda(adenda_id):
    v, error = _validar_adenda(request.get_json(silent=True) or {})
    if error:
        return jsonify({"error": error}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT contrato_id FROM contratos_adendas WHERE id = %s", (adenda_id,))
        fila = cursor.fetchone()
        if not fila:
            return jsonify({"error": "Adenda no encontrada"}), 404

        _, problema = _contrato_abierto(cursor, fila[0])
        if problema:
            return jsonify({"error": problema[0]}), problema[1]

        cursor.execute("""
            UPDATE contratos_adendas SET
                tipo = %s, descripcion = %s, fecha_suscripcion = %s, nuevo_fin = %s
            WHERE id = %s
        """, (v["tipo"], v["descripcion"], v["fecha_suscripcion"], v["nuevo_fin"], adenda_id))
        conexion.commit()
        return jsonify({"ok": True})
    except Exception as error_bd:
        conexion.rollback()
        print("ERROR ACTUALIZANDO ADENDA:", error_bd)
        return jsonify({"error": "No se pudo actualizar la adenda"}), 500
    finally:
        cursor.close()
        conexion.close()


@contratos_bp.route("/api/contratos/adendas/<int:adenda_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_adenda(adenda_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM contratos_adendas WHERE id = %s", (adenda_id,))
    eliminado = cursor.rowcount > 0
    conexion.commit()
    cursor.close()
    conexion.close()

    if not eliminado:
        return jsonify({"error": "Adenda no encontrada"}), 404
    return jsonify({"ok": True})


@contratos_bp.route("/api/contratos/adendas/<int:adenda_id>/documento", methods=["POST"])
@login_requerido
def api_subir_documento_adenda(adenda_id):
    nombre, contenido, error = _leer_pdf()
    if error:
        return jsonify({"error": error}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        "UPDATE contratos_adendas SET archivo_nombre = %s, archivo_contenido = %s WHERE id = %s",
        (nombre, psycopg2.Binary(contenido), adenda_id)
    )
    encontrada = cursor.rowcount > 0
    conexion.commit()
    cursor.close()
    conexion.close()

    if not encontrada:
        return jsonify({"error": "Adenda no encontrada"}), 404
    return jsonify({"ok": True}), 201


@contratos_bp.route("/documentos-adenda/<int:adenda_id>")
@login_requerido
def servir_documento_adenda(adenda_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(
        "SELECT archivo_nombre, archivo_contenido FROM contratos_adendas WHERE id = %s",
        (adenda_id,)
    )
    fila = cursor.fetchone()
    cursor.close()
    conexion.close()

    if not fila or not fila[1]:
        abort(404)
    return send_file(BytesIO(bytes(fila[1])), mimetype="application/pdf", download_name=fila[0])
