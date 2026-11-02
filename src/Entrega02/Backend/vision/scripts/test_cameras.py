import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VISION_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, VISION_DIR)

import cv2

from camera_manager import abrir_captura, listar_cameras   # backend DirectShow no Windows: mais confiável que cv2.VideoCapture(id) puro

WIDTH, HEIGHT, FPS = 1280, 720, 30
MAX_DISPLAY_WIDTH = 1500   # 2 cameras 1280px lado a lado = 2560px: maior que a tela, janela fica cortada
WIN_NAME = "Teste de Cameras"


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


def test_cameras(id0=0, id1=1):
    cap0 = _abrir_e_configurar(id0)
    cap1 = _abrir_e_configurar(id1)
    if cap0 is None or cap1 is None:
        print(f"Erro ao abrir câmeras (id {id0} / id {id1})")
        if cap0:
            cap0.release()
        if cap1:
            cap1.release()
        # com webcam do notebook + 2 USB, os índices 0/1 podem não ser as USB certas -> lista o que existe
        print("Câmeras detectadas no sistema:")
        for cam_id, w, h in listar_cameras():
            print(f"  id {cam_id}: {w}x{h}")
        print("Rode de novo com, por exemplo: python test_cameras.py --cam0 1 --cam1 2")
        return

    w0, h0 = int(cap0.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap0.get(cv2.CAP_PROP_FRAME_HEIGHT))
    w1, h1 = int(cap1.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap1.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Camera {id0} (Overhead): {w0}x{h0}")
    print(f"Camera {id1} (Lateral): {w1}x{h1}")

    cv2.namedWindow(WIN_NAME, cv2.WINDOW_NORMAL)
    cv2.moveWindow(WIN_NAME, 0, 0)   # força abrir no canto superior esquerdo, nunca fora da tela

    total_frames = 0
    falhas_seguidas = 0
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
            total_frames += 1

            cv2.putText(frame0, f"CAMERA {id0} (Overhead - 80cm, FOV 36x60cm)", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(frame1, f"CAMERA {id1} (Lateral - 50cm, FOV 90x50cm)", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            frame1_r = cv2.resize(frame1, (frame0.shape[1], frame0.shape[0]))
            combinado = cv2.hconcat([frame0, frame1_r])
            combinado = _ajustar_para_tela(combinado)
            cv2.putText(combinado, f"Frames: {total_frames}", (10, combinado.shape[0] - 15),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.imshow(WIN_NAME, combinado)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        cap0.release()
        cap1.release()
        cv2.destroyAllWindows()

    print(f"Total de frames capturados: {total_frames}")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument("--cam0", type=int, default=0, help="ID da câmera overhead (padrão 0)")
    ap.add_argument("--cam1", type=int, default=1, help="ID da câmera lateral (padrão 1)")
    args = ap.parse_args()
    test_cameras(args.cam0, args.cam1)
