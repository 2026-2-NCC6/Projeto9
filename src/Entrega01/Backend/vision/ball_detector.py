import math

import cv2
import numpy as np

from config import (YELLOW_LOWER, YELLOW_UPPER, GREEN_LOWER, GREEN_UPPER,
                    BALL_MIN_AREA, BALL_MAX_AREA, BALL_MIN_RADIUS, BALL_MIN_FILL,
                    MAX_FRAMES_PERDIDOS, ROI_FATOR_S, ROI_FATOR_V, BALL_MIN_FILL_ROI)

FAIXAS_PADRAO = (
    (tuple(YELLOW_LOWER), tuple(YELLOW_UPPER)),
    (tuple(GREEN_LOWER), tuple(GREEN_UPPER)),
)


class BallDetector:
    """
    Detecta a bola por cor (HSV): união das faixas (padrão: amarelo OU verde).

    detect_ball_camera1/2  detecção "estrita" de um frame isolado.
    seguir                 estrita + memória: se a bola some (borrão de movimento), procura de novo
                           SÓ perto de onde ela deveria estar, com limiares de cor mais tolerantes.
    """

    def __init__(self):
        self.last_center1 = None
        self.last_center2 = None
        self.faixas = list(FAIXAS_PADRAO)
        self.ultima_origem = None        # "cor" (detecção normal) ou "roi" (reencontrada perto da previsão)
        self._tracks = {}                # cam -> {"pos", "r", "vel", "perdidos"}
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    # --- faixas de cor (ajustáveis ao vivo pelos sliders do modo teste) -------------------
    def set_faixas(self, faixas):
        """faixas = [((h,s,v)_min, (h,s,v)_max), ...]"""
        self.faixas = [(tuple(lo), tuple(hi)) for lo, hi in faixas]

    def restaurar_faixas(self):
        self.faixas = list(FAIXAS_PADRAO)

    def faixas_relaxadas(self):
        """Mesmas cores, mas aceitando menos saturação e brilho (bola borrada perde os dois)."""
        return [((lo[0], int(lo[1] * ROI_FATOR_S), int(lo[2] * ROI_FATOR_V)), hi) for lo, hi in self.faixas]

    def mascara(self, frame, faixas=None):
        """Máscara binária (já limpa) dos pixels cuja cor está em alguma das faixas."""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
        for lo, hi in (self.faixas if faixas is None else faixas):
            mask = cv2.bitwise_or(mask, cv2.inRange(hsv, lo, hi))
        # fecha buracos e remove ruído
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self._kernel, iterations=2)
        return cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._kernel, iterations=1)

    def _detect(self, frame):
        """Retorna (x, y, raio) em pixels do maior blob de cor válido, ou None."""
        contours, _ = cv2.findContours(self.mascara(frame), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        maior = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(maior)
        if area < BALL_MIN_AREA or area > BALL_MAX_AREA:
            return None

        (x, y), raio = cv2.minEnclosingCircle(maior)
        if raio < BALL_MIN_RADIUS:
            return None
        if area / (math.pi * raio * raio) < BALL_MIN_FILL:   # mancha esparsa, não uma bola
            return None
        return int(x), int(y), int(raio)

    def _detect_roi(self, frame, centro, meia_largura):
        """Procura a bola numa janela ao redor de `centro`, com cor relaxada e forma mais tolerante."""
        h, w = frame.shape[:2]
        x0, x1 = max(0, int(centro[0] - meia_largura)), min(w, int(centro[0] + meia_largura))
        y0, y1 = max(0, int(centro[1] - meia_largura)), min(h, int(centro[1] + meia_largura))
        if x1 - x0 < 12 or y1 - y0 < 12:
            return None
        mask = self.mascara(frame[y0:y1, x0:x1], self.faixas_relaxadas())
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        melhor, melhor_dist = None, None
        for c in contours:
            area = cv2.contourArea(c)
            if area < BALL_MIN_AREA * 0.4 or area > BALL_MAX_AREA * 1.5:
                continue
            (cx, cy), raio = cv2.minEnclosingCircle(c)
            if raio < BALL_MIN_RADIUS * 0.7 or area / (math.pi * raio * raio) < BALL_MIN_FILL_ROI:
                continue
            cx, cy = cx + x0, cy + y0
            dist = math.hypot(cx - centro[0], cy - centro[1])
            if melhor_dist is None or dist < melhor_dist:      # o blob mais perto da previsão
                melhor, melhor_dist = (int(cx), int(cy), int(raio)), dist
        return melhor

    # --- API por câmera ------------------------------------------------------------------------
    def detect_ball_camera1(self, frame):
        """Câmera 1 (cima). Retorna (x_px, y_px, raio_px) ou None. Sem memória entre frames."""
        self.last_center1 = self._detect(frame)
        return self.last_center1

    def detect_ball_camera2(self, frame):
        """Câmera 2 (lado). Retorna (x_px, y_px, raio_px) ou None. Sem memória entre frames."""
        self.last_center2 = self._detect(frame)
        return self.last_center2

    def seguir(self, frame, cam=1):
        """
        Detecção com memória (uma por câmera). Se a detecção normal falha logo depois de ter visto a
        bola, extrapola a posição pela velocidade e procura de novo só ali, com limiares tolerantes.
        Nunca inventa posição: só devolve o que foi realmente encontrado no frame.
        """
        det = self._detect(frame)
        origem = "cor"
        trk = self._tracks.get(cam)
        if det is None and trk is not None and trk["perdidos"] < MAX_FRAMES_PERDIDOS:
            n = trk["perdidos"] + 1
            previsto = (trk["pos"][0] + trk["vel"][0] * n, trk["pos"][1] + trk["vel"][1] * n)
            meia = max(80.0, 3.0 * trk["r"] + 2.0 * math.hypot(*trk["vel"]))
            det = self._detect_roi(frame, previsto, meia)
            origem = "roi"

        if det is not None:
            self._atualizar_track(cam, det)
            self.ultima_origem = origem
        elif trk is not None:
            trk["perdidos"] += 1
            if trk["perdidos"] >= MAX_FRAMES_PERDIDOS:
                del self._tracks[cam]

        if cam == 1:
            self.last_center1 = det
        else:
            self.last_center2 = det
        return det

    def _atualizar_track(self, cam, det):
        x, y, r = det
        trk = self._tracks.get(cam)
        if trk is None:
            self._tracks[cam] = {"pos": (x, y), "r": r, "vel": (0.0, 0.0), "perdidos": 0}
            return
        n = trk["perdidos"] + 1                                   # frames desde a última detecção real
        vel = ((x - trk["pos"][0]) / n, (y - trk["pos"][1]) / n)
        trk["vel"] = (0.5 * trk["vel"][0] + 0.5 * vel[0], 0.5 * trk["vel"][1] + 0.5 * vel[1])
        trk["pos"], trk["r"], trk["perdidos"] = (x, y), r, 0

    def resetar_track(self, cam=None):
        if cam is None:
            self._tracks.clear()
        else:
            self._tracks.pop(cam, None)

    @staticmethod
    def draw_detections(frame1, frame2, det1, det2, origem=None):
        """Desenha as detecções nos frames (debug). frame2/det2 podem ser None (modo 1 câmera)."""
        for frame, det, cor, nome in ((frame1, det1, (0, 255, 0), "Ball1"),
                                      (frame2, det2, (0, 255, 255), "Ball2")):
            if frame is not None and det:
                x, y, r = det
                if origem == "roi":
                    cor = (0, 165, 255)                           # laranja: reencontrada perto da previsão
                cv2.circle(frame, (x, y), r, cor, 2)
                cv2.putText(frame, f"{nome} ({x},{y}) r={r}" + (" [ROI]" if origem == "roi" else ""),
                            (x - 50, y - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, cor, 1)
        return frame1, frame2
