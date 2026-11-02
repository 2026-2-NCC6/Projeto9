"""Rotula frames de uma camera FIXA comparando cada quadro com o fundo (MOG2) E checando a cor
(amarelo-esverdeado da bola de tenis). So movimento nao bastou: numa cena com pano preto amassado
(reflexos/dobras se mexendo) e gente controlando a bola por barbante, o blob que mais se move costuma
ser a mao/braço ou uma dobra do pano, nao a bola. Exigir a cor da bola alem do movimento elimina os
dois (mao e pano nao tem essa cor)."""
import argparse
import math
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VISION_DIR = os.path.dirname(SCRIPT_DIR)
ROOT_DIR = os.path.dirname(VISION_DIR)

import cv2
import numpy as np

AQUECIMENTO = 20     # frames pro MOG2 aprender o fundo antes de confiar nele
AREA_MIN, AREA_MAX = 150, 6000
FILL_MIN = 0.5        # redondeza: area do blob / area do circulo que o envolve
COR_MIN = (18, 50, 80)     # HSV: amarelo-esverdeado da bola de tenis (medido numa foto real)
COR_MAX = (42, 255, 255)


def _numero(nome):
    m = re.search(r"(\d+)", nome)
    return int(m.group(1)) if m else 0


def _frames_ordenados(pasta, desde=None):
    arquivos = [f for f in os.listdir(pasta) if f.lower().endswith(".jpg")]
    arquivos.sort(key=_numero)
    if desde is not None:
        arquivos = [f for f in arquivos if _numero(f) >= desde]
    return arquivos


def detectar(pasta, desde=None, so_cor=False):
    """Devolve {nome_arquivo: (x,y,raio) ou None}.

    so_cor=True pula o filtro de movimento (MOG2) e usa só a cor. Util pra cameras onde a bola
    fica parada/lenta tempo demais (ex: vista de cima) e o MOG2 acaba absorvendo ela como fundo,
    gerando falso negativo mesmo com a bola bem visivel. So funciona bem em fundo simples/escuro
    onde a cor da bola nao se confunde com mais nada (sem mao/pano claro no quadro)."""
    arquivos = _frames_ordenados(pasta, desde)
    bg = None if so_cor else cv2.createBackgroundSubtractorMOG2(history=25, varThreshold=20, detectShadows=False)
    kernel = np.ones((3, 3), np.uint8)
    resultados = {}
    for i, f in enumerate(arquivos):
        img = cv2.imread(os.path.join(pasta, f))
        if img is None:
            continue
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, COR_MIN, COR_MAX)
        if not so_cor:
            mask_mov = bg.apply(img)
            if i < AQUECIMENTO:
                resultados[f] = None
                continue
            mask_mov = cv2.morphologyEx(mask_mov, cv2.MORPH_OPEN, kernel)
            mask_mov = cv2.dilate(mask_mov, kernel, iterations=1)
            mask = cv2.bitwise_and(mask_mov, mask)
        contornos, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        melhor, melhor_fill = None, 0
        for c in contornos:
            area = cv2.contourArea(c)
            if area < AREA_MIN or area > AREA_MAX:
                continue
            (x, y), r = cv2.minEnclosingCircle(c)
            fill = area / (math.pi * r * r) if r > 0 else 0
            if fill < FILL_MIN:
                continue
            if fill > melhor_fill:
                melhor, melhor_fill = (int(x), int(y), int(r)), fill
        resultados[f] = melhor
    return resultados


def gravar_labels(pasta, resultados):
    com_bola = 0
    for f, det in resultados.items():
        img_path = os.path.join(pasta, f)
        img = cv2.imread(img_path)
        h, w = img.shape[:2]
        txt = os.path.join(pasta, f.replace(".jpg", ".txt"))
        if det is None:
            with open(txt, "w") as fh:
                fh.write("")
            continue
        x, y, r = det
        xc, yc = min(max(x / w, 0), 1), min(max(y / h, 0), 1)
        bw, bh = min(max(2 * r / w, 0), 1), min(max(2 * r / h, 0), 1)
        with open(txt, "w") as fh:
            fh.write(f"0 {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}\n")
        com_bola += 1
    return com_bola


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", required=True, help="dataset/training/quadra/camera0 (ex.)")
    ap.add_argument("--desde", type=int, default=None, help="só rotula frame_NNNN >= este número")
    ap.add_argument("--so-cor", action="store_true",
                    help="pula o filtro de movimento, usa só a cor (câmeras onde a bola fica parada demais)")
    args = ap.parse_args()

    resultados = detectar(args.pasta, args.desde, args.so_cor)
    com_bola = gravar_labels(args.pasta, resultados)
    print(f"{args.pasta}: {com_bola}/{len(resultados)} com bola (por movimento)")
