import cv2
import numpy as np

from config import (CAM1_X_RANGE, CAM1_Z_RANGE, CAM2_Z_RANGE, CAM2_Y_RANGE,
                    SAVE_CALIBRATION, CALIBRATION_FILE_1, CALIBRATION_FILE_2)


def _cantos_imagem(frame):
    """Cantos do frame: topo-esq, topo-dir, base-dir, base-esq (pixels)."""
    h, w = frame.shape[:2]
    return np.float32([[0, 0], [w, 0], [w, h], [0, h]])


def _aplicar(matriz, x, y):
    ponto = np.array([[[x, y]]], dtype=np.float32)
    r = cv2.perspectiveTransform(ponto, matriz)
    return float(r[0][0][0]), float(r[0][0][1])


class CameraCalibration:
    """
    Homografia pixel <-> mundo para cada câmera (plano visto por ela).

    Calibração padrão: os 4 cantos do frame são mapeados para o retângulo do mundo
    definido em config (CAM*_..._RANGE). Só é exata se a câmera enquadrar exatamente
    essa região de frente; para maior precisão, troque os pontos por marcações medidas.

    Câmera 1 (cima):  pixel -> (X, Z)
    Câmera 2 (lado):  pixel -> (Z, Y)
    """

    def __init__(self):
        self.camera1_matrix = None
        self.camera2_matrix = None
        self.camera1_inverted = None
        self.camera2_inverted = None

    def _definir(self, n, matriz):
        inversa = np.linalg.inv(matriz)
        if n == 1:
            self.camera1_matrix, self.camera1_inverted = matriz, inversa
        else:
            self.camera2_matrix, self.camera2_inverted = matriz, inversa

    def calibrate_camera1(self, frame, salvar=SAVE_CALIBRATION):
        x0, x1 = CAM1_X_RANGE
        z_topo, z_base = CAM1_Z_RANGE      # topo da imagem = fundo do gol
        mundo = np.float32([[x0, z_topo], [x1, z_topo], [x1, z_base], [x0, z_base]])
        matriz = cv2.getPerspectiveTransform(_cantos_imagem(frame), mundo)
        self._definir(1, matriz)
        if salvar:
            np.save(CALIBRATION_FILE_1, matriz)
        print("[Calibration] ✅ Câmera 1 (cima) calibrada")
        return matriz

    def calibrate_camera2(self, frame, salvar=SAVE_CALIBRATION):
        z_esq, z_dir = CAM2_Z_RANGE        # esquerda da imagem = fundo do gol
        y_base, y_topo = CAM2_Y_RANGE      # base da imagem = chão (y do pixel cresce para baixo)
        mundo = np.float32([[z_esq, y_topo], [z_dir, y_topo], [z_dir, y_base], [z_esq, y_base]])
        matriz = cv2.getPerspectiveTransform(_cantos_imagem(frame), mundo)
        self._definir(2, matriz)
        if salvar:
            np.save(CALIBRATION_FILE_2, matriz)
        print("[Calibration] ✅ Câmera 2 (lado) calibrada")
        return matriz

    # --- pixel -> mundo -------------------------------------------------------
    def pixel_to_world_camera1(self, x_px, y_px):
        """Pixel da câmera 1 -> (X, Z) em metros."""
        if self.camera1_matrix is None:
            return None
        return _aplicar(self.camera1_matrix, x_px, y_px)

    def pixel_to_world_camera2(self, x_px, y_px):
        """Pixel da câmera 2 -> (Z, Y) em metros."""
        if self.camera2_matrix is None:
            return None
        return _aplicar(self.camera2_matrix, x_px, y_px)

    # --- mundo -> pixel (para desenhar o alvo nas janelas de debug) --------------
    def world_to_pixel_camera1(self, x, z):
        if self.camera1_inverted is None:
            return None
        return _aplicar(self.camera1_inverted, x, z)

    def world_to_pixel_camera2(self, z, y):
        if self.camera2_inverted is None:
            return None
        return _aplicar(self.camera2_inverted, z, y)

    def load_calibration(self):
        """Carrega a calibração salva (vale só se a resolução da câmera não mudou)."""
        try:
            self._definir(1, np.load(CALIBRATION_FILE_1))
            self._definir(2, np.load(CALIBRATION_FILE_2))
            print("[Calibration] ✅ Calibração carregada de arquivo")
            return True
        except (OSError, ValueError):
            print("[Calibration] ⚠️ Calibração salva não encontrada; será feita agora")
            return False
