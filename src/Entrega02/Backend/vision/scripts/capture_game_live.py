import argparse
import os
import re
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VISION_DIR = os.path.dirname(SCRIPT_DIR)
ROOT_DIR = os.path.dirname(VISION_DIR)
sys.path.insert(0, VISION_DIR)

import cv2

from camera_manager import abrir_captura, listar_cameras

WIDTH, HEIGHT, FPS = 1280, 720, 30
MAX_DISPLAY_WIDTH = 1500
WIN_NAME = "Captura ao vivo - Quadra"
DATASET_BASE = os.path.join(ROOT_DIR, "dataset")


def _abrir_e_configurar(cam_id):
    cap = abrir_captura(cam_id)
    if cap is None:
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    ok, _ = _ler_seguro(cap)
    if ok:
        return cap
    print(f"Câmera {cam_id}: não aceitou {WIDTH}x{HEIGHT}@{FPS}fps, reabrindo na resolução nativa")
    cap.release()
    return abrir_captura(cam_id)


def _ler_seguro(cap):
    try:
        return cap.read()
    except cv2.error as e:
        print(f"Aviso: erro ao ler frame ({e}); tentando continuar")
        return False, None


def _ajustar_para_tela(frame):
    if frame.shape[1] > MAX_DISPLAY_WIDTH:
        escala = MAX_DISPLAY_WIDTH / frame.shape[1]
        frame = cv2.resize(frame, (MAX_DISPLAY_WIDTH, int(frame.shape[0] * escala)))
    return frame


def _proximo_indice(pasta):
    if not os.path.isdir(pasta):
        return 1
    maior = 0
    for nome in os.listdir(pasta):
        m = re.match(r"frame_(\d+)\.jpg$", nome)
        if m:
            maior = max(maior, int(m.group(1)))
    return maior + 1


def capture_game_live(id0=0, id1=1, destino="training/quadra"):
    DATASET_DIR = os.path.join(DATASET_BASE, destino)
    pasta0 = os.path.join(DATASET_DIR, "camera0")
    pasta1 = os.path.join(DATASET_DIR, "camera1")
    os.makedirs(pasta0, exist_ok=True)
    os.makedirs(pasta1, exist_ok=True)

    cap0 = _abrir_e_configurar(id0)
    cap1 = _abrir_e_configurar(id1)
    if cap0 is None or cap1 is None:
        print(f"Erro ao abrir câmeras (id {id0} / id {id1})")
        if cap0:
            cap0.release()
        if cap1:
            cap1.release()
        print("Câmeras detectadas no sistema:")
        for cam_id, w, h in listar_cameras():
            print(f"  id {cam_id}: {w}x{h}")
        return

    cv2.namedWindow(WIN_NAME, cv2.WINDOW_NORMAL)
    cv2.moveWindow(WIN_NAME, 0, 0)

    indice = _proximo_indice(pasta0)
    if indice > 1:
        print(f"Retomando: já existem {indice - 1} frames salvos")

    capturando = False
    sessao_frames = 0
    jogada_frames = 0
    falhas_seguidas = 0
    tempos_frame = []

    print("ESPACO inicia | ESC pausa | R reseta contador da jogada | Q sai")

    try:
        while True:
            t0 = time.time()
            ok0, frame0 = _ler_seguro(cap0)
            ok1, frame1 = _ler_seguro(cap1)
            if not ok0 or not ok1:
                falhas_seguidas += 1
                if falhas_seguidas > 30:
                    print("Erro ao ler frame (repetido) — encerrando")
                    break
                cv2.waitKey(30)
                continue
            falhas_seguidas = 0

            if capturando:
                nome = f"frame_{indice:04d}.jpg"
                cv2.imwrite(os.path.join(pasta0, nome), frame0)
                cv2.imwrite(os.path.join(pasta1, nome), frame1)
                indice += 1
                sessao_frames += 1
                jogada_frames += 1

            tempos_frame.append(t0)
            tempos_frame = [t for t in tempos_frame if t0 - t < 1.0]
            fps_atual = len(tempos_frame)

            disp0, disp1 = frame0.copy(), frame1.copy()
            estado_cor = (0, 220, 0) if capturando else (0, 220, 220)
            estado_txt = "CAPTURANDO" if capturando else "PAUSA"
            for d in (disp0, disp1):
                cv2.putText(d, estado_txt, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, estado_cor, 2)
                cv2.putText(d, f"FPS: {fps_atual}", (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                cv2.putText(d, f"Sessao: {sessao_frames}  Jogada: {jogada_frames}", (10, 95),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(disp0, "CAMERA 0 (Overhead)", (10, 125), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(disp1, "CAMERA 1 (Lateral)", (10, 125), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            disp1_r = cv2.resize(disp1, (disp0.shape[1], disp0.shape[0]))
            combinado = cv2.hconcat([disp0, disp1_r])
            combinado = _ajustar_para_tela(combinado)
            cv2.imshow(WIN_NAME, combinado)

            tecla = cv2.waitKey(1) & 0xFF
            if tecla == ord('q'):
                break
            elif tecla == 32:  # ESPACO
                capturando = True
                print("Capturando...")
            elif tecla == 27:  # ESC
                capturando = False
                print(f"Pausado. {jogada_frames} frames nesta jogada.")
            elif tecla == ord('r'):
                jogada_frames = 0
                print("Jogada resetada (contador zerado, frames salvos continuam no disco).")
    finally:
        cap0.release()
        cap1.release()
        cv2.destroyAllWindows()

    print("--- Captura finalizada ---")
    print(f"Frames desta sessão: {sessao_frames}")
    print(f"Total salvo em: {DATASET_DIR}")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument("--cam0", type=int, default=0, help="ID da câmera overhead")
    ap.add_argument("--cam1", type=int, default=1, help="ID da câmera lateral")
    ap.add_argument("--destino", default="training/quadra",
                    help="'training/quadra' pra treino (padrão) ou 'validacao/quadra' pra validação")
    args = ap.parse_args()
    capture_game_live(args.cam0, args.cam1, args.destino)
