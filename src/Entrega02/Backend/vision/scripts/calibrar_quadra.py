"""Calibra uma camera pra quadra: voce clica 4 pontos cuja posicao real (cm) e conhecida, o script
calcula a transformacao imagem -> cm e salva. Depois disso, clicar em qualquer ponto mostra as coordenadas
reais dele (pra conferir se a calibracao esta boa).

Exemplo (cantos do gol, face de frente, origem no canto inferior esquerdo):
  python vision/scripts/calibrar_quadra.py --cam 1 --nome lateral --pontos "0,0;310,0;310,210;0,210"

Controles: clique esquerdo = marca ponto | R = recomecar | ENTER = salvar (com 4 pontos) | Q = sair
"""
import argparse
import json
import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VISION_DIR = os.path.dirname(SCRIPT_DIR)
ROOT_DIR = os.path.dirname(VISION_DIR)
sys.path.insert(0, VISION_DIR)

import cv2
import numpy as np

from camera_manager import abrir_captura

WIDTH, HEIGHT, FPS = 1280, 720, 30
CALIB_JSON = os.path.join(ROOT_DIR, "vision", "calibracao_quadra.json")
PASTA_PRINTS = os.path.join(ROOT_DIR, "dataset", "calibracao")


def _ler_seguro(cap):
    try:
        return cap.read()
    except cv2.error:
        return False, None


def _abrir(cam_id):
    cap = abrir_captura(cam_id)
    if cap is None:
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    ok, _ = _ler_seguro(cap)
    if ok:
        return cap
    # algumas webcams nao aceitam 1280x720 pelo backend MSMF e travam o read: reabre na resolucao nativa
    print(f"Câmera {cam_id}: não aceitou {WIDTH}x{HEIGHT}, reabrindo na resolução nativa")
    cap.release()
    return abrir_captura(cam_id)


def _frame_estavel(cap, descartar=15):
    frame = None
    for _ in range(descartar):
        ok, f = _ler_seguro(cap)
        if ok:
            frame = f
        time.sleep(0.02)
    return frame


def _ler_json():
    if os.path.isfile(CALIB_JSON):
        with open(CALIB_JSON, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _salvar(nome, pontos_img, pontos_cm, frame):
    pontos_img = np.array(pontos_img, dtype=np.float32)
    pontos_cm = np.array(pontos_cm, dtype=np.float32)
    H = cv2.getPerspectiveTransform(pontos_img, pontos_cm)

    dados = _ler_json()
    dados[nome] = {
        "H": H.tolist(),
        "pontos_imagem": pontos_img.tolist(),
        "pontos_cm": pontos_cm.tolist(),
        "resolucao": [frame.shape[1], frame.shape[0]],
    }
    os.makedirs(os.path.dirname(CALIB_JSON), exist_ok=True)
    with open(CALIB_JSON, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=2)

    os.makedirs(PASTA_PRINTS, exist_ok=True)
    print_img = frame.copy()
    _desenhar_pontos(print_img, pontos_img.tolist(), pontos_cm.tolist())
    caminho = os.path.join(PASTA_PRINTS, f"{nome}_calibracao.jpg")
    cv2.imwrite(caminho, print_img)
    print(f"[calibracao] '{nome}' salva em {CALIB_JSON}")
    print(f"[calibracao] print com os cliques: {caminho}")
    return H


def _desenhar_pontos(img, pontos_img, pontos_cm):
    for i, ((x, y), (cx, cy)) in enumerate(zip(pontos_img, pontos_cm), start=1):
        cv2.circle(img, (int(x), int(y)), 8, (0, 0, 255), -1)
        cv2.putText(img, f"{i}: ({cx:.0f},{cy:.0f})cm", (int(x) + 12, int(y) - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)


def calibrar(cam_id, nome, pontos_cm_str):
    pontos_cm = [tuple(float(v) for v in p.split(",")) for p in pontos_cm_str.split(";")]
    if len(pontos_cm) != 4:
        print("Informe exatamente 4 pontos em --pontos (ex.: \"0,0;310,0;310,210;0,210\").")
        return

    cap = _abrir(cam_id)
    if cap is None:
        print(f"Câmera {cam_id} não abriu.")
        return
    frame_base = _frame_estavel(cap)
    if frame_base is None:
        print("Câmera abriu mas não entregou imagem.")
        cap.release()
        return
    print(f"Resolução: {frame_base.shape[1]}x{frame_base.shape[0]}")

    marcados = []
    estado = {"H": None}
    janela = f"Calibracao - {nome}"
    cv2.namedWindow(janela, cv2.WINDOW_NORMAL)
    cv2.moveWindow(janela, 0, 0)

    def clique(evento, x, y, flags, param):
        if evento != cv2.EVENT_LBUTTONDOWN:
            return
        if estado["H"] is not None:
            ponto = np.array([[[x, y]]], dtype=np.float32)
            cm = cv2.perspectiveTransform(ponto, estado["H"])[0][0]
            print(f"pixel ({x},{y}) = {cm[0]:.1f} cm (horizontal) x {cm[1]:.1f} cm (vertical)")
        elif len(marcados) < 4:
            marcados.append((x, y))
            print(f"ponto {len(marcados)} marcado: pixel ({x},{y}) = cm {pontos_cm[len(marcados) - 1]}")
    cv2.setMouseCallback(janela, clique)

    print("Clique nos 4 pontos na ordem: " + " -> ".join(
        f"{i}:({x:.0f},{y:.0f})cm" for i, (x, y) in enumerate(pontos_cm, start=1)))
    print("R recomeça | ENTER salva | Q sai")

    try:
        while True:
            ok, frame = _ler_seguro(cap)
            if not ok:
                frame = frame_base
            tela = frame.copy()
            _desenhar_pontos(tela, marcados, pontos_cm[:len(marcados)])
            if estado["H"] is not None:
                cv2.putText(tela, "CALIBRADO: clique em qualquer ponto pra ver cm", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            else:
                proximo = pontos_cm[len(marcados)] if len(marcados) < 4 else "ENTER"
                cv2.putText(tela, f"Pontos: {len(marcados)}/4  (proximo: {proximo})",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.imshow(janela, tela)

            tecla = cv2.waitKey(20) & 0xFF
            if tecla == ord('q'):
                break
            elif tecla == ord('r'):
                marcados.clear()
                estado["H"] = None
                print("recomeçando")
            elif tecla in (13, 10) and len(marcados) == 4 and estado["H"] is None:
                estado["H"] = _salvar(nome, marcados, pontos_cm, frame)
                print("Agora clique em qualquer ponto da imagem pra ver as coordenadas reais (cm).")
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cam", type=int, required=True, help="ID da câmera")
    ap.add_argument("--nome", required=True, help="nome da câmera (ex.: overhead ou lateral)")
    ap.add_argument("--pontos", required=True, help="4 pontos reais em cm, ex.: \"0,0;310,0;310,210;0,210\"")
    args = ap.parse_args()
    calibrar(args.cam, args.nome, args.pontos)
