"""
Testes do modo de teste com 1 câmera (sem câmera real: frames sintéticos e câmera falsa).
Rode dentro de vision/:  python -m unittest test_modo_teste -v
"""
import unittest
from unittest import mock

import cv2
import numpy as np

import config
import main
from ball_detector import BallDetector

W, H = 640, 480


def frame_com_bola(px, py, raio=25, h=30):
    frame = np.zeros((H, W, 3), dtype=np.uint8)
    bgr = tuple(int(c) for c in cv2.cvtColor(np.uint8([[[h, 200, 220]]]), cv2.COLOR_HSV2BGR)[0][0])
    cv2.circle(frame, (int(px), int(py)), raio, bgr, -1)
    return frame


def sistema(**kw):
    s = main.SmartTennisVision(test_mode=True, headless=True, **kw)
    s.calibration.calibrate_camera1(np.zeros((H, W, 3), dtype=np.uint8), salvar=False)
    return s


class TestAvaliacaoDoModoTeste(unittest.TestCase):

    def test_bola_no_laser_e_acerto_simulado(self):
        s = sistema(tolerancia=0.10)
        px, py = s.calibration.world_to_pixel_camera1(config.LASER_X, config.LASER_Z)
        det, info = s.avaliar_teste(frame_com_bola(px, py), agora=100.0)
        X, Z, dist, acerto = info
        self.assertLess(dist, 0.05)
        self.assertTrue(acerto)
        self.assertEqual(s.acertos_simulados, 1)

    def test_bola_longe_do_laser_nao_acerta(self):
        s = sistema()
        det, info = s.avaliar_teste(frame_com_bola(60, 60), agora=100.0)
        self.assertIsNotNone(det)
        self.assertFalse(info[3])
        self.assertGreater(info[2], 0.5)

    def test_sem_bola(self):
        s = sistema()
        det, info = s.avaliar_teste(np.zeros((H, W, 3), dtype=np.uint8))
        self.assertIsNone(det)
        self.assertIsNone(info)
        self.assertEqual((s.frames, s.frames_com_bola), (1, 0))

    def test_debounce_do_acerto(self):
        s = sistema(tolerancia=0.10)
        px, py = s.calibration.world_to_pixel_camera1(config.LASER_X, config.LASER_Z)
        f = frame_com_bola(px, py)
        self.assertTrue(s.avaliar_teste(f, agora=100.0)[1][3])
        self.assertFalse(s.avaliar_teste(f, agora=100.0 + config.HIT_DEBOUNCE_S / 2)[1][3])
        self.assertTrue(s.avaliar_teste(f, agora=100.0 + config.HIT_DEBOUNCE_S + 0.1)[1][3])
        self.assertEqual(s.acertos_simulados, 2)

    def test_tolerancia_configuravel(self):
        s = sistema(tolerancia=0.01)
        px, py = s.calibration.world_to_pixel_camera1(config.LASER_X + 0.3, config.LASER_Z)
        self.assertFalse(s.avaliar_teste(frame_com_bola(px, py), agora=1.0)[1][3])
        s2 = sistema(tolerancia=0.5)
        self.assertTrue(s2.avaliar_teste(frame_com_bola(px, py), agora=1.0)[1][3])

    def test_estatisticas(self):
        s = sistema()
        for f in (np.zeros((H, W, 3), np.uint8), frame_com_bola(100, 100), frame_com_bola(200, 200)):
            s.avaliar_teste(f, agora=1.0)
        self.assertEqual((s.frames, s.frames_com_bola), (3, 2))


class TestFaixasHSV(unittest.TestCase):

    def test_faixa_estreita_que_nao_cobre_a_bola_nao_detecta(self):
        d = BallDetector()
        f = frame_com_bola(300, 200, h=30)
        self.assertIsNotNone(d.detect_ball_camera1(f))
        d.set_faixas([((100, 80, 100), (110, 255, 255))])      # só azul
        self.assertIsNone(d.detect_ball_camera1(f))
        d.restaurar_faixas()
        self.assertIsNotNone(d.detect_ball_camera1(f))

    def test_faixa_unica_dos_sliders(self):
        d = BallDetector()
        d.set_faixas([((25, 100, 100), (35, 255, 255))])
        self.assertIsNotNone(d.detect_ball_camera1(frame_com_bola(300, 200, h=30)))

    def test_mascara_e_binaria_do_tamanho_do_frame(self):
        m = BallDetector().mascara(frame_com_bola(300, 200))
        self.assertEqual(m.shape, (H, W))
        self.assertTrue(set(np.unique(m)) <= {0, 255})

    def test_draw_aceita_segundo_frame_none(self):
        f = frame_com_bola(300, 200)
        BallDetector.draw_detections(f, None, (300, 200, 25), None)   # não pode levantar


class TestFiltroDeRedondeza(unittest.TestCase):

    def setUp(self):
        self.d = BallDetector()

    def _bgr(self, h=30):
        return tuple(int(c) for c in cv2.cvtColor(np.uint8([[[h, 200, 220]]]), cv2.COLOR_HSV2BGR)[0][0])

    def test_bola_redonda_passa(self):
        self.assertIsNotNone(self.d.detect_ball_camera1(frame_com_bola(300, 200, raio=30)))

    def test_bola_borrada_2_para_1_ainda_passa(self):
        f = np.zeros((H, W, 3), dtype=np.uint8)
        cv2.ellipse(f, (300, 200), (40, 20), 0, 0, 360, self._bgr(), -1)
        self.assertIsNotNone(self.d.detect_ball_camera1(f))

    def test_mancha_esparsa_e_rejeitada(self):
        """Regressao medida na webcam real: mancha bege grande e esparsa era aceita como bola."""
        f = np.zeros((H, W, 3), dtype=np.uint8)
        cor = self._bgr()
        for (x, y) in ((100, 100), (300, 110), (110, 300), (300, 310), (200, 200)):
            cv2.circle(f, (x, y), 22, cor, -1)          # 5 pontos separados dentro de uma area grande
        cv2.line(f, (100, 100), (300, 310), cor, 6)     # ligados por um fio fino: 1 contorno, pouco preenchido
        cv2.line(f, (300, 110), (110, 300), cor, 6)
        self.assertIsNone(self.d.detect_ball_camera1(f))


class FakeCamera:
    """Substitui CameraThread: entrega sempre o mesmo frame sintético."""
    def __init__(self, *a, **k):
        self._f = frame_com_bola(100, 100)
        self.fechada = False

    def abrir(self):
        return True

    def ultimo_frame(self):
        return self._f

    def fechar(self):
        self.fechada = True


class TestInicializacao(unittest.TestCase):

    def test_modo_teste_nao_liga_flask_nem_grava_calibracao(self):
        s = main.SmartTennisVision(test_mode=True, headless=True)
        with mock.patch.object(main, "CameraThread", FakeCamera), \
             mock.patch.object(s.flask, "start_heartbeat") as hb, \
             mock.patch("camera_calibration.np.save") as salvar:
            self.assertTrue(s.initialize())
        hb.assert_not_called()      # senão o app acharia que a visão está ativa
        salvar.assert_not_called()  # a calibração das 2 câmeras da arena não pode ser sobrescrita
        self.assertTrue(s.running)

    def test_camera_que_nao_abre(self):
        class Quebrada(FakeCamera):
            def abrir(self):
                return False
        s = main.SmartTennisVision(test_mode=True, headless=True)
        with mock.patch.object(main, "CameraThread", Quebrada):
            self.assertFalse(s.initialize())

    def test_loop_headless_encerra_por_tempo_e_conta_frames(self):
        s = main.SmartTennisVision(test_mode=True, headless=True, segundos=0.3)
        with mock.patch.object(main, "CameraThread", FakeCamera):
            self.assertTrue(s.initialize())
            s.cam._f = frame_com_bola(100, 100)
            # o FakeCamera devolve SEMPRE o mesmo objeto: só o 1º conta como frame novo
            s.run()
        self.assertGreaterEqual(s.frames, 1)


class TestLinhaDeComando(unittest.TestCase):

    def test_padroes(self):
        a = main.criar_parser().parse_args([])
        self.assertFalse(a.test)
        self.assertFalse(a.debug)
        self.assertEqual(a.camera, config.CAMERA1_ID)
        self.assertEqual(a.fps_limit, config.TARGET_FPS)
        self.assertEqual(a.tolerancia, config.HIT_TOLERANCE)

    def test_flags(self):
        a = main.criar_parser().parse_args(
            ["--test", "--debug", "--camera", "2", "--fps-limit", "15", "--headless", "--segundos", "5",
             "--tolerancia", "0.2"])
        self.assertTrue(a.test and a.debug and a.headless)
        self.assertEqual((a.camera, a.fps_limit, a.segundos, a.tolerancia), (2, 15, 5.0, 0.2))


if __name__ == "__main__":
    unittest.main()
