# resumen.py
# Vista de resumen mensual: una fila por trabajador, una columna por cada
# semana (lunes a domingo) del mes, con los minutos de tardanza acumulados
# en esa semana.

from datetime import date, datetime, timedelta
from calendar import monthrange
from zoneinfo import ZoneInfo

from flask import Blueprint, request, render_template

from auth import login_requerido
from db import obtener_conexion
from reglas_asistencia import horario_del_trabajador, evaluar_marcaje_entrada

resumen_bp = Blueprint("resumen", __name__)

ZONA_HORARIA_LOCAL = ZoneInfo("America/Lima")

MESES_ES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]

MESES_ABREV = [
    "", "ene", "feb", "mar", "abr", "may", "jun",
    "jul", "ago", "sep", "oct", "nov", "dic"
]

UMBRAL_DESCUENTO_ALTO_MIN = 60  # 1 hora


def _etiqueta_semana(numero, inicio, fin):
    if inicio.month == fin.month:
        return f"Semana {numero} (del {inicio.day} al {fin.day})"
    # La semana cruza el fin de mes (ej. lunes 31 ago a viernes 4 sep):
    # se aclara el mes de cada extremo para que no se lea como un error.
    return (
        f"Semana {numero} (del {inicio.day} {MESES_ABREV[inicio.month]} "
        f"al {fin.day} {MESES_ABREV[fin.month]})"
    )


def _construir_semanas(anio, mes):
    """Semanas de lunes a viernes (nunca sabado/domingo), siempre de 5 dias
    completos. Cada semana pertenece al mes en el que cae su LUNES, sin
    importar si el viernes de esa semana ya cae en el mes siguiente. Esto
    mantiene el criterio de '1 hora acumulada = amonestacion' parejo todas
    las semanas, y de paso hace que cada mes tenga entre 4 y 5 semanas
    (nunca fragmentos sueltos de 1-2 dias)."""
    primer_dia = date(anio, mes, 1)
    ultimo_dia = date(anio, mes, monthrange(anio, mes)[1])

    dias_hasta_lunes = (7 - primer_dia.weekday()) % 7
    lunes = primer_dia + timedelta(days=dias_hasta_lunes)

    semanas = []
    numero = 1

    while lunes <= ultimo_dia:
        viernes = lunes + timedelta(days=4)
        semanas.append({
            "numero": numero,
            "inicio": lunes,
            "fin": viernes,
            "etiqueta": _etiqueta_semana(numero, lunes, viernes)
        })
        lunes += timedelta(days=7)
        numero += 1

    return semanas


def _semana_de(fecha, semanas):
    for semana in semanas:
        if semana["inicio"] <= fecha <= semana["fin"]:
            return semana["numero"]
    return None


def _formatear_duracion(minutos):
    horas = minutos // 60
    resto = minutos % 60
    return f"{horas}:{resto:02d}:00"


@resumen_bp.route("/resumen")
@login_requerido
def pagina_resumen():
    hoy = datetime.now(ZONA_HORARIA_LOCAL).date()

    anio = request.args.get("anio", type=int) or hoy.year
    mes = request.args.get("mes", type=int) or hoy.month

    if mes < 1 or mes > 12:
        anio, mes = hoy.year, hoy.month

    semanas = _construir_semanas(anio, mes)
    primer_dia = semanas[0]["inicio"]
    ultimo_dia = semanas[-1]["fin"]

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    # Solo tiene sentido mostrar trabajadores que tengan codigo de empleado
    # (sin eso, nunca van a tener marcajes que evaluar).
    cursor.execute("""
        SELECT id, nombres, apellidos, hora_entrada, hora_salida
        FROM trabajadores
        WHERE codigo_empleado IS NOT NULL
        ORDER BY nombres, apellidos
    """)
    columnas_t = ["id", "nombres", "apellidos", "hora_entrada", "hora_salida"]
    trabajadores = [dict(zip(columnas_t, f)) for f in cursor.fetchall()]

    # Entradas del mes, unidas a su trabajador por codigo de empleado o DNI
    # (mismo criterio que usa el panel de asistencias).
    cursor.execute("""
        SELECT t.id, a.fecha, a.hora
        FROM asistencias a
        JOIN trabajadores t
            ON t.codigo_empleado = a.codigo_empleado
            OR t.dni = a.codigo_empleado
        WHERE a.tipo_marcaje = '0'
          AND a.fecha BETWEEN %s AND %s
    """, (primer_dia, ultimo_dia))

    entradas_por_trabajador = {}
    for trabajador_id, fecha, hora in cursor.fetchall():
        dias = entradas_por_trabajador.setdefault(trabajador_id, {})
        if fecha not in dias or hora < dias[fecha]:
            dias[fecha] = hora

    cursor.execute(
        "SELECT fecha FROM feriados WHERE fecha BETWEEN %s AND %s",
        (primer_dia, ultimo_dia)
    )
    feriados_set = {f[0] for f in cursor.fetchall()}

    cursor.execute("""
        SELECT trabajador_id, fecha, motivo FROM ajustes_asistencia
        WHERE fecha BETWEEN %s AND %s
    """, (primer_dia, ultimo_dia))
    ajustes_map = {(f[0], f[1]): f[2] for f in cursor.fetchall()}

    cursor.close()
    conexion.close()

    filas = []
    for t in trabajadores:
        totales_min = {s["numero"]: 0 for s in semanas}
        dias_marcados = entradas_por_trabajador.get(t["id"], {})

        for fecha, hora_entrada_real in dias_marcados.items():
            numero_semana = _semana_de(fecha, semanas)
            if numero_semana is None:
                continue

            es_feriado = fecha in feriados_set
            motivo_ajuste = ajustes_map.get((t["id"], fecha))
            hora_prog, _ = horario_del_trabajador(t["hora_entrada"], t["hora_salida"])
            evaluacion = evaluar_marcaje_entrada(
                hora_entrada_real, hora_prog, es_feriado, motivo_ajuste
            )

            totales_min[numero_semana] += evaluacion["descuento_min"]

        totales = {}
        for numero, minutos in totales_min.items():
            totales[numero] = {
                "minutos": minutos,
                "texto": _formatear_duracion(minutos),
                "alto": minutos >= UMBRAL_DESCUENTO_ALTO_MIN
            }

        filas.append({
            "nombre": f"{t['nombres']} {t['apellidos']}",
            "totales": totales
        })

    anio_prev, mes_prev = (anio, mes - 1) if mes > 1 else (anio - 1, 12)
    anio_next, mes_next = (anio, mes + 1) if mes < 12 else (anio + 1, 1)

    return render_template(
        "resumen.html",
        semanas=semanas,
        filas=filas,
        anio=anio,
        mes=mes,
        mes_nombre=MESES_ES[mes],
        anio_prev=anio_prev, mes_prev=mes_prev,
        anio_next=anio_next, mes_next=mes_next
    )