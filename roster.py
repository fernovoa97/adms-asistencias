# roster.py
# Roster de mina: programacion mensual de los trabajadores que suben a mina.
# Una fila por trabajador y mes (mina, guardia, regimen, etc.) y un codigo por
# trabajador y dia (T, DL, VA, DM...). Los dias se pueden generar a partir del
# regimen (dias de trabajo x dias de descanso y fecha de subida) y corregir a
# mano. Vacaciones, descansos medicos y feriados ya registrados en el sistema
# aparecen solos. Se exporta a Excel con el formato del modelo de la empresa.

import io
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg2
from flask import Blueprint, Response, jsonify, render_template, request, session
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from auth import login_requerido
from db import obtener_conexion
from vacaciones import obtener_rangos_vacaciones

roster_bp = Blueprint("roster", __name__)

ZONA_HORARIA_LOCAL = ZoneInfo("America/Lima")

MESES_ES = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
]
INICIAL_DIA = ["L", "M", "M", "J", "V", "S", "D"]

# Para que suma cada codigo en los totales (columna corta en la grilla).
CATEGORIAS = [
    {"clave": "trabajado", "nombre": "Trabajado", "corto": "Trab."},
    {"clave": "descanso", "nombre": "Descanso", "corto": "Desc."},
    {"clave": "vacaciones", "nombre": "Vacaciones", "corto": "Vac."},
    {"clave": "descanso_medico", "nombre": "Descanso médico", "corto": "DM"},
    {"clave": "licencia", "nombre": "Licencia", "corto": "Lic."},
    {"clave": "falta", "nombre": "Falta", "corto": "Falta"},
    {"clave": "pago_doble", "nombre": "Pago doble", "corto": "9A"},
    {"clave": "otro", "nombre": "Otro (no suma)", "corto": None},
]
CLAVES_CATEGORIA = {c["clave"] for c in CATEGORIAS}
CATEGORIAS_TOTALES = [c for c in CATEGORIAS if c["corto"]]
# Dias que cuentan para las horas trabajadas (dias x horas de la guardia).
CATEGORIAS_CON_HORAS = ("trabajado", "pago_doble")

GUARDIAS = ["A", "B", "C"]
MAX_CAMBIOS = 3000


def _hoy():
    return datetime.now(ZONA_HORARIA_LOCAL).date()


def _mes_pedido(fuente=None):
    fuente = fuente if fuente is not None else request.args
    hoy = _hoy()
    try:
        anio = int(fuente.get("anio") or hoy.year)
        mes = int(fuente.get("mes") or hoy.month)
    except (TypeError, ValueError):
        anio, mes = hoy.year, hoy.month
    if not (2000 <= anio <= 2100 and 1 <= mes <= 12):
        anio, mes = hoy.year, hoy.month
    return anio, mes


def _mes_vecino(anio, mes, paso):
    indice = anio * 12 + (mes - 1) + paso
    return indice // 12, indice % 12 + 1


def _dias_del_mes(anio, mes):
    siguiente_anio, siguiente_mes = _mes_vecino(anio, mes, 1)
    ultimo = (date(siguiente_anio, siguiente_mes, 1) - timedelta(days=1)).day
    return [date(anio, mes, d) for d in range(1, ultimo + 1)]


def _titulo_mes(anio, mes):
    return f"{MESES_ES[mes].capitalize()} {anio}"


def _leer_fecha(texto):
    try:
        return datetime.strptime(str(texto or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _color_valido(texto):
    return bool(re.fullmatch(r"#[0-9a-fA-F]{6}", texto or ""))


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------

def obtener_codigos(cursor):
    cursor.execute("""
        SELECT id, codigo, nombre, color, color_texto, categoria, sistema, orden
        FROM roster_codigos ORDER BY orden, codigo
    """)
    columnas = ["id", "codigo", "nombre", "color", "color_texto", "categoria", "sistema", "orden"]
    return [dict(zip(columnas, f)) for f in cursor.fetchall()]


def obtener_minas(cursor):
    cursor.execute("""
        SELECT m.id, m.nombre, (SELECT COUNT(*) FROM roster_filas f WHERE f.mina_id = m.id)
        FROM roster_minas m ORDER BY LOWER(m.nombre)
    """)
    return [{"id": f[0], "nombre": f[1], "filas": f[2]} for f in cursor.fetchall()]


def _residencia_de_ficha(distrito, provincia, departamento):
    partes = [p for p in (provincia or distrito, departamento) if p]
    # "Huancayo - Junin"; sin repetir si provincia y departamento coinciden.
    if len(partes) == 2 and partes[0].strip().lower() == partes[1].strip().lower():
        partes = partes[:1]
    return " - ".join(partes)


def _filas_del_mes(cursor, anio, mes, mina_id=None):
    filtro, parametros = "", [anio, mes]
    if mina_id:
        filtro = "AND f.mina_id = %s"
        parametros.append(mina_id)
    cursor.execute(f"""
        SELECT f.id, f.trabajador_id, t.apellidos, t.nombres, t.dni, t.cargo, t.sexo,
               t.distrito, t.provincia, t.departamento,
               f.mina_id, m.nombre, f.guardia, f.regimen_trabajo, f.regimen_descanso,
               f.inicio_ciclo, f.horas_guardia, f.condicion, f.conduce_mina, f.residencia
        FROM roster_filas f
        JOIN trabajadores t ON t.id = f.trabajador_id
        LEFT JOIN roster_minas m ON m.id = f.mina_id
        WHERE f.anio = %s AND f.mes = %s {filtro}
        ORDER BY m.nombre NULLS LAST, f.guardia NULLS LAST, t.apellidos, t.nombres
    """, parametros)
    filas = []
    for (fila_id, t_id, apellidos, nombres, dni, cargo, sexo, distrito, provincia, departamento,
         m_id, mina, guardia, reg_t, reg_d, inicio, horas, condicion, conduce, residencia) in cursor.fetchall():
        regimen = f"{reg_t}x{reg_d}" if reg_t and reg_d else ""
        filas.append({
            "id": fila_id,
            "trabajador_id": t_id,
            "nombre": f"{apellidos} {nombres}".strip(),
            "dni": dni or "",
            "cargo": cargo or "",
            "sexo": sexo or "",
            "mina_id": m_id,
            "mina": mina or "",
            "guardia": guardia or "",
            "regimen_trabajo": reg_t,
            "regimen_descanso": reg_d,
            "regimen": regimen,
            "inicio_ciclo": inicio.isoformat() if inicio else "",
            "horas_guardia": float(horas) if horas is not None else 12.0,
            "condicion": condicion or "",
            "conduce_mina": bool(conduce),
            "residencia": residencia or "",
            "residencia_ficha": _residencia_de_ficha(distrito, provincia, departamento),
        })
    return filas


def _eventos_del_sistema(cursor, trabajador_ids, inicio, fin):
    """Vacaciones y descansos medicos ya registrados en sus modulos."""
    vacaciones = obtener_rangos_vacaciones(cursor)
    cursor.execute("""
        SELECT trabajador_id, fecha_inicio, fecha_fin FROM descansos_medicos
        WHERE fecha_inicio <= %s AND fecha_fin >= %s
    """, (fin, inicio))
    descansos = {}
    for t_id, desde, hasta in cursor.fetchall():
        descansos.setdefault(t_id, []).append((desde, hasta))
    return (
        {t: vacaciones.get(t, []) for t in trabajador_ids},
        {t: descansos.get(t, []) for t in trabajador_ids},
    )


def armar_roster(cursor, anio, mes, mina_id=None):
    dias = _dias_del_mes(anio, mes)
    inicio, fin = dias[0], dias[-1]
    hoy = _hoy()

    codigos = obtener_codigos(cursor)
    por_id = {c["id"]: c for c in codigos}
    por_codigo = {c["codigo"]: c for c in codigos}
    id_va = por_codigo.get("VA", {}).get("id")
    id_dm = por_codigo.get("DM", {}).get("id")
    id_fe = por_codigo.get("FE", {}).get("id")

    filas = _filas_del_mes(cursor, anio, mes, mina_id)
    ids = [f["trabajador_id"] for f in filas]

    guardados = {}
    if ids:
        cursor.execute("""
            SELECT trabajador_id, fecha, codigo_id, manual FROM roster_dias
            WHERE trabajador_id = ANY(%s) AND fecha BETWEEN %s AND %s
        """, (ids, inicio, fin))
        for t_id, fecha, codigo_id, manual in cursor.fetchall():
            guardados[(t_id, fecha)] = (codigo_id, manual)

    cursor.execute("SELECT fecha, descripcion FROM feriados WHERE fecha BETWEEN %s AND %s", (inicio, fin))
    feriados = {f[0]: f[1] or "Feriado" for f in cursor.fetchall()}
    vacaciones, descansos = _eventos_del_sistema(cursor, ids, inicio, fin)

    for fila in filas:
        t_id = fila["trabajador_id"]
        celdas = []
        totales = {c["clave"]: 0 for c in CATEGORIAS}
        for fecha in dias:
            codigo_id, manual = guardados.get((t_id, fecha), (None, False))
            auto = None
            if any(d <= fecha <= h for d, h in vacaciones[t_id]):
                auto = id_va
            elif any(d <= fecha <= h for d, h in descansos[t_id]):
                auto = id_dm
            efectivo = resolver_dia(codigo_id, manual, auto, id_fe if fecha in feriados else None)
            codigo = por_id.get(efectivo)
            if codigo:
                totales[codigo["categoria"]] = totales.get(codigo["categoria"], 0) + 1
            celdas.append({
                "fecha": fecha.isoformat(),
                "guardado": codigo_id,
                "manual": bool(manual),
                "auto": auto,
                "feriado": fecha in feriados,
                "efectivo": efectivo,
                "codigo": codigo,
            })
        fila["celdas"] = celdas
        fila["totales"] = totales
        dias_con_horas = sum(totales[c] for c in CATEGORIAS_CON_HORAS)
        fila["horas"] = _formatear_horas(dias_con_horas * fila["horas_guardia"])

    return {
        "anio": anio,
        "mes": mes,
        "titulo": _titulo_mes(anio, mes),
        "dias": [{
            "fecha": d.isoformat(),
            "dia": d.day,
            "inicial": INICIAL_DIA[d.weekday()],
            "domingo": d.weekday() == 6,
            "feriado": feriados.get(d),
            "hoy": d == hoy,
        } for d in dias],
        "filas": filas,
        "codigos": codigos,
    }


def resolver_dia(guardado, manual, auto, feriado):
    """Que codigo se ve en un dia. Prioridad: lo puesto a mano, luego las
    vacaciones o descansos medicos registrados, luego lo generado por el
    regimen y, si no hay nada, el feriado."""
    if guardado and manual:
        return guardado
    if auto:
        return auto
    if guardado:
        return guardado
    return feriado


def _formatear_horas(horas):
    return f"{horas:g}"


# ---------------------------------------------------------------------------
# Generacion por regimen
# ---------------------------------------------------------------------------

def codigo_por_regimen(fecha, inicio_ciclo, dias_trabajo, dias_descanso):
    """"T" o "DL" segun el ciclo que empieza el dia de subida. Antes de la
    subida no hay nada que generar (None)."""
    if not (inicio_ciclo and dias_trabajo and dias_descanso) or fecha < inicio_ciclo:
        return None
    posicion = (fecha - inicio_ciclo).days % (dias_trabajo + dias_descanso)
    return "T" if posicion < dias_trabajo else "DL"


def generar_dias(cursor, fila_id, usuario):
    """Rehace los dias generados (no los puestos a mano) del mes de la fila.
    Devuelve cuantos dias quedaron generados; None si falta el regimen."""
    cursor.execute("""
        SELECT trabajador_id, anio, mes, regimen_trabajo, regimen_descanso, inicio_ciclo
        FROM roster_filas WHERE id = %s
    """, (fila_id,))
    fila = cursor.fetchone()
    if not fila:
        return None
    t_id, anio, mes, dias_trabajo, dias_descanso, inicio_ciclo = fila
    if not (dias_trabajo and dias_descanso and inicio_ciclo):
        return None

    cursor.execute("SELECT codigo, id FROM roster_codigos WHERE codigo IN ('T', 'DL')")
    ids = dict(cursor.fetchall())
    dias = _dias_del_mes(anio, mes)
    cursor.execute("""
        DELETE FROM roster_dias
        WHERE trabajador_id = %s AND fecha BETWEEN %s AND %s AND manual = FALSE
    """, (t_id, dias[0], dias[-1]))

    generados = 0
    ahora = datetime.now()
    for fecha in dias:
        codigo = codigo_por_regimen(fecha, inicio_ciclo, dias_trabajo, dias_descanso)
        if not codigo or codigo not in ids:
            continue
        cursor.execute("""
            INSERT INTO roster_dias (trabajador_id, fecha, codigo_id, manual, actualizado_por, actualizado_en)
            VALUES (%s, %s, %s, FALSE, %s, %s)
            ON CONFLICT (trabajador_id, fecha) DO NOTHING
        """, (t_id, fecha, ids[codigo], usuario, ahora))
        generados += cursor.rowcount
    return generados


# ---------------------------------------------------------------------------
# Pagina
# ---------------------------------------------------------------------------

@roster_bp.route("/roster")
@login_requerido
def pagina_roster():
    anio, mes = _mes_pedido()
    mina_id = request.args.get("mina", type=int)

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    roster = armar_roster(cursor, anio, mes, mina_id)
    minas = obtener_minas(cursor)

    anio_prev, mes_prev = _mes_vecino(anio, mes, -1)
    anio_next, mes_next = _mes_vecino(anio, mes, 1)
    copiables = 0
    if not roster["filas"] and not mina_id:
        cursor.execute("""
            SELECT COUNT(*) FROM roster_filas WHERE anio = %s AND mes = %s
        """, (anio_prev, mes_prev))
        copiables = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM roster_filas WHERE anio = %s AND mes = %s
    """, (anio, mes))
    filas_del_mes = cursor.fetchone()[0]

    cursor.close()
    conexion.close()

    hoy = _hoy()
    return render_template(
        "roster.html",
        active_page="roster",
        roster=roster,
        minas=minas,
        mina_id=mina_id,
        guardias=GUARDIAS,
        categorias=CATEGORIAS,
        categorias_totales=CATEGORIAS_TOTALES,
        anio=anio, mes=mes,
        anio_prev=anio_prev, mes_prev=mes_prev,
        anio_next=anio_next, mes_next=mes_next,
        titulo_prev=_titulo_mes(anio_prev, mes_prev),
        es_mes_actual=(anio, mes) == (hoy.year, hoy.month),
        copiables=copiables,
        filas_del_mes=filas_del_mes,
    )


# ---------------------------------------------------------------------------
# API: trabajadores del roster
# ---------------------------------------------------------------------------

@roster_bp.route("/api/roster/candidatos")
@login_requerido
def api_candidatos():
    """Trabajadores activos que aun no estan en el roster del mes."""
    anio, mes = _mes_pedido()
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("""
        SELECT t.id, t.apellidos, t.nombres, t.dni, t.cargo, s.nombre
        FROM trabajadores t
        LEFT JOIN sedes s ON s.id = t.sede_id
        WHERE t.estado IS DISTINCT FROM 'INACTIVO'
          AND NOT EXISTS (
              SELECT 1 FROM roster_filas f
              WHERE f.trabajador_id = t.id AND f.anio = %s AND f.mes = %s
          )
        ORDER BY t.apellidos, t.nombres
    """, (anio, mes))
    trabajadores = [{
        "id": f[0], "nombre": f"{f[1]} {f[2]}".strip(), "dni": f[3] or "",
        "cargo": f[4] or "", "sede": f[5] or ""
    } for f in cursor.fetchall()]
    cursor.close()
    conexion.close()
    return jsonify({"trabajadores": trabajadores})


def _copiar_fila_previa(cursor, trabajador_id, anio, mes):
    """Datos de mina del ultimo mes en que el trabajador estuvo en el roster."""
    cursor.execute("""
        SELECT mina_id, guardia, regimen_trabajo, regimen_descanso, inicio_ciclo,
               horas_guardia, condicion, conduce_mina, residencia
        FROM roster_filas
        WHERE trabajador_id = %s AND (anio * 12 + mes) < %s
        ORDER BY anio DESC, mes DESC LIMIT 1
    """, (trabajador_id, anio * 12 + mes))
    return cursor.fetchone()


def _insertar_fila(cursor, trabajador_id, anio, mes, mina_id, previa):
    if previa:
        (p_mina, guardia, reg_t, reg_d, inicio, horas, condicion, conduce, residencia) = previa
        mina_id = mina_id or p_mina
    else:
        guardia = reg_t = reg_d = inicio = condicion = residencia = None
        horas, conduce = 12, False
    cursor.execute("""
        INSERT INTO roster_filas (anio, mes, trabajador_id, mina_id, guardia, regimen_trabajo,
                                  regimen_descanso, inicio_ciclo, horas_guardia, condicion,
                                  conduce_mina, residencia, creado_en)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (anio, mes, trabajador_id) DO NOTHING
        RETURNING id
    """, (anio, mes, trabajador_id, mina_id, guardia, reg_t, reg_d, inicio, horas,
          condicion, conduce, residencia, datetime.now()))
    fila = cursor.fetchone()
    return fila[0] if fila else None


@roster_bp.route("/api/roster/filas", methods=["POST"])
@login_requerido
def api_agregar_filas():
    datos = request.get_json(silent=True) or {}
    anio, mes = _mes_pedido(datos)
    ids = datos.get("trabajador_ids") or []
    if not isinstance(ids, list) or not ids or not all(type(i) is int for i in ids):
        return jsonify({"error": "Elige al menos un trabajador"}), 400
    mina_id = datos.get("mina_id") or None
    if mina_id is not None and type(mina_id) is not int:
        return jsonify({"error": "Mina no válida"}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        if mina_id:
            cursor.execute("SELECT 1 FROM roster_minas WHERE id = %s", (mina_id,))
            if not cursor.fetchone():
                return jsonify({"error": "Mina no encontrada"}), 404
        cursor.execute("SELECT id FROM trabajadores WHERE id = ANY(%s)", (ids,))
        existentes = {f[0] for f in cursor.fetchall()}
        agregados = 0
        for t_id in ids:
            if t_id not in existentes:
                continue
            fila_id = _insertar_fila(cursor, t_id, anio, mes, mina_id, _copiar_fila_previa(cursor, t_id, anio, mes))
            if fila_id:
                agregados += 1
                generar_dias(cursor, fila_id, session.get("username"))
        conexion.commit()
        return jsonify({"ok": True, "agregados": agregados})
    finally:
        cursor.close()
        conexion.close()


@roster_bp.route("/api/roster/copiar", methods=["POST"])
@login_requerido
def api_copiar_mes_anterior():
    datos = request.get_json(silent=True) or {}
    anio, mes = _mes_pedido(datos)
    anio_prev, mes_prev = _mes_vecino(anio, mes, -1)
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("""
            SELECT f.trabajador_id FROM roster_filas f JOIN trabajadores t ON t.id = f.trabajador_id
            WHERE f.anio = %s AND f.mes = %s AND t.estado IS DISTINCT FROM 'INACTIVO'
        """, (anio_prev, mes_prev))
        copiados = 0
        for (t_id,) in cursor.fetchall():
            fila_id = _insertar_fila(cursor, t_id, anio, mes, None, _copiar_fila_previa(cursor, t_id, anio, mes))
            if fila_id:
                copiados += 1
                generar_dias(cursor, fila_id, session.get("username"))
        conexion.commit()
        return jsonify({"ok": True, "copiados": copiados})
    finally:
        cursor.close()
        conexion.close()


def _entero(valor, minimo, maximo):
    if valor in (None, ""):
        return None
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        raise ValueError("Los días del régimen deben ser números enteros")
    if not minimo <= numero <= maximo:
        raise ValueError(f"Los días del régimen deben estar entre {minimo} y {maximo}")
    return numero


def _leer_datos_fila(datos):
    reg_t = _entero(datos.get("regimen_trabajo"), 1, 60)
    reg_d = _entero(datos.get("regimen_descanso"), 1, 60)
    if bool(reg_t) != bool(reg_d):
        raise ValueError("Completa los días de trabajo y de descanso del régimen")
    inicio = None
    if datos.get("inicio_ciclo"):
        inicio = _leer_fecha(datos.get("inicio_ciclo"))
        if not inicio:
            raise ValueError("Fecha de subida no válida")
    try:
        horas = float(datos.get("horas_guardia") or 12)
    except (TypeError, ValueError):
        raise ValueError("Horas de guardia no válidas")
    if not 1 <= horas <= 24:
        raise ValueError("Las horas de guardia deben estar entre 1 y 24")
    sexo = (datos.get("sexo") or "").strip().upper()
    if sexo not in ("", "M", "F"):
        raise ValueError("Sexo no válido")
    mina_id = datos.get("mina_id") or None
    if mina_id is not None and type(mina_id) is not int:
        raise ValueError("Mina no válida")
    return {
        "mina_id": mina_id,
        "guardia": (datos.get("guardia") or "").strip().upper()[:10] or None,
        "regimen_trabajo": reg_t,
        "regimen_descanso": reg_d,
        "inicio_ciclo": inicio,
        "horas_guardia": horas,
        "condicion": (datos.get("condicion") or "").strip()[:60] or None,
        "conduce_mina": bool(datos.get("conduce_mina")),
        "residencia": (datos.get("residencia") or "").strip()[:120] or None,
        "sexo": sexo or None,
    }


@roster_bp.route("/api/roster/filas/<int:fila_id>", methods=["PUT"])
@login_requerido
def api_editar_fila(fila_id):
    try:
        d = _leer_datos_fila(request.get_json(silent=True) or {})
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        if d["mina_id"]:
            cursor.execute("SELECT 1 FROM roster_minas WHERE id = %s", (d["mina_id"],))
            if not cursor.fetchone():
                return jsonify({"error": "Mina no encontrada"}), 404
        cursor.execute("""
            UPDATE roster_filas SET mina_id = %s, guardia = %s, regimen_trabajo = %s,
                   regimen_descanso = %s, inicio_ciclo = %s, horas_guardia = %s,
                   condicion = %s, conduce_mina = %s, residencia = %s
            WHERE id = %s RETURNING trabajador_id
        """, (d["mina_id"], d["guardia"], d["regimen_trabajo"], d["regimen_descanso"],
              d["inicio_ciclo"], d["horas_guardia"], d["condicion"], d["conduce_mina"],
              d["residencia"], fila_id))
        fila = cursor.fetchone()
        if not fila:
            conexion.rollback()
            return jsonify({"error": "Fila no encontrada"}), 404
        # El sexo es un dato de la persona: se guarda en su ficha.
        cursor.execute("UPDATE trabajadores SET sexo = %s WHERE id = %s", (d["sexo"], fila[0]))
        generados = generar_dias(cursor, fila_id, session.get("username"))
        conexion.commit()
        return jsonify({"ok": True, "generados": generados})
    finally:
        cursor.close()
        conexion.close()


@roster_bp.route("/api/roster/filas/<int:fila_id>", methods=["DELETE"])
@login_requerido
def api_quitar_fila(fila_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("DELETE FROM roster_filas WHERE id = %s RETURNING trabajador_id, anio, mes", (fila_id,))
        fila = cursor.fetchone()
        if not fila:
            conexion.rollback()
            return jsonify({"error": "Fila no encontrada"}), 404
        t_id, anio, mes = fila
        dias = _dias_del_mes(anio, mes)
        cursor.execute("""
            DELETE FROM roster_dias WHERE trabajador_id = %s AND fecha BETWEEN %s AND %s
        """, (t_id, dias[0], dias[-1]))
        conexion.commit()
        return jsonify({"ok": True})
    finally:
        cursor.close()
        conexion.close()


@roster_bp.route("/api/roster/generar", methods=["POST"])
@login_requerido
def api_generar():
    """Vuelve a generar por regimen todas las filas del mes (o de una mina)."""
    datos = request.get_json(silent=True) or {}
    anio, mes = _mes_pedido(datos)
    mina_id = datos.get("mina_id") or None
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        filtro, parametros = "", [anio, mes]
        if mina_id:
            filtro = "AND mina_id = %s"
            parametros.append(mina_id)
        cursor.execute(f"SELECT id FROM roster_filas WHERE anio = %s AND mes = %s {filtro}", parametros)
        filas, sin_regimen = 0, 0
        for (fila_id,) in cursor.fetchall():
            if generar_dias(cursor, fila_id, session.get("username")) is None:
                sin_regimen += 1
            else:
                filas += 1
        conexion.commit()
        return jsonify({"ok": True, "filas": filas, "sin_regimen": sin_regimen})
    finally:
        cursor.close()
        conexion.close()


# ---------------------------------------------------------------------------
# API: dias
# ---------------------------------------------------------------------------

@roster_bp.route("/api/roster/dias", methods=["POST"])
@login_requerido
def api_guardar_dias():
    """Guarda un lote de cambios: [{trabajador_id, fecha, codigo_id|null,
    manual?}]. codigo_id null borra lo guardado (vuelve a lo automatico)."""
    cambios = (request.get_json(silent=True) or {}).get("cambios")
    if not isinstance(cambios, list) or not cambios:
        return jsonify({"error": "No hay cambios"}), 400
    if len(cambios) > MAX_CAMBIOS:
        return jsonify({"error": "Demasiados cambios a la vez"}), 400

    limpios = []
    for cambio in cambios:
        if not isinstance(cambio, dict):
            return jsonify({"error": "Cambio no válido"}), 400
        t_id = cambio.get("trabajador_id")
        fecha = _leer_fecha(cambio.get("fecha"))
        codigo_id = cambio.get("codigo_id")
        if type(t_id) is not int or not fecha or (codigo_id is not None and type(codigo_id) is not int):
            return jsonify({"error": "Cambio no válido"}), 400
        limpios.append((t_id, fecha, codigo_id, cambio.get("manual", True) is not False))

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT id FROM roster_codigos")
        codigos = {f[0] for f in cursor.fetchall()}
        meses = {(f.year, f.month) for _, f, _, _ in limpios}
        cursor.execute("""
            SELECT trabajador_id, anio, mes FROM roster_filas
            WHERE trabajador_id = ANY(%s) AND (anio * 12 + mes) = ANY(%s)
        """, (list({c[0] for c in limpios}), [a * 12 + m for a, m in meses]))
        en_roster = {(t, a, m) for t, a, m in cursor.fetchall()}

        ahora = datetime.now()
        usuario = session.get("username")
        for t_id, fecha, codigo_id, manual in limpios:
            if (t_id, fecha.year, fecha.month) not in en_roster:
                conexion.rollback()
                return jsonify({"error": "El trabajador no está en el roster de ese mes"}), 400
            if codigo_id is None:
                cursor.execute("DELETE FROM roster_dias WHERE trabajador_id = %s AND fecha = %s", (t_id, fecha))
                continue
            if codigo_id not in codigos:
                conexion.rollback()
                return jsonify({"error": "Código no encontrado"}), 400
            cursor.execute("""
                INSERT INTO roster_dias (trabajador_id, fecha, codigo_id, manual, actualizado_por, actualizado_en)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (trabajador_id, fecha) DO UPDATE SET
                    codigo_id = EXCLUDED.codigo_id, manual = EXCLUDED.manual,
                    actualizado_por = EXCLUDED.actualizado_por, actualizado_en = EXCLUDED.actualizado_en
            """, (t_id, fecha, codigo_id, manual, usuario, ahora))
        conexion.commit()
        return jsonify({"ok": True, "guardados": len(limpios)})
    finally:
        cursor.close()
        conexion.close()


# ---------------------------------------------------------------------------
# API: minas y codigos
# ---------------------------------------------------------------------------

@roster_bp.route("/api/roster/minas", methods=["POST"])
@login_requerido
def api_crear_mina():
    nombre = ((request.get_json(silent=True) or {}).get("nombre") or "").strip()[:80]
    if not nombre:
        return jsonify({"error": "Escribe el nombre de la mina"}), 400
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT 1 FROM roster_minas WHERE LOWER(nombre) = LOWER(%s)", (nombre,))
        if cursor.fetchone():
            return jsonify({"error": f"Ya existe la mina {nombre}"}), 409
        cursor.execute("INSERT INTO roster_minas (nombre, creado_en) VALUES (%s, %s) RETURNING id",
                       (nombre, datetime.now()))
        mina_id = cursor.fetchone()[0]
        conexion.commit()
        return jsonify({"ok": True, "id": mina_id}), 201
    finally:
        cursor.close()
        conexion.close()


@roster_bp.route("/api/roster/minas/<int:mina_id>", methods=["PUT"])
@login_requerido
def api_editar_mina(mina_id):
    nombre = ((request.get_json(silent=True) or {}).get("nombre") or "").strip()[:80]
    if not nombre:
        return jsonify({"error": "Escribe el nombre de la mina"}), 400
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT 1 FROM roster_minas WHERE LOWER(nombre) = LOWER(%s) AND id <> %s", (nombre, mina_id))
        if cursor.fetchone():
            return jsonify({"error": f"Ya existe la mina {nombre}"}), 409
        cursor.execute("UPDATE roster_minas SET nombre = %s WHERE id = %s", (nombre, mina_id))
        if cursor.rowcount == 0:
            conexion.rollback()
            return jsonify({"error": "Mina no encontrada"}), 404
        conexion.commit()
        return jsonify({"ok": True})
    finally:
        cursor.close()
        conexion.close()


@roster_bp.route("/api/roster/minas/<int:mina_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_mina(mina_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("DELETE FROM roster_minas WHERE id = %s", (mina_id,))
        if cursor.rowcount == 0:
            conexion.rollback()
            return jsonify({"error": "Mina no encontrada"}), 404
        conexion.commit()
        return jsonify({"ok": True})
    finally:
        cursor.close()
        conexion.close()


def _leer_codigo(datos, sistema=False):
    codigo = (datos.get("codigo") or "").strip().upper()
    nombre = (datos.get("nombre") or "").strip()[:120]
    color = (datos.get("color") or "").strip().lower()
    color_texto = (datos.get("color_texto") or "").strip().lower()
    categoria = datos.get("categoria") or "otro"
    if not sistema and not re.fullmatch(r"[A-Z0-9]{1,4}", codigo):
        raise ValueError("El código debe tener de 1 a 4 letras o números")
    if not nombre:
        raise ValueError("Escribe el significado del código")
    if not _color_valido(color) or not _color_valido(color_texto):
        raise ValueError("Color no válido")
    if categoria not in CLAVES_CATEGORIA:
        raise ValueError("Categoría no válida")
    return codigo, nombre, color, color_texto, categoria


@roster_bp.route("/api/roster/codigos", methods=["POST"])
@login_requerido
def api_crear_codigo():
    try:
        codigo, nombre, color, color_texto, categoria = _leer_codigo(request.get_json(silent=True) or {})
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("""
            INSERT INTO roster_codigos (codigo, nombre, color, color_texto, categoria, orden, creado_en)
            VALUES (%s, %s, %s, %s, %s, (SELECT COALESCE(MAX(orden), 0) + 1 FROM roster_codigos), %s)
            RETURNING id
        """, (codigo, nombre, color, color_texto, categoria, datetime.now()))
        codigo_id = cursor.fetchone()[0]
        conexion.commit()
        return jsonify({"ok": True, "id": codigo_id}), 201
    except psycopg2.errors.UniqueViolation:
        conexion.rollback()
        return jsonify({"error": f"Ya existe el código {codigo}"}), 409
    finally:
        cursor.close()
        conexion.close()


@roster_bp.route("/api/roster/codigos/<int:codigo_id>", methods=["PUT"])
@login_requerido
def api_editar_codigo(codigo_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT codigo, sistema FROM roster_codigos WHERE id = %s", (codigo_id,))
        actual = cursor.fetchone()
        if not actual:
            return jsonify({"error": "Código no encontrado"}), 404
        try:
            codigo, nombre, color, color_texto, categoria = _leer_codigo(
                request.get_json(silent=True) or {}, sistema=actual[1]
            )
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        if actual[1]:
            codigo = actual[0]  # los codigos del sistema no cambian de letra
        cursor.execute("""
            UPDATE roster_codigos SET codigo = %s, nombre = %s, color = %s, color_texto = %s, categoria = %s
            WHERE id = %s
        """, (codigo, nombre, color, color_texto, categoria, codigo_id))
        conexion.commit()
        return jsonify({"ok": True})
    except psycopg2.errors.UniqueViolation:
        conexion.rollback()
        return jsonify({"error": f"Ya existe el código {codigo}"}), 409
    finally:
        cursor.close()
        conexion.close()


@roster_bp.route("/api/roster/codigos/<int:codigo_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_codigo(codigo_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT sistema FROM roster_codigos WHERE id = %s", (codigo_id,))
        fila = cursor.fetchone()
        if not fila:
            return jsonify({"error": "Código no encontrado"}), 404
        if fila[0]:
            return jsonify({"error": "Este código lo usa el sistema y no se puede eliminar"}), 400
        cursor.execute("SELECT COUNT(*) FROM roster_dias WHERE codigo_id = %s", (codigo_id,))
        usados = cursor.fetchone()[0]
        if usados:
            return jsonify({"error": f"El código está puesto en {usados} día(s) del roster. Cámbialos antes de eliminarlo."}), 409
        cursor.execute("DELETE FROM roster_codigos WHERE id = %s", (codigo_id,))
        conexion.commit()
        return jsonify({"ok": True})
    finally:
        cursor.close()
        conexion.close()


# ---------------------------------------------------------------------------
# Excel (formato del modelo de la empresa)
# ---------------------------------------------------------------------------

AZUL_ENCABEZADO = "140A9A"
ROJO_DIAS = "C00000"
BORDE = Border(*(Side(style="thin", color="7F7F7F") for _ in range(4)))
COLUMNAS_DATOS = [
    ("N°", 5), ("SEXO", 6), ("MINA", 14), ("GUARDIA", 9), ("RÉGIMEN TURNO", 10),
    ("CONDICIÓN", 13), ("LUGAR DE RESIDENCIA", 18), ("CARGO", 20), ("CONDUCE EN MINA", 10),
    ("DNI", 11), ("APELLIDOS Y NOMBRES", 34),
]


def _relleno(color):
    return PatternFill("solid", start_color=color.lstrip("#").upper())


def _celda(hoja, fila, columna, valor, fondo=None, texto="000000", negrita=False,
           centrado=True, tamano=10, ajustar=False):
    celda = hoja.cell(row=fila, column=columna, value=valor)
    if isinstance(valor, str):
        celda.data_type = "s"  # nada que empiece con "=" se abre como formula
    celda.font = Font(bold=negrita, color=texto.lstrip("#").upper(), size=tamano)
    celda.alignment = Alignment(horizontal="center" if centrado else "left",
                                vertical="center", wrap_text=ajustar)
    celda.border = BORDE
    if fondo:
        celda.fill = _relleno(fondo)
    return celda


def _hoja_programacion(hoja, roster, nombre_mina):
    hoja.title = "PROGRAMACIÓN"
    dias = roster["dias"]
    n_datos = len(COLUMNAS_DATOS)
    primera_dia = n_datos + 1
    ultima_dia = n_datos + len(dias)
    totales = CATEGORIAS_TOTALES + [{"clave": "horas", "corto": "Horas"}]

    titulo = "DRILLCO TOOLS PERÚ S.A.C." + (f" · {nombre_mina}" if nombre_mina else "")
    _celda(hoja, 1, 1, titulo, "D9E1F2", AZUL_ENCABEZADO, negrita=True, tamano=12)
    hoja.merge_cells(start_row=1, start_column=1, end_row=2, end_column=n_datos)
    _celda(hoja, 1, primera_dia, roster["titulo"], negrita=True, tamano=11)
    hoja.merge_cells(start_row=1, start_column=primera_dia, end_row=1, end_column=ultima_dia)
    _celda(hoja, 1, ultima_dia + 1, "TOTALES", AZUL_ENCABEZADO, "FFFFFF", negrita=True)
    hoja.merge_cells(start_row=1, start_column=ultima_dia + 1, end_row=2, end_column=ultima_dia + len(totales))

    for i, (titulo_col, ancho) in enumerate(COLUMNAS_DATOS, 1):
        _celda(hoja, 3, i, titulo_col, AZUL_ENCABEZADO, "FFFFFF", negrita=True, tamano=9, ajustar=True)
        hoja.column_dimensions[get_column_letter(i)].width = ancho

    for i, dia in enumerate(dias):
        columna = primera_dia + i
        fondo_inicial = "7F7F7F" if dia["feriado"] else ROJO_DIAS
        _celda(hoja, 2, columna, dia["inicial"], fondo_inicial, "FFFFFF", negrita=True, tamano=8)
        fecha = _celda(hoja, 3, columna, date.fromisoformat(dia["fecha"]),
                       "D9D9D9" if dia["feriado"] else None, negrita=True, tamano=8)
        fecha.number_format = "d-mmm"
        fecha.alignment = Alignment(horizontal="center", vertical="center", text_rotation=90)
        hoja.column_dimensions[get_column_letter(columna)].width = 4.2

    for i, total in enumerate(totales):
        columna = ultima_dia + 1 + i
        _celda(hoja, 3, columna, total["corto"], "D9E1F2", AZUL_ENCABEZADO, negrita=True, tamano=9, ajustar=True)
        hoja.column_dimensions[get_column_letter(columna)].width = 6.5

    hoja.row_dimensions[3].height = 62

    for n, fila in enumerate(roster["filas"], 1):
        r = 3 + n
        valores = [
            n, fila["sexo"], fila["mina"], fila["guardia"], fila["regimen"], fila["condicion"],
            fila["residencia"] or fila["residencia_ficha"], fila["cargo"],
            "SÍ" if fila["conduce_mina"] else "NO", fila["dni"], fila["nombre"],
        ]
        for i, valor in enumerate(valores, 1):
            _celda(hoja, r, i, valor, centrado=i not in (7, 8, 11), tamano=9)
        for i, celda in enumerate(fila["celdas"]):
            codigo = celda["codigo"]
            if codigo:
                _celda(hoja, r, primera_dia + i, codigo["codigo"], codigo["color"], codigo["color_texto"],
                       negrita=True, tamano=8)
            else:
                _celda(hoja, r, primera_dia + i, None, tamano=8)
        for i, total in enumerate(totales):
            valor = fila["horas"] if total["clave"] == "horas" else fila["totales"][total["clave"]]
            if total["clave"] == "horas":
                valor = float(valor)
            _celda(hoja, r, ultima_dia + 1 + i, valor, "F2F2F2", negrita=True, tamano=9)

    hoja.freeze_panes = hoja.cell(row=4, column=primera_dia)
    hoja.sheet_view.zoomScale = 90


def _hoja_leyenda(hoja, codigos):
    hoja.title = "LEYENDA"
    _celda(hoja, 1, 1, "LEYENDA", AZUL_ENCABEZADO, "FFFFFF", negrita=True, tamano=11)
    hoja.merge_cells("A1:C1")
    _celda(hoja, 2, 1, "Código", "D9E1F2", negrita=True)
    _celda(hoja, 2, 2, "Significado", "D9E1F2", negrita=True)
    _celda(hoja, 2, 3, "Suma en", "D9E1F2", negrita=True)
    nombres = {c["clave"]: c["nombre"] for c in CATEGORIAS}
    for r, c in enumerate(codigos, 3):
        _celda(hoja, r, 1, c["codigo"], c["color"], c["color_texto"], negrita=True)
        _celda(hoja, r, 2, c["nombre"], centrado=False)
        _celda(hoja, r, 3, nombres.get(c["categoria"], ""), centrado=False)
    hoja.column_dimensions["A"].width = 9
    hoja.column_dimensions["B"].width = 48
    hoja.column_dimensions["C"].width = 18


def _hoja_resumen(hoja, roster):
    """Conteo por codigo de cada trabajador, para planilla."""
    hoja.title = "RESUMEN"
    codigos = roster["codigos"]
    encabezados = ["N°", "APELLIDOS Y NOMBRES", "DNI", "MINA"] + [c["codigo"] for c in codigos] + ["HORAS"]
    for i, titulo in enumerate(encabezados, 1):
        fondo, texto = AZUL_ENCABEZADO, "FFFFFF"
        if 4 < i <= 4 + len(codigos):
            fondo, texto = codigos[i - 5]["color"], codigos[i - 5]["color_texto"]
        _celda(hoja, 1, i, titulo, fondo, texto, negrita=True, tamano=9)
        hoja.column_dimensions[get_column_letter(i)].width = 6
    hoja.column_dimensions["A"].width = 5
    hoja.column_dimensions["B"].width = 34
    hoja.column_dimensions["C"].width = 11
    hoja.column_dimensions["D"].width = 14
    hoja.column_dimensions[get_column_letter(len(encabezados))].width = 8

    for n, fila in enumerate(roster["filas"], 1):
        conteo = {}
        for celda in fila["celdas"]:
            if celda["codigo"]:
                conteo[celda["codigo"]["id"]] = conteo.get(celda["codigo"]["id"], 0) + 1
        valores = [n, fila["nombre"], fila["dni"], fila["mina"]]
        valores += [conteo.get(c["id"], 0) for c in codigos] + [float(fila["horas"])]
        for i, valor in enumerate(valores, 1):
            _celda(hoja, n + 1, i, valor, centrado=i != 2, tamano=9)
    hoja.freeze_panes = "C2"


@roster_bp.route("/roster/exportar")
@login_requerido
def exportar_roster():
    anio, mes = _mes_pedido()
    mina_id = request.args.get("mina", type=int)
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    roster = armar_roster(cursor, anio, mes, mina_id)
    nombre_mina = ""
    if mina_id:
        cursor.execute("SELECT nombre FROM roster_minas WHERE id = %s", (mina_id,))
        fila = cursor.fetchone()
        nombre_mina = fila[0] if fila else ""
    cursor.close()
    conexion.close()

    libro = Workbook()
    _hoja_programacion(libro.active, roster, nombre_mina)
    _hoja_leyenda(libro.create_sheet(), roster["codigos"])
    _hoja_resumen(libro.create_sheet(), roster)

    salida = io.BytesIO()
    libro.save(salida)
    sufijo = re.sub(r"[^A-Za-z0-9]+", "_", nombre_mina).strip("_")
    nombre = f"roster_{anio}-{mes:02d}{'_' + sufijo if sufijo else ''}.xlsx"
    respuesta = Response(
        salida.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    respuesta.headers["Content-Disposition"] = f"attachment; filename={nombre}"
    return respuesta
