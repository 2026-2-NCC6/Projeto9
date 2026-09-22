"""
Benchmark de bola RÁPIDA com borrão de movimento (frames sintéticos, sem câmera).

Uma bola atravessa o quadro na horizontal, passando pelo alvo. A velocidade é dada em px/frame e o
borrão pela fração do intervalo entre frames em que o obturador fica aberto (exposição). Mede:
  - detecção: % de frames em que a bola é encontrada perto da posição real
  - acerto:   % de passagens pelo alvo que viram ACERTO, olhando só os pontos ("ponto") ou o trecho
              entre dois frames ("trajetoria")

Uso:  python bench_movimento.py
"""
import math

import cv2
import numpy as np

from ball_detector import BallDetector
from hit_detector import distancia_ponto_segmento

W, H = 640, 480
RAIO = 22
ALVO = (320, 240)
TOL_PX = 8            # tolerância do acerto, em pixels
FUNDO_BGR = (150, 160, 172)   # parede clara (bege/cinza): o borrão mistura a bola COM O FUNDO
SUBQUADROS = 14       # posições somadas para simular o borrão
SEMENTES = 8          # passagens por combinação (a fase do alvo muda em cada uma)


BOLA_HSV = (30, 200, 220)     # --palida usa uma bola menos saturada (câmera real, brilho estourado)


def bola_bgr():
    return np.uint8([[list(BOLA_HSV)]])


def render(cx, cy, vx, expo, rng):
    """Um frame: a bola percorre vx*expo pixels enquanto o obturador está aberto.
    Renderiza só a faixa de linhas por onde a bola passa (o resto é só parede)."""
    y0, y1 = cy - RAIO - 3, cy + RAIO + 4
    faixa = np.zeros((y1 - y0, W, 3), dtype=np.float32)
    cor = cv2.cvtColor(bola_bgr(), cv2.COLOR_HSV2BGR)[0][0].astype(np.float32)
    for u in np.linspace(-0.5, 0.5, SUBQUADROS):
        q = np.empty((y1 - y0, W, 3), dtype=np.uint8)
        q[:] = FUNDO_BGR
        cv2.circle(q, (int(round(cx + vx * expo * u)), cy - y0), RAIO, tuple(int(c) for c in cor), -1)
        faixa += q
    faixa /= SUBQUADROS
    faixa += rng.normal(0, 3, faixa.shape)           # ruído do sensor
    frame = np.empty((H, W, 3), dtype=np.uint8)
    frame[:] = FUNDO_BGR
    frame[y0:y1] = np.clip(faixa, 0, 255).astype(np.uint8)
    return frame


def _avaliar(frames, xs, usar_track):
    det = BallDetector()
    achou, dets = 0, []
    for frame, x in zip(frames, xs):
        d = det.seguir(frame, cam=1) if usar_track else det.detect_ball_camera1(frame)
        ok = d is not None and math.hypot(d[0] - x, d[1] - ALVO[1]) <= 1.5 * RAIO
        achou += ok
        dets.append((d[0], d[1]) if ok else None)
    # acerto por ponto: algum frame com a bola a <= TOL_PX do alvo
    ponto = any(p is not None and math.hypot(p[0] - ALVO[0], p[1] - ALVO[1]) <= TOL_PX for p in dets)
    # acerto por trajetória: o trecho entre dois frames consecutivos passa a <= TOL_PX do alvo
    traj = ponto
    for a, b in zip(dets, dets[1:]):
        if a is not None and b is not None and distancia_ponto_segmento(ALVO, a, b) <= TOL_PX:
            traj = True
    return achou / len(xs), ponto, traj


def passagem(v, expo, seed):
    """Renderiza uma passagem UMA vez e avalia os dois detectores nos mesmos frames."""
    rng = np.random.default_rng(seed)
    xs = np.arange(40 + (seed * v) // SEMENTES, W - 40, v)   # fases uniformes: o alvo cai em pontos diferentes do passo
    frames = [render(x, ALVO[1], v, expo, rng) for x in xs]
    return _avaliar(frames, xs, False), _avaliar(frames, xs, True)


def main():
    print(f"bola de {2 * RAIO}px atravessando o alvo | tolerancia {TOL_PX}px | detector: cor apenas (antes) x cor+ROI (depois)\n")
    print(f"px/frame  expo  | deteccao antes -> depois | acerto por ponto -> por trajetoria ({SEMENTES} passagens)")
    for v in (5, 10, 20, 40, 80):
        for expo in (0.25, 0.5, 1.0):
            det_a, det_d, ponto, traj = [], [], 0, 0
            for seed in range(SEMENTES):
                (a, _, _), (d, p, t) = passagem(v, expo, seed)
                det_a.append(a); det_d.append(d); ponto += p; traj += t
            print(f"{v:>7}  {expo:>4}  |   {100 * np.mean(det_a):5.0f}% -> {100 * np.mean(det_d):5.0f}%      |"
                  f"   {ponto:>2}/{SEMENTES} -> {traj:>2}/{SEMENTES}")


if __name__ == "__main__":
    import sys
    if "--palida" in sys.argv:
        BOLA_HSV = (30, 110, 190)
        print("(bola PALIDA: HSV 30,110,190)")
    main()
