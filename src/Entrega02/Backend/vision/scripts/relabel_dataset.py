"""Re-rotula .jpg ja capturados em dataset/training/cameraN/ com o BallDetector atual (config.py e
ball_detector.py corrigidos). Nao recaptura nada -- so regrava os .txt YOLO por cima dos antigos,
gerados quando o detector ainda nao enxergava a bola direito."""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VISION_DIR = os.path.dirname(SCRIPT_DIR)
ROOT_DIR = os.path.dirname(VISION_DIR)
sys.path.insert(0, VISION_DIR)

import cv2
from ball_detector import BallDetector


def linha_yolo(frame, detector):
    det = detector.detect_ball_camera1(frame)
    if det is None:
        return ""
    h, w = frame.shape[:2]
    x, y, r = det
    xc = min(max(x / w, 0.0), 1.0)
    yc = min(max(y / h, 0.0), 1.0)
    bw = min(max((2 * r) / w, 0.0), 1.0)
    bh = min(max((2 * r) / h, 0.0), 1.0)
    return f"0 {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}\n"


def relabel(pasta):
    detector = BallDetector()
    arquivos = sorted(f for f in os.listdir(pasta) if f.endswith(".jpg"))
    com_bola = 0
    for f in arquivos:
        img = cv2.imread(os.path.join(pasta, f))
        if img is None:
            continue
        linha = linha_yolo(img, detector)
        if linha:
            com_bola += 1
        with open(os.path.join(pasta, f.replace(".jpg", ".txt")), "w") as fh:
            fh.write(linha)
    print(f"{pasta}: {com_bola}/{len(arquivos)} com bola detectada ({100*com_bola/len(arquivos):.1f}%)")


if __name__ == "__main__":
    for cam in ("camera0", "camera1"):
        relabel(os.path.join(ROOT_DIR, "dataset", "training", cam))
