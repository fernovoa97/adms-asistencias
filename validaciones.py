# validaciones.py
# Helpers de validacion compartidos por los modulos de la ficha del
# colaborador (contrato, renovaciones y seguros).

from datetime import date, datetime
from zoneinfo import ZoneInfo

ZONA_HORARIA_LOCAL = ZoneInfo("America/Lima")


def hoy_local():
    """Fecha de hoy en Peru: el servidor corre en UTC, asi que despues de
    las 19:00 date.today() ya devolveria el dia siguiente."""
    return datetime.now(ZONA_HORARIA_LOCAL).date()


def parsear_fecha(valor):
    """Convierte 'AAAA-MM-DD' en date. Devuelve None si viene vacio y lanza
    ValueError si el texto no es una fecha valida."""
    valor = (valor or "").strip() if isinstance(valor, str) else valor
    if not valor:
        return None
    if not isinstance(valor, str):
        raise ValueError("Fecha no válida")
    return datetime.strptime(valor, "%Y-%m-%d").date()


def calcular_edad(fecha_nacimiento, hoy=None):
    """Edad en anios cumplidos a la fecha indicada. Se calcula siempre al
    leer: guardarla en la BD la dejaria desactualizada al anio siguiente."""
    if not fecha_nacimiento:
        return None
    hoy = hoy or hoy_local()
    aun_no_cumple = (hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day)
    return hoy.year - fecha_nacimiento.year - (1 if aun_no_cumple else 0)
