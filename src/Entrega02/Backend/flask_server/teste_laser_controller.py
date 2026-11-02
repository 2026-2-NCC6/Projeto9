"""
Testes do movimento automático do laser (sem Arduino, sem relógio real).
Rode dentro de flask_server/:  python -m unittest teste_laser_controller -v
"""
import unittest

from laser_controller import LaserController, LaserDriver, Nivel, MAX_JOGO_S


class Relogio:
    """Relógio falso: o teste avança o tempo à mão."""
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class ArduinoSimulado:
    """Reproduz o sketch hoje.ino: A/D/W/S = ±5° com constrain(0,180), R = 90°, G<x>,<y> = absoluto."""
    def __init__(self):
        self.a1 = 90
        self.a2 = 90
        self.escritas = []

    def escrever(self, dados):
        texto = dados.decode()
        self.escritas.append(texto)
        if texto.startswith("G"):
            x, y = texto[1:].strip().split(",")
            self.a1, self.a2 = max(0, min(180, int(x))), max(0, min(180, int(y)))
            return
        for c in texto:
            if c == "A": self.a1 = min(180, self.a1 + 5)
            elif c == "D": self.a1 = max(0, self.a1 - 5)
            elif c == "W": self.a2 = min(180, self.a2 + 5)
            elif c == "S": self.a2 = max(0, self.a2 - 5)
            elif c == "R": self.a1 = self.a2 = 90
            else: raise AssertionError(f"comando inesperado enviado ao Arduino: {c!r}")


class TestControlador(unittest.TestCase):

    def setUp(self):
        self.relogio = Relogio()
        self.c = LaserController(seed=42, relogio=self.relogio)

    def test_facil_sempre_no_centro(self):
        self.c.start_game("facil")
        for t in (0, 1, 5, 30, 60):
            self.assertEqual(self.c.get_servo_angles(t), (90, 90))

    def test_medio_comeca_no_centro_e_abre_o_circulo(self):
        self.c.start_game("medio")
        self.assertEqual(self.c.get_servo_angles(0), (90, 90))
        self.assertEqual(self.c.get_servo_angles(2.5), (90, 115))   # quarto de volta: topo

    def test_medio_dentro_da_faixa_e_periodico(self):
        self.c.start_game("medio")
        for i in range(0, 600):
            t = i * 0.1
            x, y = self.c.get_servo_angles(t)
            self.assertTrue(55 <= x <= 125 and 65 <= y <= 115, f"t={t}: ({x},{y})")
            if t >= 1:   # depois da rampa inicial
                self.assertEqual(self.c.get_servo_angles(t + 10), (x, y), f"não é periódico em t={t}")

    def test_medio_e_suave(self):
        self.c.start_game("medio")
        ant = self.c.get_servo_angles(0)
        for i in range(1, 300):
            atual = self.c.get_servo_angles(i * 0.05)
            self.assertLessEqual(abs(atual[0] - ant[0]), 4)
            self.assertLessEqual(abs(atual[1] - ant[1]), 4)
            ant = atual

    def test_dificil_faixa_completa(self):
        self.c.start_game("dificil")
        for i in range(0, 1200):
            x, y = self.c.get_servo_angles(i * 0.05)
            self.assertTrue(30 <= x <= 150 and 30 <= y <= 150, f"({x},{y})")

    def test_dificil_e_deterministico_e_muda_de_alvo(self):
        self.c.start_game("dificil")
        pontos = [self.c.get_servo_angles(t) for t in (1.0, 3.0, 5.0, 7.0, 9.0)]
        self.assertEqual(pontos, [self.c.get_servo_angles(t) for t in (1.0, 3.0, 5.0, 7.0, 9.0)])
        self.assertGreater(len(set(pontos)), 1, "DIFÍCIL deve mudar de posição")

    def test_dificil_partidas_diferentes_tem_alvos_diferentes(self):
        a = LaserController(seed=1); a.start_game("dificil")
        b = LaserController(seed=2); b.start_game("dificil")
        self.assertNotEqual([a.alvo_dificil(k) for k in range(5)], [b.alvo_dificil(k) for k in range(5)])

    def test_dificil_sem_semente_sorteia_uma_por_partida(self):
        c = LaserController(relogio=self.relogio)
        c.start_game("dificil"); s1 = [c.alvo_dificil(k) for k in range(5)]
        c.start_game("dificil"); s2 = [c.alvo_dificil(k) for k in range(5)]
        self.assertNotEqual(s1, s2)

    def test_dificil_transicao_respeita_a_velocidade_maxima(self):
        """Pior caso: 120 graus em 0,5 s = 24 graus por decimo de segundo (o teste do prompt exigia <15: impossivel)."""
        self.c.start_game("dificil")
        ant = self.c.get_servo_angles(0)
        for i in range(1, 400):
            atual = self.c.get_servo_angles(i * 0.1)
            self.assertLessEqual(abs(atual[0] - ant[0]), 25)
            self.assertLessEqual(abs(atual[1] - ant[1]), 25)
            ant = atual

    def test_dificil_sem_salto_na_virada_de_ciclo(self):
        self.c.start_game("dificil")
        for ciclo in range(1, 15):
            antes = self.c.get_servo_angles(ciclo * 2.0 - 1e-6)
            depois = self.c.get_servo_angles(ciclo * 2.0 + 1e-6)
            self.assertLessEqual(max(abs(antes[0] - depois[0]), abs(antes[1] - depois[1])), 1)

    def test_nivel_invalido(self):
        with self.assertRaises(ValueError):
            self.c.start_game("impossivel")

    def test_nivel_aceita_maiusculas(self):
        self.assertEqual(self.c.start_game("DIFICIL"), Nivel.DIFICIL)

    def test_inativo_fica_no_centro(self):
        self.assertFalse(self.c.is_active)
        self.assertEqual(self.c.get_servo_angles(), (90, 90))

    def test_parar_desativa(self):
        self.c.start_game("medio")
        self.assertTrue(self.c.is_active)
        self.c.stop_game()
        self.assertFalse(self.c.is_active)

    def test_jogo_expira_sozinho(self):
        """Se o app cair sem mandar /jogo/parar, o laser não pode ficar se movendo para sempre."""
        self.c.start_game("dificil")
        self.relogio.t += MAX_JOGO_S - 1
        self.assertTrue(self.c.is_active)
        self.relogio.t += 2
        self.assertFalse(self.c.is_active)


class TestDriver(unittest.TestCase):

    def montar(self, modo, nivel, seed=7):
        self.relogio = Relogio()
        self.ctrl = LaserController(seed=seed, relogio=self.relogio)
        self.ard = ArduinoSimulado()
        self.drv = LaserDriver(self.ctrl, self.ard.escrever, modo)
        self.ctrl.start_game(nivel)

    def rodar(self, segundos, taxa=20):
        for _ in range(int(segundos * taxa)):
            self.relogio.t += 1.0 / taxa
            self.drv.passo()

    # --- modo absoluto ---------------------------------------------------------------------
    def test_abs_medio_envia_comandos_G_validos(self):
        self.montar("abs", "medio")
        self.rodar(10)
        gs = [e for e in self.ard.escritas if e.startswith("G")]
        self.assertGreater(len(gs), 50)
        for g in gs:
            self.assertRegex(g, r"^G\d{1,3},\d{1,3}\n$")
        self.assertEqual((self.ard.a1, self.ard.a2), tuple(self.drv.pos))

    def test_abs_nao_reenvia_posicao_repetida(self):
        self.montar("abs", "dificil")
        self.rodar(1.4)   # ainda na fase de manutenção do alvo: nada de novo a enviar
        n = len(self.ard.escritas)
        self.rodar(0.9)
        self.assertLessEqual(len(self.ard.escritas) - n, 12)   # no máx. a transição do ciclo seguinte

    def test_abs_dificil_alcanca_o_alvo(self):
        self.montar("abs", "dificil")
        self.rodar(0.6)
        self.assertEqual((self.ard.a1, self.ard.a2), self.ctrl.alvo_dificil(0))

    # --- modo incremental (sketch atual) ----------------------------------------------------
    def test_incremental_so_envia_comandos_que_o_sketch_conhece(self):
        self.montar("incremental", "dificil")
        self.rodar(30)   # ArduinoSimulado levanta erro se vier algo diferente de A/D/W/S/R
        self.assertTrue(all(set(e) <= set("ADWSR") for e in self.ard.escritas))

    def test_incremental_posicao_estimada_igual_a_real(self):
        for nivel in ("medio", "dificil"):
            with self.subTest(nivel=nivel):
                self.montar("incremental", nivel)
                for _ in range(600):
                    self.relogio.t += 0.05
                    self.drv.passo()
                    self.assertEqual([self.ard.a1, self.ard.a2], self.drv.pos)
                    self.assertTrue(0 <= self.ard.a1 <= 180 and 0 <= self.ard.a2 <= 180)

    def test_incremental_medio_acompanha_o_alvo(self):
        self.montar("incremental", "medio")
        self.rodar(3)   # depois da rampa
        maior = 0
        for _ in range(200):
            self.relogio.t += 0.05
            self.drv.passo()
            ax, ay = self.ctrl.get_servo_angles()
            maior = max(maior, abs(self.ard.a1 - ax), abs(self.ard.a2 - ay))
        self.assertLessEqual(maior, 10, "no MEDIO o laser deve ficar a no maximo 10 graus do alvo")

    def test_incremental_dificil_e_limitado_pela_velocidade(self):
        """Limitação conhecida: com passos de 5° o DIFÍCIL não alcança as transições de 0,5 s."""
        self.montar("incremental", "dificil", seed=3)
        maior = 0
        for _ in range(400):
            self.relogio.t += 0.05
            self.drv.passo()
            ax, ay = self.ctrl.get_servo_angles()
            maior = max(maior, abs(self.ard.a1 - ax), abs(self.ard.a2 - ay))
        self.assertGreater(maior, 10)

    # --- comum -----------------------------------------------------------------------------------
    def test_facil_so_centraliza_uma_vez_e_deixa_o_operador_ajustar(self):
        for modo in ("abs", "incremental"):
            with self.subTest(modo=modo):
                self.montar(modo, "facil")
                self.rodar(30)
                self.assertEqual(len(self.ard.escritas), 1)
                self.assertEqual((self.ard.a1, self.ard.a2), (90, 90))

    def test_volta_ao_centro_ao_parar(self):
        for modo in ("abs", "incremental"):
            with self.subTest(modo=modo):
                self.montar(modo, "dificil")
                self.rodar(5)
                self.ctrl.stop_game()
                self.rodar(0.2)
                self.assertEqual((self.ard.a1, self.ard.a2), (90, 90))
                self.assertEqual(self.drv.pos, [90, 90])

    def test_volta_ao_centro_quando_o_jogo_expira(self):
        self.montar("incremental", "dificil")
        self.rodar(5)
        self.relogio.t += MAX_JOGO_S
        self.rodar(0.2)
        self.assertEqual((self.ard.a1, self.ard.a2), (90, 90))

    def test_manual_abs(self):
        self.montar("abs", "medio")
        self.rodar(2)
        self.assertEqual(self.drv.ir_para(120, 60), (120, 60))
        self.assertFalse(self.ctrl.is_active)
        self.assertEqual((self.ard.a1, self.ard.a2), (120, 60))

    def test_manual_incremental_e_nao_e_recentralizado_pelo_fim_de_jogo(self):
        self.montar("incremental", "medio")
        self.rodar(2)
        x, y = self.drv.ir_para(120, 60)
        self.rodar(1)   # o laço NÃO pode "voltar ao centro" por cima da posição manual
        self.assertEqual((self.ard.a1, self.ard.a2), (x, y))
        self.assertLessEqual(abs(x - 120), 3)
        self.assertLessEqual(abs(y - 60), 3)

    def test_manual_limita_a_faixa_do_servo(self):
        self.montar("abs", "facil")
        self.assertEqual(self.drv.ir_para(500, -20), (180, 0))

    def test_simulado_nao_escreve_nada(self):
        self.montar("simulado", "medio")
        self.rodar(5)
        self.assertEqual(self.ard.escritas, [])


if __name__ == "__main__":
    unittest.main()
