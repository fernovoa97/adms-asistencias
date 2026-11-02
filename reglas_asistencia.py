# reglas_asistencia.py
# Logica pura (sin base de datos) para calcular si una entrada fue puntual,
# tardanza, o tardanza con descuento, segun el horario del trabajador.
#
# Reglas del negocio:
# - Hasta la hora de entrada programada: Puntual.
# - De 1 a 30 minutos tarde: Tardanza, sin descuento.
# - Mas de 30 minutos tarde: Tardanza, con descuento = TODOS los minutos
#   tarde (no solo el excedente de 30). Ej: entrada programada 8:00,
#   marca 8:31 -> 31 minutos de descuento.

from datetime import date, time, timedelta

HORA_ENTRADA_ESTANDAR = time(8, 0)
HORA_SALIDA_ESTANDAR = time(17, 0)
TOLERANCIA_MINUTOS = 30
DIA_CORTE = 23  # cada periodo va del 24 del mes anterior al 23 del mes


def horario_del_trabajador(hora_entrada_personalizada, hora_salida_personalizada,
                           hora_entrada_estandar=HORA_ENTRADA_ESTANDAR):
    """Devuelve (hora_entrada, hora_salida) a usar para un trabajador: su
    horario personalizado si lo tiene, o el estandar de la empresa (el que
    esta configurado en Ajustes, cuando quien llama lo pasa)."""
    entrada = hora_entrada_personalizada or hora_entrada_estandar
    salida = hora_salida_personalizada or HORA_SALIDA_ESTANDAR
    return entrada, salida


def calcular_estado_entrada(hora_programada, hora_marcada):
    """Compara la hora marcada contra la hora programada y devuelve un
    diccionario con el estado y los minutos de descuento (0 si no aplica)."""
    minutos_programada = hora_programada.hour * 60 + hora_programada.minute
    minutos_marcada = hora_marcada.hour * 60 + hora_marcada.minute
    diferencia = minutos_marcada - minutos_programada

    if diferencia <= 0:
        return {"estado": "puntual", "minutos_tarde": 0, "descuento_min": 0}
    elif diferencia <= TOLERANCIA_MINUTOS:
        return {"estado": "tardanza", "minutos_tarde": diferencia, "descuento_min": 0}
    else:
        return {"estado": "tardanza", "minutos_tarde": diferencia, "descuento_min": diferencia}


ETIQUETAS_ESTADO = {
    "puntual": "Puntual",
    "tardanza": "Tardanza",
    "justificado": "Justificado",
    "feriado": "Feriado"
}


def evaluar_marcaje_entrada(hora_marcada, hora_entrada_programada, es_feriado, motivo_ajuste):
    """Punto de entrada principal: aplica feriado > ajuste > calculo normal,
    en ese orden de prioridad, y devuelve un dict listo para mostrar.

    Incluye dos totales distintos, para dos usos distintos:
    - descuento_min: solo cuenta si supera los 30 min de tolerancia (se usa
      para el descuento de pago que se muestra en el panel diario).
    - minutos_tarde: TODOS los minutos tarde, desde el minuto 1 (se usa para
      la tardanza acumulada semanal del Resumen, ya que incluso las
      tardanzas chicas dentro de la tolerancia cuentan para la
      amonestacion de 1 hora acumulada)."""
    if es_feriado:
        return {
            "estado": "feriado", "etiqueta": "Feriado",
            "descuento_min": 0, "minutos_tarde": 0, "detalle": None
        }

    if motivo_ajuste:
        return {
            "estado": "justificado", "etiqueta": "Justificado",
            "descuento_min": 0, "minutos_tarde": 0, "detalle": motivo_ajuste
        }

    resultado = calcular_estado_entrada(hora_entrada_programada, hora_marcada)

    if resultado["estado"] == "puntual":
        return {
            "estado": "puntual", "etiqueta": "Puntual",
            "descuento_min": 0, "minutos_tarde": 0, "detalle": None
        }

    if resultado["descuento_min"] > 0:
        etiqueta = f"Tardanza (-{resultado['descuento_min']} min)"
    else:
        etiqueta = "Tardanza"

    return {
        "estado": "tardanza",
        "etiqueta": etiqueta,
        "descuento_min": resultado["descuento_min"],
        "minutos_tarde": resultado["minutos_tarde"],
        "detalle": None
    }


# ---------------------------------------------------------------------------
# Panel de asistencia: tardanza exacta en segundos y periodos con corte
# ---------------------------------------------------------------------------

def _segundos_del_dia(hora):
    return hora.hour * 3600 + hora.minute * 60 + hora.second


def segundos_tardanza(hora_programada, hora_marcada):
    """Tardanza exacta: hora marcada menos hora programada, nunca negativa."""
    return max(0, _segundos_del_dia(hora_marcada) - _segundos_del_dia(hora_programada))


def formatear_hms(segundos):
    horas, resto = divmod(int(segundos), 3600)
    minutos, segs = divmod(resto, 60)
    return f"{horas:02d}:{minutos:02d}:{segs:02d}"


def periodo_de_fecha(fecha):
    """(anio, mes) del periodo al que pertenece una fecha: hasta el dia de
    corte es el periodo de ese mes; despues, el del mes siguiente."""
    if fecha.day <= DIA_CORTE:
        return fecha.year, fecha.month
    return (fecha.year, fecha.month + 1) if fecha.month < 12 else (fecha.year + 1, 1)


def periodo_vecino(anio, mes, salto):
    """Periodo anterior (salto=-1) o siguiente (salto=1)."""
    total = anio * 12 + (mes - 1) + salto
    return total // 12, total % 12 + 1


def rango_periodo(anio, mes):
    """(inicio, fin) del periodo: ej. noviembre = 24 oct - 23 nov."""
    anio_prev, mes_prev = periodo_vecino(anio, mes, -1)
    return date(anio_prev, mes_prev, DIA_CORTE + 1), date(anio, mes, DIA_CORTE)


def semanas_del_periodo(anio, mes):
    """Semanas de lunes a viernes del periodo. Solo incluye los dias que caen
    dentro del periodo: una semana que cruza el corte queda partida y cada
    parte suma en su propio periodo."""
    inicio, fin = rango_periodo(anio, mes)
    semanas = []
    lunes_actual = None
    dia = inicio

    while dia <= fin:
        if dia.weekday() < 5:
            lunes = dia - timedelta(days=dia.weekday())
            if lunes != lunes_actual:
                semanas.append([])
                lunes_actual = lunes
            semanas[-1].append(dia)
        dia += timedelta(days=1)

    return semanas
