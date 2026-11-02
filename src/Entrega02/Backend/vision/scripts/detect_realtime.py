import argparse
import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VISION_DIR = os.path.dirname(SCRIPT_DIR)
ROOT_DIR = os.path.dirname(VISION_DIR)
sys.path.insert(0, VISION_DIR)

import cv2
import requests

from camera_manager import abrir_captura
from ball_detector import BallDetector

WIDTH, HEIGHT, FPS = 1280, 720, 30
MODEL_PATH = os.path.join(ROOT_DIR, "runs", "detect", "ball_detector_v1", "weights", "best.pt")
# 127.0.0.1: este script roda no mesmo notebook que o Flask (não no celular), então não depende do
# IP da rede Wi-Fi (que muda a cada rede, como já vimos com o app). Use --flask-url para outro host.
FLASK_URL_PADRAO = "http://127.0.0.1:5000/acerto"
FLASK_TIMEOUT = 0.3
# a bolinha some do quadro em bem menos de 1s: sem isto, ficaria enviando 30 posts/s de acerto
# pro Flask enquanto ela estiver parada visível, inundando o contador de pontuação.
ENVIO_COOLDOWN_S = 1.0
MAX_DISPLAY_WIDTH = 1500   # 2 cameras 1280px lado a lado = 2560px: maior que a tela, janela fica cortada
WIN_NAME = "Deteccao em Tempo Real"


def _abrir_e_configurar(cam_id):
    """
    Abre a câmera e tenta 1280x720@30fps. Algumas webcams (via backend MSMF do Windows) não aceitam
    bem essa reconfiguração e deixam o stream num estado inválido: o próximo read() trava com
    'cv2.error: ... Mat::Mat ... _step >= minstep' em vez de simplesmente falhar. Se acontecer,
    fecha e reabre a câmera limpa, sem forçar resolução (usa o padrão nativo dela).
    """
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
    """cap.read() sem deixar um erro do driver (MSMF/DSHOW) derrubar o script inteiro."""
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


def _enviar_flask(flask_url, camera, x, y, confianca):
    try:
        requests.post(flask_url, json={
            "source": "vision", "camera": camera,
            "x": x, "y": y, "confidence": confianca,
        }, timeout=FLASK_TIMEOUT)
    except requests.exceptions.RequestException:
        pass  # Flask fora do ar: ignora e continua


def _processar(frame, modelo, camera_id, ultimo_envio, flask_url):
    resultados = modelo(frame, verbose=False)[0]
    if len(resultados.boxes) == 0:
        return 0
    caixa = resultados.boxes[int(resultados.boxes.conf.argmax())]
    confianca = float(caixa.conf[0])
    if confianca <= 0:
        return 0

    x1, y1, x2, y2 = map(int, caixa.xyxy[0])
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.circle(frame, (cx, cy), 5, (0, 255, 0), -1)
    cv2.putText(frame, f"Bolinha! Conf: {confianca:.2f}", (x1, max(20, y1 - 10)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    agora = time.time()
    if agora - ultimo_envio[camera_id] > ENVIO_COOLDOWN_S:
        _enviar_flask(flask_url, camera_id, cx, cy, confianca)
        ultimo_envio[camera_id] = agora
    return 1


def _processar_cor(frame, detector, camera_id, ultimo_envio, flask_url):
    """Mesma coisa que _processar, mas com o detector de cor (ball_detector.py) em vez do YOLO —
    usado como pré-visualização antes do modelo treinado existir. Sem "confiança" real (é
    tudo-ou-nada), então mostra 'OK' no lugar do percentual do YOLO."""
    det = detector.detect_ball_camera1(frame)   # mesma detecção estrita serve para qualquer câmera
    if det is None:
        return 0
    x, y, r = det
    cv2.circle(frame, (x, y), r, (0, 255, 0), 2)
    cv2.circle(frame, (x, y), 5, (0, 255, 0), -1)
    cv2.putText(frame, "Bolinha! (detector de cor)", (max(0, x - r), max(20, y - r - 10)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    agora = time.time()
    if agora - ultimo_envio[camera_id] > ENVIO_COOLDOWN_S:
        _enviar_flask(flask_url, camera_id, x, y, 1.0)
        ultimo_envio[camera_id] = agora
    return 1


def detect_realtime(flask_url=FLASK_URL_PADRAO, id0=0, id1=1):
    usar_yolo = os.path.isfile(MODEL_PATH)
    if usar_yolo:
        from ultralytics import YOLO
        modelo = YOLO(MODEL_PATH)
    else:
        print("Modelo YOLO ainda não treinado (rode train_yolo.py depois) — usando o detector de "
              "cor (ball_detector.py) como pré-visualização por enquanto.")
        modelo = BallDetector()

    cap0 = _abrir_e_configurar(id0)
    cap1 = _abrir_e_configurar(id1)
    if cap0 is None or cap1 is None:
        print(f"Erro ao abrir câmeras (id {id0} / id {id1})")
        if cap0:
            cap0.release()
        if cap1:
            cap1.release()
        return

    cv2.namedWindow(WIN_NAME, cv2.WINDOW_NORMAL)
    cv2.moveWindow(WIN_NAME, 0, 0)   # força abrir no canto superior esquerdo, nunca fora da tela

    frames_processados = 0
    deteccoes_totais = 0
    falhas_seguidas = 0
    ultimo_envio = {id0: 0.0, id1: 0.0}

    try:
        while True:
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
            frames_processados += 1

            funcao = _processar if usar_yolo else _processar_cor
            deteccoes_totais += funcao(frame0, modelo, id0, ultimo_envio, flask_url)
            deteccoes_totais += funcao(frame1, modelo, id1, ultimo_envio, flask_url)

            cv2.putText(frame0, f"CAMERA {id0} (Overhead)", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(frame1, f"CAMERA {id1} (Lateral)", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            frame1_r = cv2.resize(frame1, (frame0.shape[1], frame0.shape[0]))
            combinado = cv2.hconcat([frame0, frame1_r])
            combinado = _ajustar_para_tela(combinado)
            cv2.imshow(WIN_NAME, combinado)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        cap0.release()
        cap1.release()
        cv2.destroyAllWindows()

    print("Detecção finalizada")
    print(f"Frames processados: {frames_processados}")
    print(f"Detecções totais: {deteccoes_totais}")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument("--flask-url", default=FLASK_URL_PADRAO,
                     help="URL do /acerto. Padrão: localhost (script roda no mesmo PC do Flask).")
    ap.add_argument("--cam0", type=int, default=0, help="ID da câmera overhead (padrão 0)")
    ap.add_argument("--cam1", type=int, default=1, help="ID da câmera lateral (padrão 1)")
    args = ap.parse_args()
    detect_realtime(args.flask_url, args.cam0, args.cam1)
