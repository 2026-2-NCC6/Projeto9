import os
import threading
import time

import cv2

from config import (CAMERA1_ID, CAMERA2_ID, CAMERA_WIDTH, CAMERA_HEIGHT, TARGET_FPS)


def abrir_captura(camera_id):
    """
    Abre a câmera e confirma que ela entrega imagem. No Windows o backend padrão (MSMF) costuma
    demorar para abrir e limitar o FPS; tenta DirectShow primeiro. Retorna VideoCapture ou None.
    """
    backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY] if os.name == "nt" else [cv2.CAP_ANY]
    for backend in backends:
        cap = cv2.VideoCapture(camera_id, backend)
        if cap.isOpened():
            ok, _ = cap.read()
            if ok:
                return cap
        cap.release()
    return None


def listar_cameras(max_id=4):
    """[(id, largura, altura)] das câmeras que abrem. Acende a luz de cada câmera por um instante."""
    achadas = []
    for i in range(max_id + 1):
        cap = abrir_captura(i)
        if cap is not None:
            achadas.append((i, int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))))
            cap.release()
    return achadas


class CameraThread:
    """Lê uma câmera em loop e guarda sempre o frame MAIS RECENTE."""

    def __init__(self, camera_id, nome, largura=CAMERA_WIDTH, altura=CAMERA_HEIGHT, fps=TARGET_FPS, exposicao=None):
        self.camera_id = camera_id
        self.nome = nome
        self.largura, self.altura, self.fps = largura, altura, fps
        self.exposicao = exposicao   # None = automática; número (ex.: -5) = manual, em log2 de segundos
        self.cap = None
        self._frame = None
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

    def abrir(self):
        self.cap = abrir_captura(self.camera_id)
        if self.cap is None:
            return False
        # MJPG antes da resolução: muitas webcams só dão 30 FPS em 720p comprimindo em MJPG
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.largura)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.altura)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if self.exposicao is not None:
            self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)   # 0.25 = manual no DirectShow
            self.cap.set(cv2.CAP_PROP_EXPOSURE, self.exposicao)
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def resolucao(self):
        """(largura, altura) que a câmera realmente entregou (pode diferir do pedido)."""
        return int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    def _loop(self):
        while self._running:
            ok, frame = self.cap.read()
            if ok:
                with self._lock:
                    self._frame = frame  # sobrescreve: o frame antigo é descartado
            else:
                time.sleep(0.01)  # evita loop quente se a câmera falhar

    def ultimo_frame(self):
        with self._lock:
            return self._frame

    def fechar(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
        if self.cap:
            self.cap.release()


_CameraThread = CameraThread  # nome antigo


class CameraManager:
    """Gerencia as 2 câmeras USB, cada uma em sua thread."""

    def __init__(self):
        self.cam1 = CameraThread(CAMERA1_ID, "câmera 1 (cima)")
        self.cam2 = CameraThread(CAMERA2_ID, "câmera 2 (lado)")

    def init_cameras(self):
        """Abre as duas câmeras. Só retorna True se AMBAS abrirem."""
        falhas = [c.nome + f" (id {c.camera_id})" for c in (self.cam1, self.cam2) if not c.abrir()]
        if falhas:
            print(f"[CameraManager] ❌ Não abriu: {', '.join(falhas)}")
            self.release()
            return False
        print("[CameraManager] ✅ Ambas câmeras inicializadas")
        return True

    def get_frames(self):
        """(frame_cima, frame_lado): o mais recente de cada câmera, ou None se ainda não chegou."""
        return self.cam1.ultimo_frame(), self.cam2.ultimo_frame()

    def release(self):
        self.cam1.fechar()
        self.cam2.fechar()
        print("[CameraManager] 🛑 Câmeras liberadas")
