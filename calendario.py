# calendario.py
# Modulo de calendario de eventos de la empresa. Vista mensual (por defecto)
# o semanal, con creacion/edicion/eliminacion via un modal (sin recargar
# la pagina para el formulario, aunque si se recarga despues de guardar
# para refrescar la grilla con el dato nuevo -- mantiene el codigo simple).

from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Blueprint, request, render_template, jsonify, session

from auth import login_requerido
from db import obtener_conexion

calendario_bp = Blueprint("calendario", __name__)

ZONA_HORARIA_LOCAL = ZoneInfo("America/Lima")

DIAS_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
DIAS_ES_CORTO = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MESES_ES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]
MESES_ABREV = [
    "", "ene", "feb", "mar", "abr", "may", "jun",
    "jul", "ago", "sep", "oct", "nov", "dic"
]

COLORES_DISPONIBLES = [
    ("#133984", "Azul"),
    ("#9900cc", "Morado"),
    ("#e6c800", "Amarillo"),
    ("#d92b2b", "Rojo"),
    ("#059669", "Verde"),
]


def _obtener_eventos_en_rango(desde, hasta):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("""
        SELECT id, titulo, descripcion, fecha, hora, color
        FROM eventos
        WHERE fecha BETWEEN %s AND %s
        ORDER BY fecha, hora NULLS FIRST, titulo
    """, (desde, hasta))
    columnas = ["id", "titulo", "descripcion", "fecha", "hora", "color"]

    eventos_por_dia = {}
    for fila in cursor.fetchall():
        e = dict(zip(columnas, fila))
        e["hora_texto"] = e["hora"].strftime("%H:%M") if e["hora"] else None
        eventos_por_dia.setdefault(e["fecha"], []).append(e)

    cursor.close()
    conexion.close()
    return eventos_por_dia


def _obtener_cumpleanos_en_rango(desde, hasta):
    """Cumpleaños de los trabajadores activos que caen dentro del rango de
    fechas, comparando solo mes y dia (no el año) -- asi se calculan solos
    cada año, sin tener que crear un evento manual cada vez. Los
    trabajadores inactivos no se incluyen."""
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("""
        SELECT nombres, apellidos, fecha_nacimiento
        FROM trabajadores
        WHERE fecha_nacimiento IS NOT NULL
          AND estado IS DISTINCT FROM 'INACTIVO'
    """)

    cumples_por_mes_dia = {}
    for nombres, apellidos, fecha_nac in cursor.fetchall():
        clave = (fecha_nac.month, fecha_nac.day)
        cumples_por_mes_dia.setdefault(clave, []).append(f"{nombres} {apellidos}")

    cursor.close()
    conexion.close()

    cumples_por_dia = {}
    cursor_dia = desde
    while cursor_dia <= hasta:
        clave = (cursor_dia.month, cursor_dia.day)
        if clave in cumples_por_mes_dia:
            cumples_por_dia[cursor_dia] = cumples_por_mes_dia[clave]
        cursor_dia += timedelta(days=1)

    return cumples_por_dia


@calendario_bp.route("/calendario")
@login_requerido
def pagina_calendario():
    hoy = datetime.now(ZONA_HORARIA_LOCAL).date()

    vista = request.args.get("vista", "mes")
    if vista not in ("mes", "semana"):
        vista = "mes"

    anio = request.args.get("anio", type=int) or hoy.year
    mes = request.args.get("mes", type=int) or hoy.month
    if mes < 1 or mes > 12:
        anio, mes = hoy.year, hoy.month

    if vista == "semana":
        dia_param = request.args.get("dia", type=int)
        try:
            fecha_ref = date(anio, mes, dia_param) if dia_param else hoy
        except ValueError:
            fecha_ref = hoy

        inicio = fecha_ref - timedelta(days=fecha_ref.weekday())
        fin = inicio + timedelta(days=6)

        eventos_por_dia = _obtener_eventos_en_rango(inicio, fin)
        cumples_por_dia = _obtener_cumpleanos_en_rango(inicio, fin)

        dias_semana = []
        cursor_dia = inicio
        while cursor_dia <= fin:
            dias_semana.append({
                "fecha": cursor_dia,
                "dia_semana": DIAS_ES[cursor_dia.weekday()],
                "es_hoy": cursor_dia == hoy,
                "eventos": eventos_por_dia.get(cursor_dia, []),
                "cumpleanos": cumples_por_dia.get(cursor_dia, [])
            })
            cursor_dia += timedelta(days=1)

        if inicio.month == fin.month:
            titulo_periodo = f"{inicio.day} al {fin.day} de {MESES_ES[fin.month]} {fin.year}"
        else:
            titulo_periodo = (
                f"{inicio.day} {MESES_ABREV[inicio.month]} - "
                f"{fin.day} {MESES_ABREV[fin.month]} {fin.year}"
            )

        anterior = inicio - timedelta(days=7)
        siguiente = inicio + timedelta(days=7)

        nav_prev = {"vista": "semana", "anio": anterior.year, "mes": anterior.month, "dia": anterior.day}
        nav_next = {"vista": "semana", "anio": siguiente.year, "mes": siguiente.month, "dia": siguiente.day}
        nav_hoy = {"vista": "semana", "anio": hoy.year, "mes": hoy.month, "dia": hoy.day}
        nav_vista_mes = {"vista": "mes", "anio": fecha_ref.year, "mes": fecha_ref.month}
        nav_vista_semana = {"vista": "semana", "anio": anio, "mes": mes, "dia": dia_param or hoy.day}

        return render_template(
            "calendario.html",
            vista=vista,
            semanas=None,
            dias_semana=dias_semana,
            titulo_periodo=titulo_periodo,
            nav_prev=nav_prev, nav_next=nav_next, nav_hoy=nav_hoy,
            nav_vista_mes=nav_vista_mes, nav_vista_semana=nav_vista_semana,
            colores=COLORES_DISPONIBLES,
            active_page="calendario"
        )

    # --- vista mes ---
    primer_dia = date(anio, mes, 1)
    ultimo_dia = date(anio, mes, monthrange(anio, mes)[1])

    inicio_grilla = primer_dia - timedelta(days=primer_dia.weekday())
    fin_grilla = ultimo_dia + timedelta(days=(6 - ultimo_dia.weekday()))

    eventos_por_dia = _obtener_eventos_en_rango(inicio_grilla, fin_grilla)
    cumples_por_dia = _obtener_cumpleanos_en_rango(inicio_grilla, fin_grilla)

    semanas = []
    semana_actual = []
    cursor_dia = inicio_grilla
    while cursor_dia <= fin_grilla:
        semana_actual.append({
            "fecha": cursor_dia,
            "dia_numero": cursor_dia.day,
            "es_mes_actual": cursor_dia.month == mes,
            "es_hoy": cursor_dia == hoy,
            "eventos": eventos_por_dia.get(cursor_dia, []),
            "cumpleanos": cumples_por_dia.get(cursor_dia, [])
        })
        if len(semana_actual) == 7:
            semanas.append(semana_actual)
            semana_actual = []
        cursor_dia += timedelta(days=1)

    anio_prev, mes_prev = (anio, mes - 1) if mes > 1 else (anio - 1, 12)
    anio_next, mes_next = (anio, mes + 1) if mes < 12 else (anio + 1, 1)

    nav_prev = {"vista": "mes", "anio": anio_prev, "mes": mes_prev}
    nav_next = {"vista": "mes", "anio": anio_next, "mes": mes_next}
    nav_hoy = {"vista": "mes", "anio": hoy.year, "mes": hoy.month}

    # Al pasar a vista semanal desde el mes, centrar en "hoy" si el mes
    # mostrado incluye hoy, si no, en el primer dia del mes mostrado.
    dia_referencia = hoy.day if (anio == hoy.year and mes == hoy.month) else 1
    nav_vista_semana = {"vista": "semana", "anio": anio, "mes": mes, "dia": dia_referencia}
    nav_vista_mes = {"vista": "mes", "anio": anio, "mes": mes}

    return render_template(
        "calendario.html",
        vista=vista,
        semanas=semanas,
        dias_semana=None,
        titulo_periodo=f"{MESES_ES[mes]} {anio}",
        nav_prev=nav_prev, nav_next=nav_next, nav_hoy=nav_hoy,
        nav_vista_mes=nav_vista_mes, nav_vista_semana=nav_vista_semana,
        colores=COLORES_DISPONIBLES,
        active_page="calendario"
    )


# ---------------------------------------------------------------------------
# API: crear / editar / eliminar eventos
# ---------------------------------------------------------------------------

@calendario_bp.route("/api/eventos", methods=["POST"])
@login_requerido
def api_crear_evento():
    datos = request.get_json(silent=True) or {}
    titulo = (datos.get("titulo") or "").strip()
    fecha = (datos.get("fecha") or "").strip()

    if not titulo or not fecha:
        return jsonify({"error": "El título y la fecha son obligatorios"}), 400

    descripcion = (datos.get("descripcion") or "").strip()
    hora = (datos.get("hora") or "").strip() or None
    color = (datos.get("color") or "#133984").strip()

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("""
            INSERT INTO eventos (titulo, descripcion, fecha, hora, color, creado_por, creado_en)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (titulo, descripcion, fecha, hora, color, session.get("username"), datetime.now()))
        evento_id = cursor.fetchone()[0]
        conexion.commit()
        return jsonify({"ok": True, "id": evento_id}), 201
    except Exception as error:
        conexion.rollback()
        print("ERROR CREANDO EVENTO:", error)
        return jsonify({"error": "No se pudo crear el evento"}), 500
    finally:
        cursor.close()
        conexion.close()


@calendario_bp.route("/api/eventos/<int:evento_id>", methods=["PUT"])
@login_requerido
def api_actualizar_evento(evento_id):
    datos = request.get_json(silent=True) or {}
    titulo = (datos.get("titulo") or "").strip()
    fecha = (datos.get("fecha") or "").strip()

    if not titulo or not fecha:
        return jsonify({"error": "El título y la fecha son obligatorios"}), 400

    descripcion = (datos.get("descripcion") or "").strip()
    hora = (datos.get("hora") or "").strip() or None
    color = (datos.get("color") or "#133984").strip()

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("""
            UPDATE eventos SET titulo = %s, descripcion = %s, fecha = %s, hora = %s, color = %s
            WHERE id = %s
        """, (titulo, descripcion, fecha, hora, color, evento_id))

        if cursor.rowcount == 0:
            conexion.rollback()
            return jsonify({"error": "Evento no encontrado"}), 404

        conexion.commit()
        return jsonify({"ok": True})
    except Exception as error:
        conexion.rollback()
        print("ERROR ACTUALIZANDO EVENTO:", error)
        return jsonify({"error": "No se pudo actualizar el evento"}), 500
    finally:
        cursor.close()
        conexion.close()


@calendario_bp.route("/api/eventos/<int:evento_id>", methods=["DELETE"])
@login_requerido
def api_eliminar_evento(evento_id):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM eventos WHERE id = %s", (evento_id,))
    eliminado = cursor.rowcount > 0
    conexion.commit()
    cursor.close()
    conexion.close()

    if not eliminado:
        return jsonify({"error": "Evento no encontrado"}), 404
    return jsonify({"ok": True})
