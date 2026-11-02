import unittest
from datetime import date, time

from reglas_asistencia import (
    formatear_hms,
    horario_del_trabajador,
    periodo_de_fecha,
    periodo_vecino,
    rango_periodo,
    segundos_tardanza,
    semanas_del_periodo,
)

ENTRADA = time(8, 0, 0)


class TardanzaTest(unittest.TestCase):
    def test_suma_semanal_del_ejemplo(self):
        marcas = [time(8, 8, 18), time(8, 5, 56), time(8, 2, 28)]
        total = sum(segundos_tardanza(ENTRADA, m) for m in marcas)
        self.assertEqual(formatear_hms(total), "00:16:42")

    def test_a_la_hora_o_antes_no_hay_tardanza(self):
        self.assertEqual(segundos_tardanza(ENTRADA, time(8, 0, 0)), 0)
        self.assertEqual(segundos_tardanza(ENTRADA, time(7, 45, 10)), 0)

    def test_cuenta_segundos(self):
        self.assertEqual(segundos_tardanza(ENTRADA, time(8, 0, 1)), 1)

    def test_formato_supera_24_horas(self):
        self.assertEqual(formatear_hms(90 * 3600 + 5), "90:00:05")

    def test_horario_usa_el_estandar_configurado_y_respeta_el_propio(self):
        self.assertEqual(horario_del_trabajador(None, None, time(9, 0))[0], time(9, 0))
        self.assertEqual(horario_del_trabajador(time(7, 0), None, time(9, 0))[0], time(7, 0))


class PeriodoTest(unittest.TestCase):
    def test_rango_del_ejemplo(self):
        self.assertEqual(rango_periodo(2026, 11), (date(2026, 10, 24), date(2026, 11, 23)))

    def test_rango_de_enero_cruza_el_anio(self):
        self.assertEqual(rango_periodo(2027, 1), (date(2026, 12, 24), date(2027, 1, 23)))

    def test_periodo_de_fecha(self):
        self.assertEqual(periodo_de_fecha(date(2026, 11, 23)), (2026, 11))
        self.assertEqual(periodo_de_fecha(date(2026, 11, 24)), (2026, 12))
        self.assertEqual(periodo_de_fecha(date(2026, 12, 24)), (2027, 1))

    def test_periodo_vecino(self):
        self.assertEqual(periodo_vecino(2027, 1, -1), (2026, 12))
        self.assertEqual(periodo_vecino(2026, 12, 1), (2027, 1))

    def test_semanas_son_de_lunes_a_viernes_y_no_salen_del_periodo(self):
        semanas = semanas_del_periodo(2026, 11)
        self.assertEqual(semanas[0][0], date(2026, 10, 26))
        self.assertEqual(semanas[0][-1], date(2026, 10, 30))
        self.assertEqual(semanas[-1], [date(2026, 11, 23)])

    def test_semana_que_cruza_el_corte_se_reparte_sin_perder_dias(self):
        # 23 nov 2026 es lunes: ese dia va a noviembre; mar-vie, a diciembre.
        self.assertEqual(semanas_del_periodo(2026, 12)[0], [date(2026, 11, d) for d in (24, 25, 26, 27)])

        dias = [d for mes in range(1, 13) for semana in semanas_del_periodo(2026, mes) for d in semana]
        self.assertEqual(len(dias), len(set(dias)))


if __name__ == "__main__":
    unittest.main()
