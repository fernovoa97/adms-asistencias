import unittest
from decimal import Decimal

from montos import a_decimal, calcular_totales, entero_en_letras, formatear_correlativo, monto_en_letras

D = Decimal


class TotalesTest(unittest.TestCase):
    def test_orden_c62_del_excel(self):
        items = [
            {"cantidad": D(3), "valor_unitario": D("72.5")},
            {"cantidad": D(2), "valor_unitario": D("87.5")},
            {"cantidad": D(2), "valor_unitario": D("87.5")},
            {"cantidad": D(2), "valor_unitario": D("87.5")},
        ]
        t = calcular_totales(items)
        self.assertEqual(t["lineas"], [D("217.50"), D("175.00"), D("175.00"), D("175.00")])
        self.assertEqual(t["valor_venta"], D("742.50"))
        self.assertEqual(t["igv"], D("133.65"))
        self.assertEqual(t["total"], D("876.15"))

    def test_orden_c64_del_excel(self):
        t = calcular_totales([{"cantidad": D(12), "valor_unitario": D(87)}])
        self.assertEqual(t["total"], D("1231.92"))

    def test_igv_redondea_al_centimo(self):
        t = calcular_totales([{"cantidad": D(1), "valor_unitario": D("0.25")}])
        self.assertEqual(t["igv"], D("0.05"))  # 0.045 -> 0.05

    def test_a_decimal_acepta_coma(self):
        self.assertEqual(a_decimal("10,5"), D("10.5"))
        with self.assertRaises(ValueError):
            a_decimal("abc")
        with self.assertRaises(ValueError):
            a_decimal("")


class LetrasTest(unittest.TestCase):
    def test_ejemplos_del_excel(self):
        self.assertEqual(monto_en_letras(D("876.15"), "USD"),
                         "OCHOCIENTOS SETENTA Y SEIS Y 15/100 DÓLARES AMERICANOS")
        self.assertEqual(monto_en_letras(D("99.12"), "USD"),
                         "NOVENTA Y NUEVE Y 12/100 DÓLARES AMERICANOS")
        self.assertEqual(monto_en_letras(D("1231.92"), "PEN"),
                         "MIL DOSCIENTOS TREINTA Y UNO Y 92/100 SOLES")
        self.assertEqual(monto_en_letras(D("572.30"), "PEN"),
                         "QUINIENTOS SETENTA Y DOS Y 30/100 SOLES")

    def test_casos_especiales(self):
        self.assertEqual(entero_en_letras(0), "CERO")
        self.assertEqual(entero_en_letras(100), "CIEN")
        self.assertEqual(entero_en_letras(101), "CIENTO UNO")
        self.assertEqual(entero_en_letras(21000), "VEINTIÚN MIL")
        self.assertEqual(entero_en_letras(31500), "TREINTA Y UN MIL QUINIENTOS")
        self.assertEqual(entero_en_letras(100000), "CIEN MIL")
        self.assertEqual(entero_en_letras(1000000), "UN MILLÓN")
        self.assertEqual(entero_en_letras(2_501_016), "DOS MILLONES QUINIENTOS UN MIL DIECISÉIS")

    def test_centimos_con_dos_digitos(self):
        self.assertEqual(monto_en_letras(D("1200"), "PEN"), "MIL DOSCIENTOS Y 00/100 SOLES")
        self.assertEqual(monto_en_letras(D("0.05"), "PEN"), "CERO Y 05/100 SOLES")


class CorrelativoTest(unittest.TestCase):
    def test_formato(self):
        self.assertEqual(formatear_correlativo(2026, 69), "ADM-2026-C69")
        self.assertEqual(formatear_correlativo(2027, 1), "ADM-2027-C1")


if __name__ == "__main__":
    unittest.main()
