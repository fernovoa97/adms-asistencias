# montos.py
# Calculos de importes de una orden de compra y el texto "Son:" con el
# total en letras. No depende de la base de datos para poder probarse solo.
#
# Reglas (las mismas del Excel de ordenes de compra):
#   total de linea = cantidad x valor unitario (sin IGV)
#   valor venta    = suma de las lineas
#   IGV            = 18% del valor venta
#   total          = valor venta + IGV   <- es el que va en letras

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

TASA_IGV = Decimal("0.18")
CENTIMO = Decimal("0.01")

MONEDAS = {
    "PEN": {"simbolo": "S/", "nombre": "SOLES", "etiqueta_total": "TOTAL S/"},
    "USD": {"simbolo": "US$", "nombre": "DÓLARES AMERICANOS", "etiqueta_total": "TOTAL US$"},
}

_UNIDADES = (
    "", "UNO", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE",
    "DIEZ", "ONCE", "DOCE", "TRECE", "CATORCE", "QUINCE", "DIECISÉIS", "DIECISIETE",
    "DIECIOCHO", "DIECINUEVE", "VEINTE", "VEINTIUNO", "VEINTIDÓS", "VEINTITRÉS",
    "VEINTICUATRO", "VEINTICINCO", "VEINTISÉIS", "VEINTISIETE", "VEINTIOCHO", "VEINTINUEVE",
)
_DECENAS = ("", "", "", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA", "OCHENTA", "NOVENTA")
_CENTENAS = (
    "", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS",
    "SEISCIENTOS", "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS",
)


def redondear(valor):
    return Decimal(valor).quantize(CENTIMO, rounding=ROUND_HALF_UP)


def a_decimal(valor):
    """Convierte lo que llega del formulario en Decimal. Acepta coma o punto
    decimal; lanza ValueError si no es un numero."""
    if isinstance(valor, Decimal):
        return valor
    texto = str(valor if valor is not None else "").strip().replace(",", ".")
    if not texto:
        raise ValueError("Número vacío")
    try:
        numero = Decimal(texto)
    except InvalidOperation:
        raise ValueError(f"Número no válido: {valor}")
    if not numero.is_finite():
        raise ValueError(f"Número no válido: {valor}")
    return numero


def calcular_totales(items):
    """items: lista de dicts con 'cantidad' y 'valor_unitario' (Decimal).
    Devuelve los totales por linea y los de la orden, ya redondeados."""
    lineas = [redondear(it["cantidad"] * it["valor_unitario"]) for it in items]
    valor_venta = sum(lineas, Decimal("0.00"))
    igv = redondear(valor_venta * TASA_IGV)
    return {
        "lineas": lineas,
        "valor_venta": valor_venta,
        "igv": igv,
        "total": valor_venta + igv,
    }


def _menor_a_mil(n, apocope):
    """0 < n < 1000. 'apocope' convierte UNO en UN (delante de MIL/MILLONES
    o de la moneda): VEINTIÚN MIL, CIENTO UN MIL."""
    if n == 100:
        return "CIEN"
    partes = []
    centena, resto = divmod(n, 100)
    if centena:
        partes.append(_CENTENAS[centena])
    if resto:
        if resto < 30:
            palabra = _UNIDADES[resto]
            if apocope and resto == 1:
                palabra = "UN"
            elif apocope and resto == 21:
                palabra = "VEINTIÚN"
            partes.append(palabra)
        else:
            decena, unidad = divmod(resto, 10)
            palabra = _DECENAS[decena]
            if unidad:
                palabra += " Y " + ("UN" if apocope and unidad == 1 else _UNIDADES[unidad])
            partes.append(palabra)
    return " ".join(partes)


def entero_en_letras(n, apocope=False):
    if n == 0:
        return "CERO"
    if n < 0:
        raise ValueError("Monto negativo")

    millones, resto = divmod(n, 1_000_000)
    miles, unidades = divmod(resto, 1000)
    partes = []
    if millones:
        if millones == 1:
            partes.append("UN MILLÓN")
        else:
            partes.append(entero_en_letras(millones, apocope=True) + " MILLONES")
    if miles:
        partes.append("MIL" if miles == 1 else _menor_a_mil(miles, apocope=True) + " MIL")
    if unidades:
        partes.append(_menor_a_mil(unidades, apocope))
    return " ".join(partes)


def monto_en_letras(monto, moneda):
    """876.15 USD -> 'OCHOCIENTOS SETENTA Y SEIS Y 15/100 DÓLARES AMERICANOS'"""
    monto = redondear(monto)
    entero = int(monto)
    centimos = int((monto - entero) * 100)
    nombre_moneda = MONEDAS[moneda]["nombre"]
    return f"{entero_en_letras(entero)} Y {centimos:02d}/100 {nombre_moneda}"


def formatear_correlativo(anio, numero):
    return f"ADM-{anio}-C{numero}"
