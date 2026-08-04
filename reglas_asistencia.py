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

from datetime import time

HORA_ENTRADA_ESTANDAR = time(8, 0)
HORA_SALIDA_ESTANDAR = time(17, 0)
TOLERANCIA_MINUTOS = 30


def horario_del_trabajador(hora_entrada_personalizada, hora_salida_personalizada):
    """Devuelve (hora_entrada, hora_salida) a usar para un trabajador: su
    horario personalizado si lo tiene, o el estandar de la empresa."""
    entrada = hora_entrada_personalizada or HORA_ENTRADA_ESTANDAR
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
    en ese orden de prioridad, y devuelve un dict listo para mostrar."""
    if es_feriado:
        return {"estado": "feriado", "etiqueta": "Feriado", "descuento_min": 0, "detalle": None}

    if motivo_ajuste:
        return {
            "estado": "justificado",
            "etiqueta": "Justificado",
            "descuento_min": 0,
            "detalle": motivo_ajuste
        }

    resultado = calcular_estado_entrada(hora_entrada_programada, hora_marcada)

    if resultado["estado"] == "puntual":
        return {"estado": "puntual", "etiqueta": "Puntual", "descuento_min": 0, "detalle": None}

    if resultado["descuento_min"] > 0:
        etiqueta = f"Tardanza (-{resultado['descuento_min']} min)"
    else:
        etiqueta = "Tardanza"

    return {
        "estado": "tardanza",
        "etiqueta": etiqueta,
        "descuento_min": resultado["descuento_min"],
        "detalle": None
    }