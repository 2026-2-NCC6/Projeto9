import math
import time

from config import (LASER_X, LASER_Y, LASER_Z, HIT_TOLERANCE, HIT_DEBOUNCE_S, TRAJETORIA_MAX_S)

_EPS = 1e-9  # 1.55 - 1.5 = 0.05000000000000004 em float: sem folga, o limite da tolerância falharia


def distancia_ponto_segmento(p, a, b):
    """Menor distância do ponto p ao segmento a-b (2D ou 3D; aceita tuplas de qualquer tamanho)."""
    ab = [bi - ai for ai, bi in zip(a, b)]
    ap = [pi - ai for ai, pi in zip(a, p)]
    quad = sum(c * c for c in ab)
    t = 0.0 if quad == 0 else max(0.0, min(1.0, sum(x * y for x, y in zip(ap, ab)) / quad))
    return math.sqrt(sum((pi - (ai + t * c)) ** 2 for pi, ai, c in zip(p, a, ab)))


class HitDetector:
    """Triangulação 3D e decisão de acerto (lógica pura, sem rede)."""

    def __init__(self, calibration):
        self.calibration = calibration
        self.hit_count = 0
        self.last_hit_time = 0.0
        self._anterior = None   # (posição, instante) da última detecção, para o acerto por trajetória

    def triangulate_ball_position(self, det1, det2):
        """
        det1 = (x_px, y_px, r) da câmera 1 (cima)  -> X e Z
        det2 = (x_px, y_px, r) da câmera 2 (lado)  -> Z e Y
        Retorna (X, Y, Z) em metros, ou None se faltar detecção/calibração.
        Z é medido pelas duas câmeras: usa a média.
        """
        if det1 is None or det2 is None:
            return None

        p1 = self.calibration.pixel_to_world_camera1(det1[0], det1[1])
        p2 = self.calibration.pixel_to_world_camera2(det2[0], det2[1])
        if p1 is None or p2 is None:
            return None

        x, z_cima = p1
        z_lado, y = p2
        return x, y, (z_cima + z_lado) / 2.0

    def check_hit(self, ball_pos, now=None):
        """True se a bola está dentro da tolerância do laser nos 3 eixos (com debounce)."""
        if ball_pos is None:
            return False
        now = time.time() if now is None else now
        if now - self.last_hit_time < HIT_DEBOUNCE_S:
            return False

        x, y, z = ball_pos
        if (abs(x - LASER_X) <= HIT_TOLERANCE + _EPS
                and abs(y - LASER_Y) <= HIT_TOLERANCE + _EPS
                and abs(z - LASER_Z) <= HIT_TOLERANCE + _EPS):
            self.last_hit_time = now
            self.hit_count += 1
            return True
        return False

    def check_hit_trajetoria(self, ball_pos, now=None):
        """
        Como check_hit, mas olha também o TRECHO entre a detecção anterior e a atual. A 30 FPS uma bola a
        6 m/s anda ~20 cm por frame: ela pode cruzar o alvo (tolerância de 5 cm) sem nenhum frame cair
        dentro dele. Se a detecção anterior for antiga demais, só vale o ponto.
        """
        if ball_pos is None:
            return False
        now = time.time() if now is None else now
        anterior, self._anterior = self._anterior, (ball_pos, now)
        if now - self.last_hit_time < HIT_DEBOUNCE_S:
            return False

        laser = (LASER_X, LASER_Y, LASER_Z)
        if anterior is not None and now - anterior[1] <= TRAJETORIA_MAX_S:
            dist = distancia_ponto_segmento(laser, anterior[0], ball_pos)
        else:
            dist = math.dist(laser, ball_pos)
        x, y, z = ball_pos
        no_cubo = (abs(x - LASER_X) <= HIT_TOLERANCE + _EPS and abs(y - LASER_Y) <= HIT_TOLERANCE + _EPS
                   and abs(z - LASER_Z) <= HIT_TOLERANCE + _EPS)      # o mesmo teste do check_hit
        if no_cubo or dist <= HIT_TOLERANCE + _EPS:                   # ...ou o trecho passou pelo alvo
            self.last_hit_time = now
            self.hit_count += 1
            return True
        return False

    @staticmethod
    def get_distance_to_laser(ball_pos):
        """Distância 3D bola-laser em metros (debug)."""
        if ball_pos is None:
            return None
        x, y, z = ball_pos
        return math.sqrt((x - LASER_X) ** 2 + (y - LASER_Y) ** 2 + (z - LASER_Z) ** 2)
