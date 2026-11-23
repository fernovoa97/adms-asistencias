# ordenes_compra.py
# Ordenes de compra con el formato del Excel "ORDEN DE COMPRA DRILLCO TOOLS
# PERU": proveedor (nombre, RUC, direccion), items con cantidad y valor
# unitario sin IGV, totales con IGV, total en letras y campos libres del pie.
#
# Correlativo ADM-AAAA-C<numero>: se propone el siguiente del anio de la
# fecha (MAX + 1) y se puede cambiar a mano; como el siguiente siempre sale
# del maximo, la numeracion continua desde el numero que se haya puesto.
# Al cambiar de anio arranca de nuevo en 1.

from datetime import datetime
from decimal import Decimal
import io
import re

import psycopg2
from flask import Blueprint, Response, abort, jsonify, render_template, request, session
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from auth import login_requerido
from db import obtener_conexion
from montos import MONEDAS, a_decimal, calcular_totales, formatear_correlativo, monto_en_letras
from validaciones import hoy_local, parsear_fecha

ordenes_compra_bp = Blueprint("ordenes_compra", __name__)

# Valores del pie con los que arranca la primera orden. Despues cada orden
# nueva copia los de la ultima registrada, para no reescribirlos.
PIE_INICIAL = {
    "forma_pago": "Contado",
    "autorizado_por": "Jorge Morán",
    "nota": "RETORNAR GUÍAS SELLADAS",
    "entrega": (
        "Drillco Tools Peru SAC - RUC 20451741315 - Carretera Panamericana Sur Km. 29.5 "
        "Interior C13-C14 Megacentro Lurín, ref. altura puente peatonal Vidu. "
        "Horario de atención: lunes a viernes de 8:30 a. m. a 5:00 p. m."
    ),
    "atencion": "Reynaldo Ingaruca # 992 506 717 (previa coordinación)",
}
CAMPOS_PIE = tuple(PIE_INICIAL) + ("observaciones",)

ENCABEZADO = {
    "empresa": "DRILLCO TOOLS PERU S.A.C.",
    "sistema": "Sistema Integrado de Gestión",
    "codigo": "DTPSAC-RE-68",
    "version": "01",
    "aprobacion": "10/01/2023",
}

COLUMNAS_ORDEN = """
    id, anio, numero, fecha, proveedor_nombre, proveedor_ruc, proveedor_direccion, moneda,
    forma_pago, autorizado_por, nota, entrega, atencion, observaciones,
    valor_venta, igv, total, creado_por, creado_en
"""


def _num(valor):
    """Decimal -> texto sin ceros de sobra, para JSON (12.500 -> '12.5')."""
    if valor is None:
        return None
    texto = format(Decimal(valor).normalize(), "f")
    return texto


def _fila_a_orden(f):
    return {
        "id": f[0],
        "anio": f[1],
        "numero": f[2],
        "correlativo": formatear_correlativo(f[1], f[2]),
        "fecha": f[3].isoformat(),
        "proveedor_nombre": f[4],
        "proveedor_ruc": f[5],
        "proveedor_direccion": f[6] or "",
        "moneda": f[7],
        "forma_pago": f[8] or "",
        "autorizado_por": f[9] or "",
        "nota": f[10] or "",
        "entrega": f[11] or "",
        "atencion": f[12] or "",
        "observaciones": f[13] or "",
        "valor_venta": f"{f[14]:.2f}",
        "igv": f"{f[15]:.2f}",
        "total": f"{f[16]:.2f}",
        "total_letras": monto_en_letras(f[16], f[7]),
        "creado_por": f[17],
        "creado_en": f[18].isoformat(timespec="minutes"),
    }


def _obtener_orden(cursor, orden_id):
    cursor.execute(f"SELECT {COLUMNAS_ORDEN} FROM ordenes_compra WHERE id = %s", (orden_id,))
    fila = cursor.fetchone()
    if not fila:
        return None
    orden = _fila_a_orden(fila)
    cursor.execute("""
        SELECT cantidad, descripcion, valor_unitario, total
        FROM ordenes_compra_items WHERE orden_id = %s ORDER BY orden, id
    """, (orden_id,))
    orden["items"] = [
        {"cantidad": _num(c), "descripcion": d, "valor_unitario": _num(vu), "total": f"{t:.2f}"}
        for c, d, vu, t in cursor.fetchall()
    ]
    return orden


def _siguiente_numero(cursor, anio):
    cursor.execute("SELECT COALESCE(MAX(numero), 0) + 1 FROM ordenes_compra WHERE anio = %s", (anio,))
    return cursor.fetchone()[0]


def _pie_por_defecto(cursor):
    cursor.execute(f"""
        SELECT {', '.join(PIE_INICIAL)} FROM ordenes_compra
        ORDER BY creado_en DESC, id DESC LIMIT 1
    """)
    fila = cursor.fetchone()
    if not fila:
        return dict(PIE_INICIAL)
    return {campo: (valor or "") for campo, valor in zip(PIE_INICIAL, fila)}


def _leer_items(items_crudos):
    """Valida los items del formulario. Las filas totalmente vacias se
    ignoran; una fila a medio llenar es un error."""
    items = []
    for posicion, it in enumerate(items_crudos or [], start=1):
        descripcion = (it.get("descripcion") or "").strip()
        cantidad_txt = str(it.get("cantidad") or "").strip()
        valor_txt = str(it.get("valor_unitario") or "").strip()
        if not (descripcion or cantidad_txt or valor_txt):
            continue
        if not descripcion:
            raise ValueError(f"Ítem {posicion}: falta la descripción")
        try:
            cantidad = a_decimal(cantidad_txt)
            valor_unitario = a_decimal(valor_txt)
        except ValueError:
            raise ValueError(f"Ítem {posicion}: la cantidad y el valor unitario deben ser números")
        if cantidad <= 0:
            raise ValueError(f"Ítem {posicion}: la cantidad debe ser mayor a cero")
        if valor_unitario < 0:
            raise ValueError(f"Ítem {posicion}: el valor unitario no puede ser negativo")
        if cantidad.as_tuple().exponent < -3 or valor_unitario.as_tuple().exponent < -4:
            raise ValueError(f"Ítem {posicion}: demasiados decimales (máx. 3 en cantidad y 4 en valor unitario)")
        items.append({"descripcion": descripcion, "cantidad": cantidad, "valor_unitario": valor_unitario})
    if not items:
        raise ValueError("Agrega al menos un ítem")
    return items


def _leer_orden(datos):
    proveedor_nombre = (datos.get("proveedor_nombre") or "").strip()
    proveedor_ruc = re.sub(r"\s", "", datos.get("proveedor_ruc") or "")
    if not proveedor_nombre:
        raise ValueError("El nombre del proveedor es obligatorio")
    if not re.fullmatch(r"\d{11}", proveedor_ruc):
        raise ValueError("El RUC debe tener 11 dígitos")

    try:
        fecha = parsear_fecha(datos.get("fecha"))
    except ValueError:
        raise ValueError("La fecha no es válida")
    if not fecha:
        raise ValueError("La fecha es obligatoria")

    try:
        numero = int(str(datos.get("numero") or "").strip())
    except ValueError:
        raise ValueError("El número de la O/C debe ser un número entero")
    if numero < 1:
        raise ValueError("El número de la O/C debe ser 1 o mayor")

    moneda = datos.get("moneda")
    if moneda not in MONEDAS:
        raise ValueError("Elige la moneda")

    orden = {
        "anio": fecha.year,
        "numero": numero,
        "fecha": fecha,
        "proveedor_nombre": proveedor_nombre,
        "proveedor_ruc": proveedor_ruc,
        "proveedor_direccion": (datos.get("proveedor_direccion") or "").strip(),
        "moneda": moneda,
        "items": _leer_items(datos.get("items")),
    }
    for campo in CAMPOS_PIE:
        orden[campo] = (datos.get(campo) or "").strip()
    orden["totales"] = calcular_totales(orden["items"])
    return orden


def _guardar_items(cursor, orden_id, orden):
    cursor.execute("DELETE FROM ordenes_compra_items WHERE orden_id = %s", (orden_id,))
    for posicion, (item, total) in enumerate(zip(orden["items"], orden["totales"]["lineas"])):
        cursor.execute("""
            INSERT INTO ordenes_compra_items (orden_id, orden, cantidad, descripcion, valor_unitario, total)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (orden_id, posicion, item["cantidad"], item["descripcion"], item["valor_unitario"], total))


def _respuesta_duplicado(orden):
    correlativo = formatear_correlativo(orden["anio"], orden["numero"])
    return jsonify({"error": f"Ya existe una orden de compra con el número {correlativo}"}), 409


# ==========================================================
# PAGINAS
# ==========================================================

@ordenes_compra_bp.route("/ordenes-compra")
@login_requerido
def pagina_ordenes_compra():
    return render_template("ordenes_compra.html", active_page="ordenes_compra")


@ordenes_compra_bp.route("/ordenes-compra/nueva")
@login_requerido
def pagina_nueva_orden():
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    hoy = hoy_local()
    orden = {
        "id": None,
        "fecha": hoy.isoformat(),
        "anio": hoy.year,
        "numero": _siguiente_numero(cursor, hoy.year),
        "moneda": "PEN",
        "proveedor_nombre": "",
        "proveedor_ruc": "",
        "proveedor_direccion": "",
        "observaciones": "",
        "items": [],
        **_pie_por_defecto(cursor),
    }
    cursor.close()
    conexion.close()
    return render_template("orden_compra_form.html", orden=orden, monedas=MONEDAS,
                           active_page="ordenes_compra")


@ordenes_compra_bp.route("/ordenes-compra/<int:orden_id>/editar")
@login_requerido
def pagina_editar_orden(orden_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    orden = _obtener_orden(cursor, orden_id)
    cursor.close()
    conexion.close()
    if not orden:
        abort(404)
    return render_template("orden_compra_form.html", orden=orden, monedas=MONEDAS,
                           active_page="ordenes_compra")


@ordenes_compra_bp.route("/ordenes-compra/<int:orden_id>")
@login_requerido
def pagina_ver_orden(orden_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    orden = _obtener_orden(cursor, orden_id)
    cursor.close()
    conexion.close()
    if not orden:
        abort(404)
    return render_template("orden_compra_ver.html", orden=orden, moneda=MONEDAS[orden["moneda"]],
                           encabezado=ENCABEZADO, active_page="ordenes_compra")


# ==========================================================
# API
# ==========================================================

@ordenes_compra_bp.route("/api/ordenes-compra")
@login_requerido
def api_listar_ordenes():
    busqueda = (request.args.get("q") or "").strip()
    filtro, parametros = "", []
    if busqueda:
        patron = f"%{busqueda}%"
        filtro = """
            WHERE proveedor_nombre ILIKE %s OR proveedor_ruc ILIKE %s
               OR ('ADM-' || anio || '-C' || numero) ILIKE %s
        """
        parametros = [patron, patron, patron]

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute(f"""
        SELECT {COLUMNAS_ORDEN} FROM ordenes_compra {filtro}
        ORDER BY anio DESC, numero DESC LIMIT 300
    """, parametros)
    ordenes = [_fila_a_orden(f) for f in cursor.fetchall()]
    cursor.close()
    conexion.close()
    return jsonify({"ordenes": ordenes, "monedas": MONEDAS})


@ordenes_compra_bp.route("/api/ordenes-compra/siguiente")
@login_requerido
def api_siguiente_numero():
    try:
        anio = int(request.args.get("anio") or hoy_local().year)
    except ValueError:
        return jsonify({"error": "Año no válido"}), 400
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    numero = _siguiente_numero(cursor, anio)
    cursor.close()
    conexion.close()
    return jsonify({"anio": anio, "numero": numero})


@ordenes_compra_bp.route("/api/ordenes-compra/proveedor")
@login_requerido
def api_buscar_proveedor():
    """Datos del proveedor tal como quedaron en su ultima orden, para
    autocompletar el formulario al escribir un RUC conocido."""
    ruc = re.sub(r"\s", "", request.args.get("ruc") or "")
    if not re.fullmatch(r"\d{11}", ruc):
        return jsonify({"proveedor": None})
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("""
        SELECT proveedor_nombre, proveedor_direccion FROM ordenes_compra
        WHERE proveedor_ruc = %s ORDER BY creado_en DESC LIMIT 1
    """, (ruc,))
    fila = cursor.fetchone()
    cursor.close()
    conexion.close()
    if not fila:
        return jsonify({"proveedor": None})
    return jsonify({"proveedor": {"nombre": fila[0], "direccion": fila[1] or ""}})


@ordenes_compra_bp.route("/api/ordenes-compra/calcular", methods=["POST"])
@login_requerido
def api_calcular():
    """Totales y monto en letras para la vista previa del formulario. Las
    filas incompletas se cuentan como cero, para poder calcular mientras
    se escribe."""
    datos = request.get_json(silent=True) or {}
    moneda = datos.get("moneda") if datos.get("moneda") in MONEDAS else "PEN"
    items = []
    for it in datos.get("items") or []:
        try:
            cantidad = a_decimal(it.get("cantidad"))
            valor_unitario = a_decimal(it.get("valor_unitario"))
        except ValueError:
            cantidad = valor_unitario = Decimal(0)
        items.append({"cantidad": cantidad, "valor_unitario": valor_unitario})
    totales = calcular_totales(items)
    total = max(totales["total"], Decimal(0))
    return jsonify({
        "lineas": [f"{t:.2f}" for t in totales["lineas"]],
        "valor_venta": f"{totales['valor_venta']:.2f}",
        "igv": f"{totales['igv']:.2f}",
        "total": f"{totales['total']:.2f}",
        "total_letras": monto_en_letras(total, moneda),
    })


@ordenes_compra_bp.route("/api/ordenes-compra", methods=["POST"])
@login_requerido
def api_crear_orden():
    try:
        orden = _leer_orden(request.get_json(silent=True) or {})
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute(f"""
            INSERT INTO ordenes_compra (
                anio, numero, fecha, proveedor_nombre, proveedor_ruc, proveedor_direccion, moneda,
                {', '.join(CAMPOS_PIE)}, valor_venta, igv, total, creado_por, creado_en
            )
            VALUES ({', '.join(['%s'] * (7 + len(CAMPOS_PIE) + 5))})
            RETURNING id
        """, (
            orden["anio"], orden["numero"], orden["fecha"], orden["proveedor_nombre"],
            orden["proveedor_ruc"], orden["proveedor_direccion"], orden["moneda"],
            *[orden[c] for c in CAMPOS_PIE],
            orden["totales"]["valor_venta"], orden["totales"]["igv"], orden["totales"]["total"],
            session.get("username"), datetime.now(),
        ))
        orden_id = cursor.fetchone()[0]
        _guardar_items(cursor, orden_id, orden)
        conexion.commit()
        return jsonify({"ok": True, "id": orden_id}), 201
    except psycopg2.errors.UniqueViolation:
        conexion.rollback()
        return _respuesta_duplicado(orden)
    except Exception as error:
        conexion.rollback()
        print("ERROR CREANDO ORDEN DE COMPRA:", error)
        return jsonify({"error": "No se pudo guardar la orden de compra"}), 500
    finally:
        cursor.close()
        conexion.close()


@ordenes_compra_bp.route("/api/ordenes-compra/<int:orden_id>", methods=["PUT"])
@login_requerido
def api_editar_orden(orden_id):
    try:
        orden = _leer_orden(request.get_json(silent=True) or {})
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        asignaciones = ", ".join(f"{c} = %s" for c in CAMPOS_PIE)
        cursor.execute(f"""
            UPDATE ordenes_compra SET
                anio = %s, numero = %s, fecha = %s, proveedor_nombre = %s, proveedor_ruc = %s,
                proveedor_direccion = %s, moneda = %s, {asignaciones},
                valor_venta = %s, igv = %s, total = %s, actualizado_en = %s
            WHERE id = %s
        """, (
            orden["anio"], orden["numero"], orden["fecha"], orden["proveedor_nombre"],
            orden["proveedor_ruc"], orden["proveedor_direccion"], orden["moneda"],
            *[orden[c] for c in CAMPOS_PIE],
            orden["totales"]["valor_venta"], orden["totales"]["igv"], orden["totales"]["total"],
            datetime.now(), orden_id,
        ))
        if cursor.rowcount == 0:
            conexion.rollback()
            return jsonify({"error": "Orden de compra no encontrada"}), 404
        _guardar_items(cursor, orden_id, orden)
        conexion.commit()
        return jsonify({"ok": True, "id": orden_id})
    except psycopg2.errors.UniqueViolation:
        conexion.rollback()
        return _respuesta_duplicado(orden)
    except Exception as error:
        conexion.rollback()
        print("ERROR EDITANDO ORDEN DE COMPRA:", error)
        return jsonify({"error": "No se pudo guardar la orden de compra"}), 500
    finally:
        cursor.close()
        conexion.close()


@ordenes_compra_bp.route("/api/ordenes-compra/<int:orden_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_orden(orden_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM ordenes_compra WHERE id = %s", (orden_id,))
    eliminado = cursor.rowcount > 0
    conexion.commit()
    cursor.close()
    conexion.close()
    if not eliminado:
        return jsonify({"error": "Orden de compra no encontrada"}), 404
    return jsonify({"ok": True})


# ==========================================================
# EXPORTAR A EXCEL (mismo formato que la plantilla original)
# ==========================================================

def _hoja_orden(hoja, orden):
    moneda = MONEDAS[orden["moneda"]]
    formato_monto = f'"{moneda["simbolo"]}" #,##0.00'
    fino = Side(style="thin", color="000000")
    borde = Border(left=fino, right=fino, top=fino, bottom=fino)
    negrita = Font(name="Arial", size=10, bold=True)
    normal = Font(name="Arial", size=10)
    centro = Alignment(horizontal="center", vertical="center", wrap_text=True)
    izquierda = Alignment(horizontal="left", vertical="center", wrap_text=True)
    gris = PatternFill("solid", fgColor="D9D9D9")

    for columna, ancho in zip("ABCDEFGHIJ", (7, 11, 12, 12, 12, 12, 12, 8, 14, 15)):
        hoja.column_dimensions[columna].width = ancho

    def celda(ref, valor, fuente=normal, alineacion=izquierda, fusion=None, con_borde=False):
        hoja[ref] = valor
        hoja[ref].font = fuente
        hoja[ref].alignment = alineacion
        if fusion:
            hoja.merge_cells(fusion)
        if con_borde:
            rango = hoja[fusion] if fusion else ((hoja[ref],),)
            for fila_celdas in rango:
                for c in fila_celdas:
                    c.border = borde

    # Encabezado del SIG
    celda("A2", "DRILLCO", Font(name="Arial", size=12, bold=True), centro, "A2:B5", True)
    celda("C2", ENCABEZADO["empresa"], negrita, centro, "C2:H2", True)
    celda("C3", ENCABEZADO["sistema"], normal, centro, "C3:H3", True)
    celda("C4", "ORDEN DE COMPRA", Font(name="Arial", size=14, bold=True), centro, "C4:H5", True)
    celda("I2", f"Código: {ENCABEZADO['codigo']}", normal, izquierda, "I2:J2", True)
    celda("I3", f"Versión: {ENCABEZADO['version']}", normal, izquierda, "I3:J3", True)
    celda("I4", f"Aprobación: {ENCABEZADO['aprobacion']}\nPágina 1 de 1", normal, izquierda, "I4:J5", True)

    celda("G7", "O/C:", negrita, Alignment(horizontal="right"), "G7:H7")
    celda("I7", orden["correlativo"], Font(name="Arial", size=11, bold=True), centro, "I7:J7", True)

    celda("B9", "FECHA:", negrita)
    celda("C9", datetime.strptime(orden["fecha"], "%Y-%m-%d").date(), normal, izquierda, "C9:D9")
    hoja["C9"].number_format = "DD/MM/YYYY"
    celda("B10", "PROVEEDOR:", negrita)
    celda("C10", orden["proveedor_nombre"], normal, izquierda, "C10:J10")
    celda("B11", "RUC:", negrita)
    celda("C11", orden["proveedor_ruc"], normal, izquierda, "C11:E11")
    celda("B12", "DIRECCIÓN:", negrita)
    celda("C12", orden["proveedor_direccion"], normal, izquierda, "C12:J12")
    hoja.row_dimensions[12].height = 28

    fila = 14
    for ref, texto, fusion in (("A", "ITEM", None), ("B", "CANTIDAD", None),
                               ("C", "DESCRIPCIÓN", "C{0}:H{0}"), ("I", "VALOR UNIT.", None),
                               ("J", "TOTAL", None)):
        celda(f"{ref}{fila}", texto, negrita, centro, fusion.format(fila) if fusion else None, True)
        hoja[f"{ref}{fila}"].fill = gris

    for posicion, item in enumerate(orden["items"], start=1):
        fila += 1
        celda(f"A{fila}", posicion, normal, centro, None, True)
        celda(f"B{fila}", float(item["cantidad"]), normal, centro, None, True)
        celda(f"C{fila}", item["descripcion"], normal, izquierda, f"C{fila}:H{fila}", True)
        celda(f"I{fila}", float(item["valor_unitario"]), normal, Alignment(horizontal="right", vertical="center"), None, True)
        celda(f"J{fila}", float(item["total"]), normal, Alignment(horizontal="right", vertical="center"), None, True)
        hoja[f"I{fila}"].number_format = formato_monto
        hoja[f"J{fila}"].number_format = formato_monto
        lineas = max(1, len(item["descripcion"]) // 70 + item["descripcion"].count("\n") + 1)
        hoja.row_dimensions[fila].height = max(15, 13 * lineas)

    derecha = Alignment(horizontal="right", vertical="center")
    for etiqueta, valor in (("V. VENTA", orden["valor_venta"]), ("I.G.V. 18%", orden["igv"]),
                            (moneda["etiqueta_total"], orden["total"])):
        fila += 1
        celda(f"I{fila}", etiqueta, negrita, derecha, None, True)
        celda(f"J{fila}", float(valor), negrita, derecha, None, True)
        hoja[f"J{fila}"].number_format = formato_monto
    fila_son = fila - 2
    celda(f"B{fila_son}", "Son:", negrita)
    celda(f"C{fila_son}", orden["total_letras"], normal, izquierda, f"C{fila_son}:H{fila_son + 1}")
    celda(f"B{fila_son + 2}", "Forma de pago:", negrita)
    celda(f"D{fila_son + 2}", orden["forma_pago"], normal, izquierda, f"D{fila_son + 2}:H{fila_son + 2}")

    fila += 2
    if orden["observaciones"]:
        celda(f"B{fila}", "Observaciones:", negrita)
        celda(f"D{fila}", orden["observaciones"], normal, izquierda, f"D{fila}:J{fila}")
        hoja.row_dimensions[fila].height = 30
        fila += 2

    fila += 3
    celda(f"D{fila}", "Autorizado por:", negrita, centro, f"D{fila}:F{fila}")
    hoja[f"D{fila}"].border = Border(top=fino)
    celda(f"D{fila + 1}", orden["autorizado_por"], normal, centro, f"D{fila + 1}:F{fila + 1}")

    fila += 3
    if orden["nota"]:
        celda(f"B{fila}", f"NOTA: {orden['nota']}", negrita, izquierda, f"B{fila}:J{fila}")
        fila += 2
    if orden["entrega"]:
        celda(f"B{fila}", f"ENTREGA DE MERCADERÍA O SERVICIO A REALIZAR\n{orden['entrega']}",
              normal, izquierda, f"B{fila}:J{fila + 2}", True)
        fila += 3
    if orden["atencion"]:
        celda(f"B{fila}", f"ATENCIÓN: {orden['atencion']}", negrita, izquierda, f"B{fila}:J{fila}", True)

    hoja.page_setup.paperSize = hoja.PAPERSIZE_A4
    hoja.page_setup.fitToWidth = 1
    hoja.sheet_properties.pageSetUpPr.fitToPage = True
    hoja.print_area = f"A1:J{fila}"


@ordenes_compra_bp.route("/ordenes-compra/<int:orden_id>/excel")
@login_requerido
def exportar_orden_excel(orden_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    orden = _obtener_orden(cursor, orden_id)
    cursor.close()
    conexion.close()
    if not orden:
        abort(404)

    libro = Workbook()
    hoja = libro.active
    hoja.title = orden["correlativo"]
    _hoja_orden(hoja, orden)

    salida = io.BytesIO()
    libro.save(salida)
    respuesta = Response(
        salida.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    respuesta.headers["Content-Disposition"] = f"attachment; filename=OC_{orden['correlativo']}.xlsx"
    return respuesta
