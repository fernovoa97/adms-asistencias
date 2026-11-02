# asistencia.py
# Panel de asistencia por periodo (del 24 al 23): una fila por trabajador,
# columnas por semana de lunes a viernes con la hora de entrada, y totales de
# tardanza exactos al segundo. Tambien registra marcaciones y justificaciones,
# importa marcaciones desde Excel/CSV y exporta el panel a Excel con colores.

import csv
import io
import re
import unicodedata
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, jsonify, render_template, request, session
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ajustes import obtener_config_asistencia
from auth import login_requerido
from db import obtener_conexion
from reglas_asistencia import (
    formatear_hms,
    horario_del_trabajador,
    periodo_de_fecha,
    periodo_vecino,
    rango_periodo,
    segundos_tardanza,
    semanas_del_periodo,
)
from vacaciones import fecha_en_vacaciones, obtener_rangos_vacaciones

asistencia_bp = Blueprint("asistencia", __name__)

ZONA_HORARIA_LOCAL = ZoneInfo("America/Lima")

# Marcaciones que no vinieron de un huellero: se guardan en "asistencias" para
# que Panel, Resumen e Historial las vean sin cambios.
SN_MANUAL = "MANUAL"
SN_IMPORTADO = "IMPORTADO"

# Marcacion de entrada reemplazada por una correccion manual. No se borra (es
# el dato original del dispositivo) y, al no ser '0', ninguna vista la cuenta.
TIPO_ENTRADA_ANULADA = "0A"

MAX_BYTES_IMPORTACION = 5 * 1024 * 1024
MAX_FILAS_IMPORTACION = 50000
MAX_ERRORES_MOSTRADOS = 30

MESES_ES = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
]
MESES_ABREV = ["", "ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]
DIAS_ABREV = ["LUN", "MAR", "MIÉ", "JUE", "VIE"]

# Estados que no son tipos editables: salen de otros modulos del sistema.
ESTADOS_SISTEMA = [
    {"clave": "vacaciones", "nombre": "Vacaciones", "color": "#f5c6de"},
    {"clave": "descanso", "nombre": "Descanso médico", "color": "#c7e8d3"},
]
COLOR_FERIADO = "#dcdcd5"
COLOR_SIN_TIPO = "#e4e4de"
COLOR_SEMANA = "#ffe94d"
COLOR_TOTAL_PERIODO = "#e7ecf6"
COLOR_TEXTO = "#17202f"
COLOR_ROJO = "#ad2f26"


def _hoy():
    return datetime.now(ZONA_HORARIA_LOCAL).date()


def color_texto(color_fondo):
    """Texto oscuro sobre colores claros y blanco sobre oscuros, para que un
    color elegido en Ajustes nunca deje la celda ilegible."""
    r, g, b = (int(color_fondo[i:i + 2], 16) for i in (1, 3, 5))
    return "#ffffff" if 0.299 * r + 0.587 * g + 0.114 * b < 128 else COLOR_TEXTO


# ---------------------------------------------------------------------------
# Lectura de datos y evaluacion de cada dia
# ---------------------------------------------------------------------------

def _trabajadores_del_panel(cursor):
    """Mismo criterio que el Resumen: activos, con codigo de empleado y que
    no esten excluidos de las reglas de asistencia."""
    cursor.execute("""
        SELECT id, nombres, apellidos, hora_entrada, hora_salida, fecha_ingreso
        FROM trabajadores
        WHERE codigo_empleado IS NOT NULL
          AND estado IS DISTINCT FROM 'INACTIVO'
          AND excluido_asistencia IS NOT TRUE
        ORDER BY apellidos, nombres
    """)
    columnas = ["id", "nombres", "apellidos", "hora_entrada", "hora_salida", "fecha_ingreso"]
    return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]


def _tipos_de_justificacion(cursor):
    cursor.execute("SELECT id, nombre, color, es_falta FROM motivos_justificacion ORDER BY orden, nombre")
    return [
        {"clave": f[0], "nombre": f[1], "color": f[2], "es_falta": f[3], "texto": color_texto(f[2])}
        for f in cursor.fetchall()
    ]


def _estados_sistema(tipos):
    """Estados del sistema, indicando si coinciden con un tipo del catalogo
    (ej. "Descanso medico"): en ese caso usan su color y suman en su columna,
    para no aparecer dos veces."""
    por_nombre = {t["nombre"].lower(): t for t in tipos}
    estados = {}
    for estado in ESTADOS_SISTEMA:
        tipo = por_nombre.get(estado["nombre"].lower())
        estados[estado["clave"]] = {
            **estado,
            "color": tipo["color"] if tipo else estado["color"],
            "clave_conteo": tipo["clave"] if tipo else estado["clave"],
            "en_catalogo": tipo is not None
        }
    return estados


def _datos_de_rango(cursor, inicio, fin):
    """Todo lo que hace falta para evaluar los dias de un rango, cargado de
    una vez para no consultar por cada celda."""
    # Mismo cruce por codigo o DNI que usan el Panel y el Resumen.
    cursor.execute("""
        SELECT t.id, a.fecha, a.hora, a.sn_dispositivo, a.registrado_por
        FROM asistencias a
        JOIN trabajadores t
            ON t.codigo_empleado = a.codigo_empleado
            OR t.dni = a.codigo_empleado
        WHERE a.tipo_marcaje = '0' AND a.fecha BETWEEN %s AND %s
    """, (inicio, fin))
    entradas = {}
    for trabajador_id, fecha, hora, sn, registrado_por in cursor.fetchall():
        actual = entradas.get((trabajador_id, fecha))
        if actual is None or hora < actual["hora"]:
            entradas[(trabajador_id, fecha)] = {"hora": hora, "sn": sn, "registrado_por": registrado_por}

    cursor.execute("""
        SELECT a.trabajador_id, a.fecha, a.motivo, a.observacion, a.creado_por,
               a.tipo_id, m.nombre, m.color, m.es_falta
        FROM ajustes_asistencia a
        LEFT JOIN motivos_justificacion m ON m.id = a.tipo_id
        WHERE a.fecha BETWEEN %s AND %s
    """, (inicio, fin))
    justificaciones = {}
    for t_id, fecha, motivo, observacion, creado_por, tipo_id, nombre, color, es_falta in cursor.fetchall():
        justificaciones[(t_id, fecha)] = {
            "tipo_id": tipo_id,
            "tipo": nombre or motivo,
            "color": color or COLOR_SIN_TIPO,
            "es_falta": bool(es_falta),
            "observacion": observacion,
            "registrado_por": creado_por
        }

    cursor.execute("SELECT fecha, descripcion FROM feriados WHERE fecha BETWEEN %s AND %s", (inicio, fin))
    feriados = {f[0]: f[1] for f in cursor.fetchall()}

    cursor.execute("""
        SELECT trabajador_id, fecha_inicio, fecha_fin FROM descansos_medicos
        WHERE fecha_inicio <= %s AND fecha_fin >= %s
    """, (fin, inicio))
    descansos = {}
    for t_id, desde, hasta in cursor.fetchall():
        descansos.setdefault(t_id, []).append((desde, hasta))

    return {
        "entradas": entradas,
        "justificaciones": justificaciones,
        "feriados": feriados,
        "descansos": descansos,
        "vacaciones": obtener_rangos_vacaciones(cursor),
        "estados_sistema": _estados_sistema(_tipos_de_justificacion(cursor))
    }


def _origen_marcacion(entrada):
    if entrada["sn"] == SN_MANUAL:
        return f"Manual ({entrada['registrado_por'] or 'sin usuario'})"
    if entrada["sn"] == SN_IMPORTADO:
        return f"Importada ({entrada['registrado_por'] or 'sin usuario'})"
    return "Dispositivo biométrico"


def evaluar_dia(trabajador, fecha, datos, hora_estandar):
    """Celda de un trabajador en una fecha. Solo la marcacion normal suma
    tardanza; prioridad: feriado > justificacion > vacaciones > descanso."""
    entrada = datos["entradas"].get((trabajador["id"], fecha))
    hora_texto = entrada["hora"].strftime("%H:%M:%S") if entrada else None

    celda = {
        "estado": "vacio",
        "trabajador_id": trabajador["id"],
        "trabajador": f"{trabajador['apellidos']} {trabajador['nombres']}",
        "fecha": fecha.isoformat(),
        "hora": hora_texto,
        "origen": _origen_marcacion(entrada) if entrada else None,
        "segundos": 0,
        "tipo": None,
        "tipo_id": None,
        "clave_conteo": None,
        "observacion": None,
        "registrado_por": None,
        "color": None,
        "color_texto": None,
        "texto": hora_texto or ""
    }

    justificacion = datos["justificaciones"].get((trabajador["id"], fecha))

    if fecha in datos["feriados"]:
        celda.update(
            estado="feriado", tipo="Feriado", color=COLOR_FERIADO,
            observacion=datos["feriados"][fecha], texto=hora_texto or "Feriado"
        )
    elif justificacion:
        celda.update(
            estado="falta" if justificacion["es_falta"] else "justificado",
            tipo=justificacion["tipo"],
            tipo_id=justificacion["tipo_id"],
            clave_conteo=justificacion["tipo_id"] or "otros",
            observacion=justificacion["observacion"],
            registrado_por=justificacion["registrado_por"],
            color=justificacion["color"],
            texto=hora_texto or justificacion["tipo"]
        )
    elif fecha_en_vacaciones(datos["vacaciones"].get(trabajador["id"], []), fecha):
        sistema = datos["estados_sistema"]["vacaciones"]
        celda.update(
            estado="vacaciones", tipo=sistema["nombre"], clave_conteo=sistema["clave_conteo"],
            color=sistema["color"], texto=hora_texto or sistema["nombre"]
        )
    elif fecha_en_vacaciones(datos["descansos"].get(trabajador["id"], []), fecha):
        sistema = datos["estados_sistema"]["descanso"]
        celda.update(
            estado="descanso", tipo=sistema["nombre"], clave_conteo=sistema["clave_conteo"],
            color=sistema["color"], texto=hora_texto or sistema["nombre"]
        )
    elif entrada:
        hora_programada, _ = horario_del_trabajador(
            trabajador["hora_entrada"], trabajador["hora_salida"], hora_estandar
        )
        celda.update(estado="marcacion", segundos=segundos_tardanza(hora_programada, entrada["hora"]))

    if celda["color"]:
        celda["color_texto"] = color_texto(celda["color"])
    return celda


# ---------------------------------------------------------------------------
# Armado del panel
# ---------------------------------------------------------------------------

def _etiqueta_dia(fecha):
    return f"{fecha.day:02d} {MESES_ABREV[fecha.month]}"


def _etiqueta_rango(dias):
    if len(dias) == 1:
        return _etiqueta_dia(dias[0])
    return f"{_etiqueta_dia(dias[0])} – {_etiqueta_dia(dias[-1])}"


def armar_panel(cursor, anio, mes):
    inicio, fin = rango_periodo(anio, mes)
    config = obtener_config_asistencia(cursor)
    umbral = config["umbral_semanal_seg"]
    trabajadores = _trabajadores_del_panel(cursor)
    tipos = _tipos_de_justificacion(cursor)
    datos = _datos_de_rango(cursor, inicio, fin)
    hoy = _hoy()

    semanas = [
        {
            "numero": numero,
            "etiqueta": _etiqueta_rango(dias),
            "dias": [
                {"fecha": dia, "dia": DIAS_ABREV[dia.weekday()], "etiqueta": _etiqueta_dia(dia), "es_hoy": dia == hoy}
                for dia in dias
            ]
        }
        for numero, dias in enumerate(semanas_del_periodo(anio, mes), 1)
    ]

    filas = []
    hay_sin_tipo = False

    for numero, trabajador in enumerate(trabajadores, 1):
        columnas_semana = []
        total_periodo = 0
        dias_con_tardanza = 0
        faltas = 0
        conteos = {}

        for semana in semanas:
            celdas = [evaluar_dia(trabajador, d["fecha"], datos, config["hora_entrada"]) for d in semana["dias"]]
            total_semana = sum(c["segundos"] for c in celdas)
            total_periodo += total_semana

            for celda in celdas:
                celda["tardanza"] = formatear_hms(celda["segundos"])
                if celda["segundos"] > 0:
                    dias_con_tardanza += 1
                if celda["estado"] == "falta":
                    faltas += 1
                elif celda["clave_conteo"]:
                    conteos[celda["clave_conteo"]] = conteos.get(celda["clave_conteo"], 0) + 1
                    hay_sin_tipo = hay_sin_tipo or celda["clave_conteo"] == "otros"

            columnas_semana.append({
                "celdas": celdas,
                "total": formatear_hms(total_semana),
                "supera": total_semana > umbral
            })

        filas.append({
            "numero": numero,
            "trabajador_id": trabajador["id"],
            "nombre": f"{trabajador['apellidos']} {trabajador['nombres']}",
            "semanas": columnas_semana,
            "total": formatear_hms(total_periodo),
            "dias_con_tardanza": dias_con_tardanza,
            "faltas": faltas,
            "conteos": conteos
        })

    estados_propios = [e for e in datos["estados_sistema"].values() if not e["en_catalogo"]]
    columnas_resumen = [
        {"clave": t["clave"], "nombre": t["nombre"]} for t in tipos if not t["es_falta"]
    ] + [{"clave": e["clave"], "nombre": e["nombre"]} for e in estados_propios]
    if hay_sin_tipo:
        columnas_resumen.append({"clave": "otros", "nombre": "Otros"})

    leyenda = (
        [{"nombre": t["nombre"], "color": t["color"]} for t in tipos]
        + [{"nombre": e["nombre"], "color": e["color"]} for e in estados_propios]
        + [{"nombre": "Feriado", "color": COLOR_FERIADO}]
    )
    if hay_sin_tipo:
        leyenda.append({"nombre": "Otros (sin tipo)", "color": COLOR_SIN_TIPO})

    return {
        "titulo": f"{MESES_ES[mes].capitalize()} {anio}",
        "rango": f"{inicio.day} {MESES_ES[inicio.month]} – {fin.day} {MESES_ES[fin.month]}",
        "semanas": semanas,
        "filas": filas,
        "tipos": tipos,
        "leyenda": leyenda,
        "columnas_resumen": columnas_resumen,
        "hora_entrada": config["hora_entrada"].strftime("%H:%M:%S"),
        "umbral": formatear_hms(umbral)
    }


def resumen_del_dia(cursor, fecha):
    """Indicadores del inicio. Quien marco y ademas tiene justificacion cuenta
    en Presentes y en Justificados; "Sin marcar" solo tiene a quienes no
    marcaron ni estan justificados, y una falta registrada queda ahi."""
    config = obtener_config_asistencia(cursor)
    datos = _datos_de_rango(cursor, fecha, fecha)
    dia_laborable = fecha.weekday() < 5 and fecha not in datos["feriados"]

    indicadores = {"presentes": 0, "tardanzas": 0, "justificados": 0, "sin_marcar": 0}

    for trabajador in _trabajadores_del_panel(cursor):
        if trabajador["fecha_ingreso"] and trabajador["fecha_ingreso"] > fecha:
            continue  # todavia no empieza a trabajar

        celda = evaluar_dia(trabajador, fecha, datos, config["hora_entrada"])
        justificado = celda["estado"] in ("justificado", "vacaciones", "descanso")

        if celda["hora"]:
            indicadores["presentes"] += 1
        if celda["segundos"] > 0:
            indicadores["tardanzas"] += 1
        if justificado:
            indicadores["justificados"] += 1
        if dia_laborable and not celda["hora"] and not justificado:
            indicadores["sin_marcar"] += 1

    cursor.execute(
        "SELECT COUNT(*) FROM asistencias WHERE fecha = %s AND tipo_marcaje IN ('0', '1')",
        (fecha,)
    )
    indicadores["marcaciones"] = cursor.fetchone()[0]
    return indicadores


def _periodo_pedido():
    hoy = _hoy()
    anio = request.args.get("anio", type=int)
    mes = request.args.get("mes", type=int)
    if not anio or not mes or not 1 <= mes <= 12 or not 2000 <= anio <= 2100:
        return periodo_de_fecha(hoy)
    return anio, mes


@asistencia_bp.route("/asistencia")
@login_requerido
def pagina_asistencia():
    anio, mes = _periodo_pedido()

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    panel = armar_panel(cursor, anio, mes)
    cursor.close()
    conexion.close()

    anio_prev, mes_prev = periodo_vecino(anio, mes, -1)
    anio_next, mes_next = periodo_vecino(anio, mes, 1)
    periodo_actual = periodo_de_fecha(_hoy())

    return render_template(
        "asistencia.html",
        panel=panel,
        anio=anio, mes=mes,
        anio_prev=anio_prev, mes_prev=mes_prev,
        anio_next=anio_next, mes_next=mes_next,
        es_periodo_actual=(anio, mes) == periodo_actual,
        active_page="asistencia"
    )


# ---------------------------------------------------------------------------
# Registro de marcacion o justificacion
# ---------------------------------------------------------------------------

def _codigos_del_trabajador(cursor, trabajador_id):
    """Un trabajador puede tener marcaciones bajo su codigo o bajo su DNI.
    Devuelve None si no existe."""
    cursor.execute("SELECT codigo_empleado, dni FROM trabajadores WHERE id = %s", (trabajador_id,))
    fila = cursor.fetchone()
    if not fila:
        return None
    return [codigo for codigo in fila if codigo]


def _guardar_marcacion(cursor, trabajador_id, codigos, fecha, hora):
    cursor.execute(
        "DELETE FROM ajustes_asistencia WHERE trabajador_id = %s AND fecha = %s",
        (trabajador_id, fecha)
    )

    cursor.execute("""
        SELECT MIN(hora) FROM asistencias
        WHERE codigo_empleado = ANY(%s) AND fecha = %s AND tipo_marcaje = '0'
    """, (codigos, fecha))
    if cursor.fetchone()[0] == hora:
        return  # ya es la entrada vigente: no hay nada que corregir

    cursor.execute("""
        DELETE FROM asistencias
        WHERE codigo_empleado = ANY(%s) AND fecha = %s AND tipo_marcaje = '0' AND sn_dispositivo = %s
    """, (codigos, fecha, SN_MANUAL))
    cursor.execute("""
        UPDATE asistencias SET tipo_marcaje = %s
        WHERE codigo_empleado = ANY(%s) AND fecha = %s AND tipo_marcaje = '0'
    """, (TIPO_ENTRADA_ANULADA, codigos, fecha))

    ahora = datetime.now()
    cursor.execute("""
        INSERT INTO asistencias (
            codigo_empleado, fecha_hora, fecha, hora, tipo_marcaje,
            sn_dispositivo, fecha_recepcion, registrado_por
        )
        VALUES (%s, %s, %s, %s, '0', %s, %s, %s)
        ON CONFLICT (codigo_empleado, fecha_hora, sn_dispositivo)
        DO UPDATE SET tipo_marcaje = '0', registrado_por = EXCLUDED.registrado_por
    """, (
        codigos[0], datetime.combine(fecha, hora), fecha, hora,
        SN_MANUAL, ahora, session.get("username")
    ))


def _leer_fecha(texto):
    try:
        return datetime.strptime((texto or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _leer_hora(texto):
    for formato in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime((texto or "").strip(), formato).time()
        except ValueError:
            continue
    return None


@asistencia_bp.route("/api/asistencia/registro", methods=["POST"])
@login_requerido
def api_guardar_registro():
    datos = request.get_json(silent=True) or {}
    trabajador_id = datos.get("trabajadorId")
    fecha = _leer_fecha(datos.get("fecha"))
    tipo_registro = datos.get("tipoRegistro")

    if type(trabajador_id) is not int or not fecha:
        return jsonify({"error": "Trabajador y fecha son obligatorios"}), 400
    if tipo_registro not in ("marcacion", "justificacion"):
        return jsonify({"error": "Elige marcación o justificación"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        codigos = _codigos_del_trabajador(cursor, trabajador_id)
        if codigos is None:
            return jsonify({"error": "Trabajador no encontrado"}), 404

        if tipo_registro == "marcacion":
            hora = _leer_hora(datos.get("hora"))
            if not hora:
                return jsonify({"error": "Escribe la hora de entrada (hh:mm:ss)"}), 400
            if fecha > _hoy():
                return jsonify({"error": "No se puede registrar una marcación en una fecha futura"}), 400
            if not codigos:
                return jsonify({"error": "El trabajador no tiene código de empleado ni DNI"}), 400

            _guardar_marcacion(cursor, trabajador_id, codigos, fecha, hora)
        else:
            tipo_id = datos.get("tipoId")
            cursor.execute("SELECT nombre FROM motivos_justificacion WHERE id = %s", (tipo_id,))
            tipo = cursor.fetchone() if type(tipo_id) is int else None
            if not tipo:
                return jsonify({"error": "Elige un tipo de justificación"}), 400

            observacion = (datos.get("observacion") or "").strip() or None
            cursor.execute("""
                INSERT INTO ajustes_asistencia (trabajador_id, fecha, motivo, tipo_id, observacion, creado_por, creado_en)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (trabajador_id, fecha)
                DO UPDATE SET motivo = EXCLUDED.motivo, tipo_id = EXCLUDED.tipo_id, observacion = EXCLUDED.observacion,
                              creado_por = EXCLUDED.creado_por, creado_en = EXCLUDED.creado_en
            """, (trabajador_id, fecha, tipo[0], tipo_id, observacion, session.get("username"), datetime.now()))

        conexion.commit()
        return jsonify({"ok": True})
    except Exception as error:
        conexion.rollback()
        print("ERROR GUARDANDO REGISTRO DE ASISTENCIA:", error)
        return jsonify({"error": "No se pudo guardar el registro"}), 500
    finally:
        cursor.close()
        conexion.close()


@asistencia_bp.route("/api/asistencia/registro", methods=["DELETE"])
@login_requerido
def api_quitar_registro():
    """Quita la justificacion y la correccion manual del dia. Si habia una
    marcacion original anulada, vuelve a quedar vigente."""
    datos = request.get_json(silent=True) or {}
    trabajador_id = datos.get("trabajadorId")
    fecha = _leer_fecha(datos.get("fecha"))

    if type(trabajador_id) is not int or not fecha:
        return jsonify({"error": "Trabajador y fecha son obligatorios"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        codigos = _codigos_del_trabajador(cursor, trabajador_id)
        if codigos is None:
            return jsonify({"error": "Trabajador no encontrado"}), 404

        cursor.execute(
            "DELETE FROM ajustes_asistencia WHERE trabajador_id = %s AND fecha = %s",
            (trabajador_id, fecha)
        )
        cursor.execute("""
            DELETE FROM asistencias
            WHERE codigo_empleado = ANY(%s) AND fecha = %s AND tipo_marcaje = '0' AND sn_dispositivo = %s
        """, (codigos, fecha, SN_MANUAL))
        cursor.execute("""
            UPDATE asistencias SET tipo_marcaje = '0'
            WHERE codigo_empleado = ANY(%s) AND fecha = %s AND tipo_marcaje = %s
        """, (codigos, fecha, TIPO_ENTRADA_ANULADA))
        conexion.commit()
        return jsonify({"ok": True})
    except Exception as error:
        conexion.rollback()
        print("ERROR QUITANDO REGISTRO DE ASISTENCIA:", error)
        return jsonify({"error": "No se pudo quitar el registro"}), 500
    finally:
        cursor.close()
        conexion.close()


# ---------------------------------------------------------------------------
# Importacion masiva de marcaciones (Excel o CSV)
# ---------------------------------------------------------------------------

ENCABEZADOS = {
    "codigo": {"codigo", "codigoempleado", "codempleado", "acno", "dni", "pin", "id", "idusuario", "iddeusuario"},
    "fecha_hora": {"fechahora", "fechayhora", "datetime", "tiempo", "marcacion"},
    "fecha": {"fecha", "date", "dia"},
    "hora": {"hora", "time", "horaentrada", "entrada"},
    "tipo": {"tipo", "tipomarcaje", "tipodemarcaje", "estado"},
}
FORMATOS_FECHA = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y")
FORMATOS_HORA = ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p")


def _normalizar_encabezado(valor):
    texto = unicodedata.normalize("NFKD", str(valor or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", texto.lower())


def _filas_del_archivo(nombre, contenido):
    """Devuelve las filas del archivo como listas de valores."""
    if nombre.endswith(".xlsx"):
        libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
        filas = [list(fila) for fila in libro.active.iter_rows(values_only=True)]
        libro.close()
        return filas

    try:
        texto = contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = contenido.decode("latin-1")

    primera_linea = texto.splitlines()[0] if texto.strip() else ""
    separador = max(";,\t", key=primera_linea.count)
    return list(csv.reader(io.StringIO(texto), delimiter=separador))


def _ubicar_columnas(filas):
    """Busca la fila de encabezados (algunos reportes traen un titulo antes)."""
    for indice, fila in enumerate(filas[:15]):
        columnas = {}
        for posicion, valor in enumerate(fila):
            normalizado = _normalizar_encabezado(valor)
            for campo, nombres in ENCABEZADOS.items():
                if normalizado in nombres and campo not in columnas:
                    columnas[campo] = posicion

        tiene_momento = "fecha_hora" in columnas or ("fecha" in columnas and "hora" in columnas)
        if "codigo" in columnas and tiene_momento:
            return indice, columnas
    return None, None


def _a_fecha(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor or "").strip()
    for formato in FORMATOS_FECHA:
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def _a_hora(valor):
    if isinstance(valor, datetime):
        return valor.time().replace(microsecond=0)
    if isinstance(valor, time):
        return valor.replace(microsecond=0)
    if isinstance(valor, timedelta):
        return (datetime.min + valor).time().replace(microsecond=0)
    texto = str(valor or "").strip().upper()
    for formato in FORMATOS_HORA:
        try:
            return datetime.strptime(texto, formato).time()
        except ValueError:
            continue
    return None


def _a_codigo(valor):
    # Excel guarda los codigos numericos como float: 12345.0 -> "12345".
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor if valor is not None else "").strip()


def _momento_de_fila(fila, columnas):
    if "fecha_hora" in columnas:
        valor = fila[columnas["fecha_hora"]]
        if isinstance(valor, datetime):
            return valor.date(), _a_hora(valor)
        partes = str(valor or "").strip().split(None, 1)
        if len(partes) == 2:
            return _a_fecha(partes[0]), _a_hora(partes[1])
        return None, None
    return _a_fecha(fila[columnas["fecha"]]), _a_hora(fila[columnas["hora"]])


def _tipo_de_fila(fila, columnas):
    if "tipo" not in columnas:
        return "0"
    valor = _normalizar_encabezado(fila[columnas["tipo"]])
    return "1" if valor in ("1", "salida", "out", "cout", "checkout") else "0"


def _importar_filas(cursor, filas, indice_encabezado, columnas, usuario):
    cursor.execute("SELECT codigo_empleado, dni FROM trabajadores")
    codigos_validos = {codigo for fila in cursor.fetchall() for codigo in fila if codigo}

    hoy = _hoy()
    resultado = {"insertadas": 0, "duplicadas": 0, "errores": 0, "detalle": []}

    def rechazar(numero_fila, motivo):
        resultado["errores"] += 1
        if len(resultado["detalle"]) < MAX_ERRORES_MOSTRADOS:
            resultado["detalle"].append(f"Fila {numero_fila}: {motivo}")

    ultima_columna = max(columnas.values())

    for numero_fila, fila in enumerate(filas[indice_encabezado + 1:], indice_encabezado + 2):
        if not any(str(v if v is not None else "").strip() for v in fila):
            continue
        if len(fila) <= ultima_columna:
            fila = fila + [None] * (ultima_columna + 1 - len(fila))

        codigo = _a_codigo(fila[columnas["codigo"]])
        fecha, hora = _momento_de_fila(fila, columnas)

        if codigo not in codigos_validos:
            rechazar(numero_fila, f"no hay ningún trabajador con código o DNI \"{codigo}\"")
        elif not fecha:
            rechazar(numero_fila, "la fecha no es válida")
        elif not hora:
            rechazar(numero_fila, "la hora no es válida")
        elif fecha > hoy:
            rechazar(numero_fila, "la fecha es futura")
        else:
            cursor.execute("""
                INSERT INTO asistencias (
                    codigo_empleado, fecha_hora, fecha, hora, tipo_marcaje,
                    sn_dispositivo, fecha_recepcion, registrado_por
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (codigo_empleado, fecha_hora, sn_dispositivo) DO NOTHING
            """, (
                codigo, datetime.combine(fecha, hora), fecha, hora,
                _tipo_de_fila(fila, columnas), SN_IMPORTADO, datetime.now(), usuario
            ))
            resultado["insertadas" if cursor.rowcount else "duplicadas"] += 1

    return resultado


@asistencia_bp.route("/api/asistencia/importar", methods=["POST"])
@login_requerido
def api_importar_marcaciones():
    archivo = request.files.get("archivo")
    if not archivo or not archivo.filename:
        return jsonify({"error": "Elige un archivo Excel (.xlsx) o CSV"}), 400

    nombre = archivo.filename.lower()
    if not nombre.endswith((".xlsx", ".csv", ".txt")):
        return jsonify({"error": "Formato no admitido: usa .xlsx o .csv (guarda los .xls como .xlsx)"}), 400

    contenido = archivo.read(MAX_BYTES_IMPORTACION + 1)
    if len(contenido) > MAX_BYTES_IMPORTACION:
        return jsonify({"error": "El archivo supera el límite de 5 MB"}), 400

    try:
        filas = _filas_del_archivo(nombre, contenido)
    except Exception as error:
        print("ERROR LEYENDO ARCHIVO DE MARCACIONES:", error)
        return jsonify({"error": "No se pudo leer el archivo"}), 400

    if len(filas) > MAX_FILAS_IMPORTACION:
        return jsonify({"error": f"El archivo supera el límite de {MAX_FILAS_IMPORTACION} filas"}), 400

    indice_encabezado, columnas = _ubicar_columnas(filas)
    if columnas is None:
        return jsonify({
            "error": "No se encontraron los encabezados: se necesita Código (o DNI) y Fecha y Hora"
        }), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        resultado = _importar_filas(cursor, filas, indice_encabezado, columnas, session.get("username"))
        conexion.commit()
        return jsonify({"ok": True, **resultado})
    except Exception as error:
        conexion.rollback()
        print("ERROR IMPORTANDO MARCACIONES:", error)
        return jsonify({"error": "No se pudieron importar las marcaciones"}), 500
    finally:
        cursor.close()
        conexion.close()


# ---------------------------------------------------------------------------
# Exportacion a Excel
# ---------------------------------------------------------------------------

def _relleno(color):
    return PatternFill("solid", start_color=color.lstrip("#").upper())


def _escribir(hoja, fila, columna, valor, color=None, negrita=False, color_fuente=None, centrado=True):
    celda = hoja.cell(row=fila, column=columna)
    celda.value = valor
    # Un nombre u observacion que empiece con "=" no debe abrirse como formula.
    if isinstance(valor, str):
        celda.data_type = "s"
    celda.border = BORDE
    celda.font = Font(bold=negrita, color=(color_fuente or COLOR_TEXTO).lstrip("#").upper())
    celda.alignment = Alignment(horizontal="center" if centrado else "left", vertical="center")
    if color:
        celda.fill = _relleno(color)
    return celda


BORDE = Border(*(Side(style="thin", color="B9BAB2") for _ in range(4)))


def _hoja_panel(hoja, panel):
    hoja.title = "Panel"
    _escribir(hoja, 1, 1, f"Panel de asistencia · Periodo {panel['titulo']} ({panel['rango']})", negrita=True, centrado=False).border = Border()

    _escribir(hoja, 3, 1, "N.º", negrita=True)
    _escribir(hoja, 3, 2, "Trabajador", negrita=True)
    hoja.merge_cells(start_row=3, start_column=1, end_row=4, end_column=1)
    hoja.merge_cells(start_row=3, start_column=2, end_row=4, end_column=2)
    hoja.column_dimensions["A"].width = 6
    hoja.column_dimensions["B"].width = 36

    columna = 3
    for semana in panel["semanas"]:
        inicio = columna
        for dia in semana["dias"]:
            _escribir(hoja, 3, columna, f"Semana {semana['numero']}", negrita=True)
            _escribir(hoja, 4, columna, f"{dia['dia']} {dia['etiqueta']}", negrita=True)
            hoja.column_dimensions[get_column_letter(columna)].width = 13
            columna += 1
        _escribir(hoja, 3, columna, semana["etiqueta"], COLOR_SEMANA, negrita=True)
        _escribir(hoja, 4, columna, "Tardanzas", COLOR_SEMANA, negrita=True)
        hoja.column_dimensions[get_column_letter(columna)].width = 18
        if columna - 1 > inicio:
            hoja.merge_cells(start_row=3, start_column=inicio, end_row=3, end_column=columna - 1)
        columna += 1

    _escribir(hoja, 3, columna, "Total tardanzas del periodo", COLOR_TOTAL_PERIODO, negrita=True)
    hoja.merge_cells(start_row=3, start_column=columna, end_row=4, end_column=columna)
    hoja.cell(row=3, column=columna).alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    hoja.column_dimensions[get_column_letter(columna)].width = 16

    fila_excel = 5
    for fila in panel["filas"]:
        _escribir(hoja, fila_excel, 1, fila["numero"])
        _escribir(hoja, fila_excel, 2, fila["nombre"], centrado=False)
        columna = 3
        for semana in fila["semanas"]:
            for celda in semana["celdas"]:
                fuente = celda["color_texto"] or (COLOR_ROJO if celda["segundos"] > 0 else None)
                _escribir(hoja, fila_excel, columna, celda["texto"], celda["color"], color_fuente=fuente)
                columna += 1
            _escribir(
                hoja, fila_excel, columna, semana["total"], COLOR_SEMANA, negrita=True,
                color_fuente=COLOR_ROJO if semana["supera"] else None
            )
            columna += 1
        _escribir(hoja, fila_excel, columna, fila["total"], COLOR_TOTAL_PERIODO, negrita=True)
        fila_excel += 1

    fila_excel += 1
    _escribir(hoja, fila_excel, 2, "Leyenda", negrita=True, centrado=False).border = Border()
    for entrada in panel["leyenda"]:
        fila_excel += 1
        _escribir(hoja, fila_excel, 1, "", entrada["color"])
        _escribir(hoja, fila_excel, 2, entrada["nombre"], centrado=False).border = Border()

    hoja.freeze_panes = "C5"


def _hoja_resumen(hoja, panel):
    hoja.title = "Resumen del periodo"
    encabezados = ["N.º", "Trabajador", "Total tardanzas", "Días con tardanza", "Faltas injustificadas"]
    encabezados += [c["nombre"] for c in panel["columnas_resumen"]]

    for columna, titulo in enumerate(encabezados, 1):
        _escribir(hoja, 1, columna, titulo, negrita=True).alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=True
        )
        hoja.column_dimensions[get_column_letter(columna)].width = 14
    hoja.column_dimensions["A"].width = 6
    hoja.column_dimensions["B"].width = 36

    for numero_fila, fila in enumerate(panel["filas"], 2):
        valores = [fila["numero"], fila["nombre"], fila["total"], fila["dias_con_tardanza"], fila["faltas"]]
        valores += [fila["conteos"].get(c["clave"], 0) for c in panel["columnas_resumen"]]
        for columna, valor in enumerate(valores, 1):
            _escribir(hoja, numero_fila, columna, valor, centrado=columna != 2)

    hoja.freeze_panes = "C2"


@asistencia_bp.route("/asistencia/exportar")
@login_requerido
def exportar_panel():
    anio, mes = _periodo_pedido()

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    panel = armar_panel(cursor, anio, mes)
    cursor.close()
    conexion.close()

    libro = Workbook()
    _hoja_panel(libro.active, panel)
    _hoja_resumen(libro.create_sheet(), panel)

    salida = io.BytesIO()
    libro.save(salida)

    respuesta = Response(
        salida.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    respuesta.headers["Content-Disposition"] = f"attachment; filename=asistencia_{anio}-{mes:02d}.xlsx"
    return respuesta
