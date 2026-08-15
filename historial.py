# historial.py
# Historial de asistencia de UN trabajador, mes por mes. Muestra los dias
# con marcaje real, y ademas los dias de "Falta" (para trabajadores de una
# sede con alerta de inasistencia activada) -- usa el MISMO rango de
# fechas y el MISMO criterio que resumen.py, para que la suma total de
# minutos de este mes coincida exactamente con la fila de ese trabajador
# en el Resumen mensual.

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Blueprint, render_template, request, abort

from auth import login_requerido
from db import obtener_conexion
from reglas_asistencia import horario_del_trabajador, evaluar_marcaje_entrada
from resumen import _construir_semanas, _formatear_duracion

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
        SELECT t.id, t.nombres, t.apellidos, t.dni, t.codigo_empleado, t.cargo, t.area,
               t.estado, t.hora_entrada, t.hora_salida, COALESCE(s.alerta_inasistencia, FALSE),
               t.excluido_asistencia
        FROM trabajadores t
        LEFT JOIN sedes s ON s.id = t.sede_id
        WHERE t.id = %s
    """, (trabajador_id,))
    fila_trabajador = cursor.fetchone()

    if not fila_trabajador:
        cursor.close()
        conexion.close()
        abort(404)

    columnas_t = [
        "id", "nombres", "apellidos", "dni", "codigo_empleado", "cargo",
        "area", "estado", "hora_entrada", "hora_salida", "alerta_inasistencia",
        "excluido_asistencia"
    ]
    trabajador = dict(zip(columnas_t, fila_trabajador))

    # Un trabajador inactivo no debe mostrar su asistencia en ninguna parte
    # del sistema. Cortamos aqui mismo, sin siquiera consultar sus marcajes.
    if trabajador["estado"] == "INACTIVO":
        cursor.close()
        conexion.close()

        anio_prev, mes_prev = (anio, mes - 1) if mes > 1 else (anio - 1, 12)
        anio_next, mes_next = (anio, mes + 1) if mes < 12 else (anio + 1, 1)

        return render_template(
            "historial.html",
            trabajador=trabajador,
            dias=[],
            inactivo=True,
            anio=anio, mes=mes, mes_nombre=MESES_ES[mes],
            anio_prev=anio_prev, mes_prev=mes_prev,
            anio_next=anio_next, mes_next=mes_next,
            active_page="resumen"
        )

    # Mismo rango de fechas que usa resumen.py para este mes (semanas
    # lunes-viernes, que pueden extenderse a los meses vecinos) -- asi la
    # suma de este historial coincide exacto con la fila del Resumen.
    semanas = _construir_semanas(anio, mes)
    primer_dia = semanas[0]["inicio"]
    ultimo_dia = semanas[-1]["fin"]

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

    hora_entrada_prog, hora_salida_prog = horario_del_trabajador(
        trabajador["hora_entrada"], trabajador["hora_salida"]
    )
    minutos_jornada = (
        (hora_salida_prog.hour * 60 + hora_salida_prog.minute)
        - (hora_entrada_prog.hour * 60 + hora_entrada_prog.minute)
    )
    if minutos_jornada <= 0:
        minutos_jornada = 480  # respaldo razonable (8h) si el horario quedo mal configurado

    # Solo se muestran los dias que realmente tienen algun marcaje (entrada
    # y/o salida). No se listan dias vacios, sea entre semana o fin de
    # semana -- si alguien llega a marcar un sabado, tambien aparece aqui.
    dias = []
    for fecha in sorted(marcas_por_dia.keys()):
        marca = marcas_por_dia[fecha]
        es_feriado = fecha in feriados_set
        motivo_ajuste = ajustes_map.get(fecha)

        if marca["entrada"] is not None and not trabajador["excluido_asistencia"]:
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

    # Dias de "Falta": mismo criterio EXACTO que usa resumen.py -- solo
    # para trabajadores de una sede con la alerta de inasistencia activada,
    # de lunes a viernes, sin marcaje, sin feriado, sin justificacion, y
    # que ya paso (si es hoy, respetando la tolerancia de 30 min). Nunca
    # aplica si el trabajador esta excluido de las reglas de asistencia.
    if trabajador["alerta_inasistencia"] and not trabajador["excluido_asistencia"]:
        ahora = datetime.now(ZONA_HORARIA_LOCAL)

        for semana in semanas:
            for i in range(5):
                dia_fecha = semana["inicio"] + timedelta(days=i)

                if dia_fecha > hoy:
                    continue  # dia futuro, todavia no aplica
                if dia_fecha in marcas_por_dia:
                    continue  # ya tiene marcaje ese dia
                if dia_fecha in feriados_set:
                    continue
                if dia_fecha in ajustes_map:
                    continue
                if dia_fecha == hoy:
                    limite = datetime.combine(hoy, hora_entrada_prog, tzinfo=ZONA_HORARIA_LOCAL) + timedelta(minutes=30)
                    if ahora < limite:
                        continue  # hoy, pero todavia no vence la tolerancia

                dias.append({
                    "fecha": dia_fecha,
                    "dia_semana": DIAS_ES[dia_fecha.weekday()],
                    "es_feriado": False,
                    "entrada": None,
                    "salida": None,
                    "evaluacion": {
                        "estado": "falta",
                        "etiqueta": "Falta",
                        "descuento_min": minutos_jornada,
                        "minutos_tarde": minutos_jornada,
                        "detalle": "No marcó asistencia"
                    }
                })

    dias.sort(key=lambda d: d["fecha"])

    total_minutos_mes = sum(
        d["evaluacion"]["minutos_tarde"] for d in dias if d["evaluacion"]
    )
    total_texto = _formatear_duracion(total_minutos_mes)

    anio_prev, mes_prev = (anio, mes - 1) if mes > 1 else (anio - 1, 12)
    anio_next, mes_next = (anio, mes + 1) if mes < 12 else (anio + 1, 1)

    return render_template(
        "historial.html",
        trabajador=trabajador,
        dias=dias,
        inactivo=False,
        total_texto=total_texto,
        anio=anio, mes=mes, mes_nombre=MESES_ES[mes],
        anio_prev=anio_prev, mes_prev=mes_prev,
        anio_next=anio_next, mes_next=mes_next,
        active_page="resumen"
    )
