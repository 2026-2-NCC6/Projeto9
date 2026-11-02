"""Calibra a altura na camera lateral usando o proprio poste do gol (no plano do gol).
Voce clica no pe do poste (0 cm) e no topo do poste (210 cm). Depois, clicar em qualquer ponto mostra
a altura em cm daquele ponto (valido pra bolinha quando ela esta no plano do gol).

  python vision/scripts/calibrar_altura_poste.py --cam 1 --altura-topo 210

Controles: 2 cliques (1: pe do poste, 2: topo do poste) | R recomeca | ENTER salva | Q sai
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

from camera_manager import abrir_captura

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
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    ok, _ = _ler_seguro(cap)
    if ok:
        return cap
    print("Câmera não aceitou 1280x720, reabrindo na resolução nativa")
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


def _converter(y, y_base, y_topo, altura_topo):
    return (y_base - y) / (y_base - y_topo) * altura_topo


def calibrar(cam_id, altura_topo):
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
    janela = "Calibracao altura - lateral"
    cv2.namedWindow(janela, cv2.WINDOW_NORMAL)
    cv2.moveWindow(janela, 0, 0)

    def clique(evento, x, y, flags, param):
        if evento != cv2.EVENT_LBUTTONDOWN:
            return
        if len(marcados) < 2:
            marcados.append((x, y))
            nome = "pé do poste (0 cm)" if len(marcados) == 1 else f"topo do poste ({altura_topo:.0f} cm)"
            print(f"ponto {len(marcados)} marcado: {nome} = pixel ({x},{y})")
        elif len(marcados) == 2 and estado.get("ok"):
            altura = _converter(y, estado["y_base"], estado["y_topo"], altura_topo)
            print(f"pixel ({x},{y}) = altura {altura:.1f} cm")
    estado = {}
    cv2.setMouseCallback(janela, clique)

    print("Clique: 1) pé do poste  2) topo do poste  | ENTER salva | R recomeça | Q sai")
    try:
        while True:
            ok, frame = _ler_seguro(cap)
            if not ok:
                frame = frame_base
            tela = frame.copy()
            for i, (x, y) in enumerate(marcados, start=1):
                cv2.circle(tela, (int(x), int(y)), 8, (0, 0, 255), -1)
                cv2.putText(tela, f"{i}", (int(x) + 10, int(y) - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            if "ok" in estado:
                cv2.putText(tela, "CALIBRADO: clique em qualquer ponto pra ver altura", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            else:
                cv2.putText(tela, f"Pontos: {len(marcados)}/2", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.imshow(janela, tela)

            tecla = cv2.waitKey(20) & 0xFF
            if tecla == ord('q'):
                break
            elif tecla == ord('r'):
                marcados.clear()
                estado.clear()
                print("recomeçando")
            elif tecla in (13, 10) and len(marcados) == 2 and "ok" not in estado:
                y_base = max(marcados[0][1], marcados[1][1])   # pé = ponto mais baixo na imagem
                y_topo = min(marcados[0][1], marcados[1][1])   # topo = ponto mais alto
                dados = {}
                if os.path.isfile(CALIB_JSON):
                    with open(CALIB_JSON, encoding="utf-8") as f:
                        dados = json.load(f)
                dados["lateral_altura"] = {
                    "tipo": "altura_poste",
                    "y_base": y_base,
                    "y_topo": y_topo,
                    "altura_topo_cm": altura_topo,
                    "resolucao": [frame_base.shape[1], frame_base.shape[0]],
                }
                os.makedirs(os.path.dirname(CALIB_JSON), exist_ok=True)
                with open(CALIB_JSON, "w", encoding="utf-8") as f:
                    json.dump(dados, f, indent=2)
                estado.update({"ok": True, "y_base": y_base, "y_topo": y_topo})

                os.makedirs(PASTA_PRINTS, exist_ok=True)
                print_img = frame.copy()
                cv2.line(print_img, (marcados[0][0], marcados[0][1]), (marcados[1][0], marcados[1][1]), (0, 0, 255), 2)
                caminho = os.path.join(PASTA_PRINTS, "lateral_altura_calibracao.jpg")
                cv2.imwrite(caminho, print_img)
                print(f"[calibracao] altura salva em {CALIB_JSON}")
                print(f"[calibracao] print: {caminho}")
                print("Agora clique em qualquer ponto pra ver a altura em cm.")
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cam", type=int, required=True, help="ID da câmera lateral")
    ap.add_argument("--altura-topo", type=float, default=210.0, help="altura do topo do poste em cm")
    args = ap.parse_args()
    calibrar(args.cam, args.altura_topo)
