# historial.py
# Historial de asistencia de UN trabajador, mes por mes. Solo muestra los
# dias que tienen algun marcaje real (entrada y/o salida) -- no se listan
# dias vacios, para evitar desorden en la tabla.

from calendar import monthrange
from datetime import date, datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, render_template, request, abort

from auth import login_requerido
from db import obtener_conexion
from reglas_asistencia import horario_del_trabajador, evaluar_marcaje_entrada

historial_bp = Blueprint("historial", __name__)

ZONA_HORARIA_LOCAL = ZoneInfo("America/Lima")

DIAS_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MESES_ES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]


@historial_bp.route("/trabajador/<int:trabajador_id>/historial")
@login_requerido
def pagina_historial(trabajador_id):
    hoy = datetime.now(ZONA_HORARIA_LOCAL).date()

    anio = request.args.get("anio", type=int) or hoy.year
    mes = request.args.get("mes", type=int) or hoy.month
    if mes < 1 or mes > 12:
        anio, mes = hoy.year, hoy.month

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT id, nombres, apellidos, dni, codigo_empleado, cargo, area,
               hora_entrada, hora_salida
        FROM trabajadores
        WHERE id = %s
    """, (trabajador_id,))
    fila_trabajador = cursor.fetchone()

    if not fila_trabajador:
        cursor.close()
        conexion.close()
        abort(404)

    columnas_t = [
        "id", "nombres", "apellidos", "dni", "codigo_empleado", "cargo",
        "area", "hora_entrada", "hora_salida"
    ]
    trabajador = dict(zip(columnas_t, fila_trabajador))

    primer_dia = date(anio, mes, 1)
    ultimo_dia = date(anio, mes, monthrange(anio, mes)[1])

    # Un trabajador puede tener marcajes bajo su codigo_empleado o (en casos
    # viejos, antes de vincularse) bajo un codigo que coincide con su DNI.
    cursor.execute("""
        SELECT fecha, hora, tipo_marcaje
        FROM asistencias
        WHERE (codigo_empleado = %s OR codigo_empleado = %s)
          AND fecha BETWEEN %s AND %s
    """, (trabajador["codigo_empleado"], trabajador["dni"], primer_dia, ultimo_dia))

    marcas_por_dia = {}
    for fecha, hora, tipo_marcaje in cursor.fetchall():
        registro = marcas_por_dia.setdefault(fecha, {"entrada": None, "salida": None})
        if tipo_marcaje == "0":
            if registro["entrada"] is None or hora < registro["entrada"]:
                registro["entrada"] = hora
        elif tipo_marcaje == "1":
            if registro["salida"] is None or hora > registro["salida"]:
                registro["salida"] = hora

    cursor.execute(
        "SELECT fecha FROM feriados WHERE fecha BETWEEN %s AND %s",
        (primer_dia, ultimo_dia)
    )
    feriados_set = {f[0] for f in cursor.fetchall()}

    cursor.execute("""
        SELECT fecha, motivo FROM ajustes_asistencia
        WHERE trabajador_id = %s AND fecha BETWEEN %s AND %s
    """, (trabajador_id, primer_dia, ultimo_dia))
    ajustes_map = {f[0]: f[1] for f in cursor.fetchall()}

    cursor.close()
    conexion.close()

    hora_entrada_prog, _ = horario_del_trabajador(
        trabajador["hora_entrada"], trabajador["hora_salida"]
    )

    # Solo se muestran los dias que realmente tienen algun marcaje (entrada
    # y/o salida). No se listan dias vacios, sea entre semana o fin de
    # semana -- si alguien llega a marcar un sabado, tambien aparece aqui.
    dias = []
    for fecha in sorted(marcas_por_dia.keys()):
        marca = marcas_por_dia[fecha]
        es_feriado = fecha in feriados_set
        motivo_ajuste = ajustes_map.get(fecha)

        if marca["entrada"] is not None:
            evaluacion = evaluar_marcaje_entrada(
                marca["entrada"], hora_entrada_prog, es_feriado, motivo_ajuste
            )
        else:
            evaluacion = None

        dias.append({
            "fecha": fecha,
            "dia_semana": DIAS_ES[fecha.weekday()],
            "es_feriado": es_feriado,
            "entrada": marca["entrada"],
            "salida": marca["salida"],
            "evaluacion": evaluacion
        })

    anio_prev, mes_prev = (anio, mes - 1) if mes > 1 else (anio - 1, 12)
    anio_next, mes_next = (anio, mes + 1) if mes < 12 else (anio + 1, 1)

    return render_template(
        "historial.html",
        trabajador=trabajador,
        dias=dias,
        anio=anio, mes=mes, mes_nombre=MESES_ES[mes],
        anio_prev=anio_prev, mes_prev=mes_prev,
        anio_next=anio_next, mes_next=mes_next
    )