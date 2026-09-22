"""
Testes SEM câmeras: frames sintéticos e Flask simulado.
Rode dentro de vision/:  python test_without_cameras.py -v
"""
import unittest
from unittest import mock

import cv2
import numpy as np

import config
from ball_detector import BallDetector
from camera_calibration import CameraCalibration
from flask_client import FlaskClient
from hit_detector import HitDetector

W, H = config.CAMERA_WIDTH, config.CAMERA_HEIGHT


def frame_em_branco():
    return np.zeros((H, W, 3), dtype=np.uint8)


def bola_bgr(h=30, s=200, v=220):
    """Cor da bola em BGR a partir de HSV (H no padrão OpenCV 0-179)."""
    return tuple(int(c) for c in cv2.cvtColor(np.uint8([[[h, s, v]]]), cv2.COLOR_HSV2BGR)[0][0])


def calibracao_padrao():
    cal = CameraCalibration()
    # salvar=False: o teste NUNCA pode sobrescrever a calibração real das câmeras da arena
    cal.calibrate_camera1(frame_em_branco(), salvar=False)
    cal.calibrate_camera2(frame_em_branco(), salvar=False)
    return cal


class TestCalibracaoETriangulacao(unittest.TestCase):

    def setUp(self):
        self.cal = calibracao_padrao()
        self.hits = HitDetector(self.cal)

    def test_posicao_do_laser(self):
        self.assertAlmostEqual(config.LASER_X, 1.5)
        self.assertAlmostEqual(config.LASER_Y, 1.2)
        self.assertAlmostEqual(config.LASER_Z, -1.0)

    def test_laser_esta_dentro_da_area_calibrada(self):
        """Regressão: o laser precisa cair dentro do que as câmeras enxergam."""
        self.assertTrue(config.CAM1_X_RANGE[0] <= config.LASER_X <= config.CAM1_X_RANGE[1])
        self.assertTrue(min(config.CAM1_Z_RANGE) <= config.LASER_Z <= max(config.CAM1_Z_RANGE))
        self.assertTrue(min(config.CAM2_Z_RANGE) <= config.LASER_Z <= max(config.CAM2_Z_RANGE))
        self.assertTrue(min(config.CAM2_Y_RANGE) <= config.LASER_Y <= max(config.CAM2_Y_RANGE))

    def test_cantos_do_frame(self):
        # câmera 1: topo-esq = (X mín, fundo do gol); base-dir = (X máx, frente)
        self.assertEqual(tuple(round(v, 6) for v in self.cal.pixel_to_world_camera1(0, 0)),
                         (config.CAM1_X_RANGE[0], config.CAM1_Z_RANGE[0]))
        self.assertEqual(tuple(round(v, 6) for v in self.cal.pixel_to_world_camera1(W, H)),
                         (config.CAM1_X_RANGE[1], config.CAM1_Z_RANGE[1]))
        # câmera 2: base do frame = chão; topo = altura do gol
        z, y = self.cal.pixel_to_world_camera2(0, H)
        self.assertAlmostEqual(y, config.CAM2_Y_RANGE[0], places=6)
        z, y = self.cal.pixel_to_world_camera2(0, 0)
        self.assertAlmostEqual(y, config.CAM2_Y_RANGE[1], places=6)

    def test_ida_e_volta_pixel_mundo(self):
        px = self.cal.world_to_pixel_camera1(config.LASER_X, config.LASER_Z)
        x, z = self.cal.pixel_to_world_camera1(*px)
        self.assertAlmostEqual(x, config.LASER_X, places=5)
        self.assertAlmostEqual(z, config.LASER_Z, places=5)

    def test_bola_no_pixel_do_laser_vira_acerto(self):
        """Ponta a ponta da geometria: projeta o laser em pixels, triangula de volta, deve acertar."""
        p1 = self.cal.world_to_pixel_camera1(config.LASER_X, config.LASER_Z)
        p2 = self.cal.world_to_pixel_camera2(config.LASER_Z, config.LASER_Y)
        pos = self.hits.triangulate_ball_position((p1[0], p1[1], 10), (p2[0], p2[1], 10))
        self.assertIsNotNone(pos)
        for obtido, esperado in zip(pos, (config.LASER_X, config.LASER_Y, config.LASER_Z)):
            self.assertAlmostEqual(obtido, esperado, places=5)
        self.assertTrue(self.hits.check_hit(pos))

    def test_sem_deteccao_nao_triangula(self):
        self.assertIsNone(self.hits.triangulate_ball_position(None, (10, 10, 5)))
        self.assertIsNone(self.hits.triangulate_ball_position((10, 10, 5), None))

    def test_sem_calibracao_nao_triangula(self):
        sem = HitDetector(CameraCalibration())
        self.assertIsNone(sem.triangulate_ball_position((10, 10, 5), (10, 10, 5)))


class TestAcerto(unittest.TestCase):

    def setUp(self):
        self.hits = HitDetector(CameraCalibration())

    def laser(self, dx=0.0, dy=0.0, dz=0.0):
        return (config.LASER_X + dx, config.LASER_Y + dy, config.LASER_Z + dz)

    def test_acerto_exato(self):
        self.assertTrue(self.hits.check_hit(self.laser()))

    def test_limite_da_tolerancia(self):
        """1.55 - 1.5 = 0.05000000000000004 em float; o limite exato tem que contar."""
        self.assertTrue(self.hits.check_hit(self.laser(dx=config.HIT_TOLERANCE)))

    def test_fora_da_tolerancia_em_cada_eixo(self):
        for kw in ({"dx": 0.1}, {"dy": 0.1}, {"dz": 0.1}):
            with self.subTest(kw=kw):
                self.assertFalse(HitDetector(CameraCalibration()).check_hit(self.laser(**kw)))

    def test_debounce(self):
        self.assertTrue(self.hits.check_hit(self.laser(), now=100.0))
        self.assertFalse(self.hits.check_hit(self.laser(), now=100.0 + config.HIT_DEBOUNCE_S / 2))
        self.assertTrue(self.hits.check_hit(self.laser(), now=100.0 + config.HIT_DEBOUNCE_S + 0.01))
        self.assertEqual(self.hits.hit_count, 2)

    def test_posicao_none(self):
        self.assertFalse(self.hits.check_hit(None))

    def test_distancia(self):
        self.assertAlmostEqual(self.hits.get_distance_to_laser(self.laser()), 0.0, places=6)
        self.assertAlmostEqual(self.hits.get_distance_to_laser(self.laser(dx=0.3, dy=0.4)), 0.5, places=6)
        self.assertIsNone(self.hits.get_distance_to_laser(None))


class TestDetectorDeBola(unittest.TestCase):

    def setUp(self):
        self.det = BallDetector()

    def test_detecta_bola_amarelo_esverdeada(self):
        frame = frame_em_branco()
        cv2.circle(frame, (640, 360), 30, bola_bgr(h=30), -1)
        x, y, r = self.det.detect_ball_camera1(frame)
        self.assertLessEqual(abs(x - 640), 3)
        self.assertLessEqual(abs(y - 360), 3)
        self.assertLessEqual(abs(r - 30), 3)

    def test_detecta_faixa_verde(self):
        frame = frame_em_branco()
        cv2.circle(frame, (200, 500), 25, bola_bgr(h=90), -1)
        self.assertIsNotNone(self.det.detect_ball_camera2(frame))

    def test_frame_vazio(self):
        self.assertIsNone(self.det.detect_ball_camera1(frame_em_branco()))

    def test_ignora_ruido_pequeno(self):
        frame = frame_em_branco()
        cv2.circle(frame, (100, 100), 3, bola_bgr(), -1)
        self.assertIsNone(self.det.detect_ball_camera1(frame))

    def test_ignora_objeto_de_outra_cor(self):
        frame = frame_em_branco()
        cv2.circle(frame, (300, 300), 40, (0, 0, 255), -1)  # vermelho
        self.assertIsNone(self.det.detect_ball_camera1(frame))

    def test_escolhe_o_maior_blob(self):
        frame = frame_em_branco()
        cv2.circle(frame, (100, 100), 15, bola_bgr(), -1)
        cv2.circle(frame, (900, 500), 40, bola_bgr(), -1)
        x, y, _ = self.det.detect_ball_camera1(frame)
        self.assertLessEqual(abs(x - 900), 3)


class TestFlaskClient(unittest.TestCase):

    POS = (1.5, 1.2, -1.0)

    def test_payload(self):
        p = FlaskClient.build_payload(self.POS, timestamp=123.0)
        self.assertEqual(p["source"], "vision")
        self.assertTrue(p["acertou"])
        self.assertEqual(p["position"], {"X": 1.5, "Y": 1.2, "Z": -1.0})
        self.assertEqual(p["timestamp"], 123.0)

    def test_envio_ok(self):
        with mock.patch("flask_client.requests.post", return_value=mock.Mock(status_code=200)) as post:
            self.assertTrue(FlaskClient().send_hit(self.POS))
        self.assertEqual(post.call_args.args[0], config.FLASK_URL)
        self.assertEqual(post.call_args.kwargs["json"]["source"], "vision")

    def test_flask_retorna_erro(self):
        with mock.patch("flask_client.requests.post", return_value=mock.Mock(status_code=500)):
            self.assertFalse(FlaskClient().send_hit(self.POS))

    def test_flask_fora_do_ar_nao_levanta_excecao(self):
        import requests
        with mock.patch("flask_client.requests.post", side_effect=requests.exceptions.ConnectionError):
            self.assertFalse(FlaskClient().send_hit(self.POS))

    def test_sem_posicao(self):
        self.assertFalse(FlaskClient().send_hit(None))


if __name__ == "__main__":
    unittest.main()
