import argparse
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VISION_DIR = os.path.dirname(SCRIPT_DIR)
ROOT_DIR = os.path.dirname(VISION_DIR)
sys.path.insert(0, VISION_DIR)

import cv2

from camera_manager import abrir_captura, listar_cameras
from ball_detector import BallDetector

# NOTA: o prompt original não previa uma etapa de rotulagem, mas o YOLO precisa de um .txt (formato
# YOLO: classe x_centro y_centro largura altura, normalizados) por imagem para aprender algo — sem
# isso train_yolo.py rodaria sem nenhum exemplo válido. Aqui cada frame é rotulado automaticamente
# com o detector de cor já validado no projeto (vision/ball_detector.py). Frame sem bola detectada
# -> .txt vazio (frame de fundo, sem objeto), que o YOLO também usa no treino.

WIDTH, HEIGHT, FPS = 1280, 720, 30
DATASET_DIR = os.path.join(ROOT_DIR, "dataset", "training")
META_ESTATICOS = 100
META_SEQUENCIAS = 20
FRAMES_POR_SEQUENCIA = 10
MAX_DISPLAY_WIDTH = 1500   # 2 cameras 1280px lado a lado = 2560px: maior que a tela, janela fica cortada
WIN_NAME = "Captura de Dataset"


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


def _linha_yolo(frame, detector):
    det = detector.detect_ball_camera1(frame)  # mesma detecção estrita serve para qualquer câmera
    if det is None:
        return ""
    h, w = frame.shape[:2]
    x, y, r = det
    xc = min(max(x / w, 0.0), 1.0)
    yc = min(max(y / h, 0.0), 1.0)
    bw = min(max((2 * r) / w, 0.0), 1.0)
    bh = min(max((2 * r) / h, 0.0), 1.0)
    return f"0 {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}\n"


def _salvar(pasta, nome, frame, detector):
    cv2.imwrite(os.path.join(pasta, f"{nome}.jpg"), frame)
    with open(os.path.join(pasta, f"{nome}.txt"), "w") as f:
        f.write(_linha_yolo(frame, detector))


def _contar_existentes(pasta):
    """Maior índice já salvo em `pasta`, para sessões de captura seguintes CONTINUAREM a numeração
    em vez de sobrescrever static_0001.jpg / seq_0001_*.jpg de uma sessão anterior."""
    estaticos = sequencias = 0
    if not os.path.isdir(pasta):
        return 0, 0
    for nome in os.listdir(pasta):
        m = re.match(r"static_(\d+)\.jpg$", nome)
        if m:
            estaticos = max(estaticos, int(m.group(1)))
            continue
        m = re.match(r"seq_(\d+)_\d+\.jpg$", nome)
        if m:
            sequencias = max(sequencias, int(m.group(1)))
    return estaticos, sequencias


def capture_dataset(id0=0, id1=1):
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
        print("Rode de novo com, por exemplo: python capture_dataset.py --cam0 1 --cam1 2")
        return

    detector = BallDetector()
    estaticos, sequencias = _contar_existentes(pasta0)
    if estaticos or sequencias:
        print(f"Retomando sessão anterior: {estaticos} estáticos, {sequencias} sequências já salvos")

    cv2.namedWindow(WIN_NAME, cv2.WINDOW_NORMAL)
    cv2.moveWindow(WIN_NAME, 0, 0)   # força abrir no canto superior esquerdo, nunca fora da tela

    falhas_seguidas = 0
    try:
        while True:
            ok0, frame0 = _ler_seguro(cap0)
            ok1, frame1 = _ler_seguro(cap1)
            if not ok0 or not ok1:
                falhas_seguidas += 1
                if falhas_seguidas > 30:   # câmera realmente caiu, não é só um frame perdido
                    print("Erro ao ler frame (repetido) — encerrando")
                    break
                cv2.waitKey(30)
                continue
            falhas_seguidas = 0

            disp0, disp1 = frame0.copy(), frame1.copy()
            cv2.putText(disp0, f"CAMERA {id0} (Overhead)", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(disp1, f"CAMERA {id1} (Lateral)", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            disp1_r = cv2.resize(disp1, (disp0.shape[1], disp0.shape[0]))
            combinado = cv2.hconcat([disp0, disp1_r])
            combinado = _ajustar_para_tela(combinado)
            cv2.putText(combinado, f"Estaticos: {estaticos} | Sequencias: {sequencias}",
                        (10, combinado.shape[0] - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.imshow(WIN_NAME, combinado)

            tecla = cv2.waitKey(1) & 0xFF
            if tecla == ord('q'):
                break
            elif tecla == ord(' '):
                estaticos += 1
                nome = f"static_{estaticos:04d}"
                _salvar(pasta0, nome, frame0, detector)
                _salvar(pasta1, nome, frame1, detector)
                print(f"Estático {estaticos} capturado")
            elif tecla == ord('r'):
                sequencias += 1
                for i in range(FRAMES_POR_SEQUENCIA):
                    ok0, frame0 = _ler_seguro(cap0)
                    ok1, frame1 = _ler_seguro(cap1)
                    if not ok0 or not ok1:
                        break
                    nome = f"seq_{sequencias:04d}_{i:02d}"
                    _salvar(pasta0, nome, frame0, detector)
                    _salvar(pasta1, nome, frame1, detector)
                    aviso = _ajustar_para_tela(frame0.copy())
                    cv2.putText(aviso, f"Sequencia {sequencias} - {i + 1}/{FRAMES_POR_SEQUENCIA}",
                                (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    cv2.imshow(WIN_NAME, aviso)
                    cv2.waitKey(1)
                print(f"Sequência {sequencias} capturada ({FRAMES_POR_SEQUENCIA} frames)")
    finally:
        cap0.release()
        cap1.release()
        cv2.destroyAllWindows()

    total = estaticos + sequencias * FRAMES_POR_SEQUENCIA
    print("--- Captura finalizada ---")
    print(f"Total de frames: {total}")
    print(f"Estáticos: {estaticos} (meta: {META_ESTATICOS})")
    print(f"Sequências: {sequencias} (meta: {META_SEQUENCIAS})")
    print(f"Salvos em: {DATASET_DIR}")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument("--cam0", type=int, default=0, help="ID da câmera overhead (padrão 0)")
    ap.add_argument("--cam1", type=int, default=1, help="ID da câmera lateral (padrão 1)")
    args = ap.parse_args()
    capture_dataset(args.cam0, args.cam1)
