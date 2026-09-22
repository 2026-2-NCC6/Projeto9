import argparse
import math
import os
import time
from collections import deque

import cv2

from ball_detector import BallDetector
from camera_calibration import CameraCalibration
from camera_manager import CameraManager, CameraThread, listar_cameras
from config import (DEBUG, TARGET_FPS, CAMERA1_ID, LASER_X, LASER_Y, LASER_Z, LOG_INTERVAL_S,
                    HIT_TOLERANCE, HIT_DEBOUNCE_S, BASE_DIR,
                    CAM1_X_RANGE, CAM1_Z_RANGE, CAM2_Z_RANGE, CAM2_Y_RANGE)
from flask_client import FlaskClient
from hit_detector import HitDetector

JANELA_TESTE = "Camera de teste (1 camera)"
JANELA_HSV = "HSV"
JANELA_MASCARA = "Mascara"


class SmartTennisVision:
    """
    Sistema de visão.
      modo normal (2 câmeras): bola -> posição 3D -> acerto -> POST /acerto no Flask (+ heartbeat)
      modo teste  (1 câmera) : bola -> posição (X, Z) -> "acerto simulado". NÃO fala com o Flask,
                               para o app não achar que a visão está ativa.
    """

    def __init__(self, test_mode=False, debug=None, camera_id=CAMERA1_ID, fps_limit=TARGET_FPS,
                 headless=False, segundos=None, tolerancia=HIT_TOLERANCE, exposicao=None):
        self.test_mode = test_mode
        self.debug = DEBUG if debug is None else debug
        self.camera_id = camera_id
        self.fps_limit = fps_limit
        self.headless = headless          # sem janelas (para rodar em script)
        self.segundos = segundos          # encerra sozinho após N segundos
        self.tolerancia = tolerancia
        self.exposicao = exposicao

        self.camera_mgr = CameraManager()
        self.cam = None                   # câmera única (modo teste)
        self.calibration = CameraCalibration()
        self.ball_detector = BallDetector()
        self.hit_detector = HitDetector(self.calibration)
        self.flask = FlaskClient()
        self.running = False

        self._frame_times = deque(maxlen=30)
        self._ultimo_log = 0.0
        self._hsv_ativo = False
        # estatísticas do modo teste
        self.frames = 0
        self.frames_com_bola = 0
        self.acertos_simulados = 0
        self._ultimo_acerto = 0.0
        self._inicio = None
        self._capturas = 0

    # ====================================================================================
    # Inicialização
    # ====================================================================================
    def initialize(self):
        print("\n" + "=" * 60)
        print("🎾 SMART TENNIS ARENA — " + ("TESTE DE VISÃO (1 câmera)" if self.test_mode else "VISÃO COMPUTACIONAL"))
        print("=" * 60 + "\n")
        return self._initialize_single_camera() if self.test_mode else self._initialize_dual_camera()

    def _esperar_frames(self, timeout, obter):
        fim = time.time() + timeout
        while time.time() < fim:
            frames = obter()
            if all(f is not None for f in frames):
                return frames
            time.sleep(0.05)
        return tuple(None for _ in obter())

    def _initialize_single_camera(self):
        self.cam = CameraThread(self.camera_id, f"câmera {self.camera_id}", fps=self.fps_limit, exposicao=self.exposicao)
        if not self.cam.abrir():
            print(f"[Main] ❌ Câmera {self.camera_id} não abriu.")
            print("       Dicas: feche outros apps que usam a câmera; rode com --listar para ver os ids;")
            print("       tente --camera 1 ou --camera 2.")
            return False
        (frame,) = self._esperar_frames(5.0, lambda: (self.cam.ultimo_frame(),))
        if frame is None:
            print("[Main] ❌ A câmera abriu mas não entregou imagem")
            return False
        w, h = frame.shape[1], frame.shape[0]
        print(f"[Main] ✅ Câmera {self.camera_id} conectada: {w}x{h}")
        # o modo teste NÃO grava calibração: ela é da resolução desta webcam, não das câmeras da arena
        self.calibration.calibrate_camera1(frame, salvar=False)
        self.running = True
        return True

    def _initialize_dual_camera(self):
        if not self.camera_mgr.init_cameras():
            return False

        print("[Main] Aguardando câmeras estabilizarem...")
        frame1, frame2 = self._esperar_frames(5.0, self.camera_mgr.get_frames)
        if frame1 is None or frame2 is None:
            print("[Main] ❌ Uma das câmeras não entregou imagem")
            return False

        # Calibração salva vale só se a resolução for a mesma; senão, refaz
        if not self.calibration.load_calibration() or not self._calibracao_confere(frame1, frame2):
            self.calibration.calibrate_camera1(frame1)
            self.calibration.calibrate_camera2(frame2)

        self.flask.start_heartbeat()
        self.running = True
        print("[Main] ✅ Sistema inicializado\n")
        return True

    def _calibracao_confere(self, frame1, frame2):
        """A calibração salva foi feita para esta resolução? O canto inferior direito do frame
        tem que cair no canto esperado do mundo (senão a resolução mudou)."""
        h1, w1 = frame1.shape[:2]
        h2, w2 = frame2.shape[:2]
        p1 = self.calibration.pixel_to_world_camera1(w1, h1)   # -> (X máx, Z da base)
        p2 = self.calibration.pixel_to_world_camera2(w2, h2)   # -> (Z da direita, Y do chão)
        esperado1 = (CAM1_X_RANGE[1], CAM1_Z_RANGE[1])
        esperado2 = (CAM2_Z_RANGE[1], CAM2_Y_RANGE[0])
        ok = (p1 is not None and p2 is not None
              and max(abs(a - b) for a, b in zip(p1 + p2, esperado1 + esperado2)) < 1e-3)
        if not ok:
            print("[Main] ⚠️ Calibração salva não corresponde à resolução atual; recalibrando")
        return ok

    # ====================================================================================
    # Loop principal
    # ====================================================================================
    def run(self):
        self._inicio = time.time()
        if self.test_mode:
            self._run_test_mode()
        else:
            self._run_dual_mode()

    def _venceu_o_tempo(self):
        return self.segundos is not None and time.time() - self._inicio >= self.segundos

    def _run_dual_mode(self):
        print("[Main] 🚀 Detectando bola...  ('q' sai, 'c' recalibra; sem janelas use Ctrl+C)\n")
        while self.running and not self._venceu_o_tempo():
            t0 = time.time()
            frame1, frame2 = self.camera_mgr.get_frames()
            if frame1 is None or frame2 is None:
                time.sleep(0.01)
                continue

            det1 = self.ball_detector.detect_ball_camera1(frame1)
            det2 = self.ball_detector.detect_ball_camera2(frame2)
            ball_pos = self.hit_detector.triangulate_ball_position(det1, det2)

            if ball_pos:
                if self.hit_detector.check_hit(ball_pos):
                    self.flask.send_hit_async(ball_pos)
                self._log_posicao(ball_pos)

            if self.debug and not self.headless:
                self._mostrar(frame1, frame2, det1, det2)
                if not self._tratar_teclas(frame1, frame2):
                    break

            self._frame_times.append(time.time())
            resto = 1.0 / TARGET_FPS - (time.time() - t0)
            if resto > 0:
                time.sleep(resto)

    # --- modo teste ---------------------------------------------------------------------
    def avaliar_teste(self, frame, agora=None):
        """
        Um frame do modo teste. Retorna (det, info): det = (x, y, raio) em pixels ou None;
        info = (X, Z, dist, acerto) em metros ou None. Com 1 câmera só há X e Z (vista de cima).
        """
        agora = time.time() if agora is None else agora
        det = self.ball_detector.detect_ball_camera1(frame)
        self.frames += 1
        if det is None:
            return None, None
        self.frames_com_bola += 1

        X, Z = self.calibration.pixel_to_world_camera1(det[0], det[1])
        dist = math.hypot(X - LASER_X, Z - LASER_Z)
        acerto = dist <= self.tolerancia + 1e-9 and agora - self._ultimo_acerto >= HIT_DEBOUNCE_S
        if acerto:
            self._ultimo_acerto = agora
            self.acertos_simulados += 1
        return det, (X, Z, dist, acerto)

    def _run_test_mode(self):
        print("[Main] 🚀 Iniciando teste...")
        if not self.headless:
            print("Teclas:  q sair | c recalibrar | s screenshot | d liga/desliga anotações"
                  " | h sliders HSV | p imprime HSV para o config.py\n")
        ultimo = None
        while self.running and not self._venceu_o_tempo():
            frame = self.cam.ultimo_frame()
            if frame is None or frame is ultimo:      # ainda não chegou frame novo
                time.sleep(0.002)
                continue
            ultimo = frame
            self._frame_times.append(time.time())

            if self._hsv_ativo:
                self._aplicar_hsv()
            det, info = self.avaliar_teste(frame)

            if info:
                X, Z, dist, acerto = info
                self._log_teste(X, Z, dist)
                if acerto:
                    print(f"[Main] ✅ ACERTO SIMULADO!  (X={X:.2f}m Z={Z:.2f}m, a {dist * 100:.1f} cm do laser)")

            if not self.headless:
                self._mostrar_teste(frame, det, info)
                if not self._tratar_teclas_teste(frame):
                    break

    def _log_teste(self, X, Z, dist):
        agora = time.time()
        if agora - self._ultimo_log >= LOG_INTERVAL_S:
            self._ultimo_log = agora
            print(f"[Main] Bola: X={X:.2f}m Z={Z:.2f}m  dist_laser={dist:.2f}m  FPS={self._fps():.1f}")

    def _mostrar_teste(self, frame, det, info):
        tela = frame.copy()
        if self.debug:
            self.ball_detector.draw_detections(tela, None, det, None)
            alvo = self.calibration.world_to_pixel_camera1(LASER_X, LASER_Z)
            if alvo:
                raio_px = self._tolerancia_em_pixels()
                cv2.circle(tela, (int(alvo[0]), int(alvo[1])), raio_px, (255, 0, 0), 2)
                cv2.putText(tela, "LASER ALVO", (int(alvo[0]) - 50, int(alvo[1]) - raio_px - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
            if info:
                X, Z, dist, _ = info
                cv2.putText(tela, f"X={X:.2f}m Z={Z:.2f}m Dist={dist:.2f}m", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(tela, f"FPS: {self._fps():.1f}   Acertos simulados: {self.acertos_simulados}",
                        (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow(JANELA_TESTE, tela)
        if self._hsv_ativo:
            cv2.imshow(JANELA_MASCARA, self.ball_detector.mascara(frame))

    def _tolerancia_em_pixels(self):
        """Raio (px) da tolerância de acerto ao redor do alvo, para desenhar o círculo."""
        c = self.calibration.world_to_pixel_camera1(LASER_X, LASER_Z)
        b = self.calibration.world_to_pixel_camera1(LASER_X + self.tolerancia, LASER_Z)
        return max(3, int(math.hypot(b[0] - c[0], b[1] - c[1])))

    def _tratar_teclas_teste(self, frame):
        """Retorna False para encerrar."""
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            return False
        if key == ord("c"):
            print("[Main] 🔄 Recalibrando...")
            self.calibration.calibrate_camera1(frame, salvar=False)
        elif key == ord("s"):
            caminho = os.path.join(BASE_DIR, f"screenshot_{self._capturas}.png")
            cv2.imwrite(caminho, frame)
            print(f"[Main] 📸 Screenshot salvo: {caminho}")
            self._capturas += 1
        elif key == ord("d"):
            self.debug = not self.debug
            print(f"[Main] Anotações: {'ON' if self.debug else 'OFF'}")
        elif key == ord("h"):
            self._alternar_hsv()
        elif key == ord("p"):
            self._imprimir_hsv()
        return True

    # --- sliders HSV ao vivo -----------------------------------------------------------------
    def _alternar_hsv(self):
        if self._hsv_ativo:
            for nome in (JANELA_HSV, JANELA_MASCARA):
                cv2.destroyWindow(nome)
            self.ball_detector.restaurar_faixas()
            self._hsv_ativo = False
            print("[Main] Sliders HSV desligados (faixas do config.py restauradas)")
            return
        lo, hi = self.ball_detector.faixas[0]          # parte da faixa amarela
        cv2.namedWindow(JANELA_HSV)
        for nome, valor, maximo in (("H min", lo[0], 179), ("H max", hi[0], 179),
                                    ("S min", lo[1], 255), ("S max", hi[1], 255),
                                    ("V min", lo[2], 255), ("V max", hi[2], 255)):
            cv2.createTrackbar(nome, JANELA_HSV, valor, maximo, lambda v: None)
        self._hsv_ativo = True
        print("[Main] Sliders HSV ligados: usam UMA faixa (as duas do config.py ficam suspensas)")

    def _ler_hsv(self):
        g = lambda n: cv2.getTrackbarPos(n, JANELA_HSV)  # noqa: E731
        return (g("H min"), g("S min"), g("V min")), (g("H max"), g("S max"), g("V max"))

    def _aplicar_hsv(self):
        lo, hi = self._ler_hsv()
        self.ball_detector.set_faixas([(lo, hi)])

    def _imprimir_hsv(self):
        lo, hi = self._ler_hsv() if self._hsv_ativo else self.ball_detector.faixas[0]
        print("[HSV] Cole no vision/config.py:")
        print(f"  YELLOW_LOWER = {tuple(lo)}")
        print(f"  YELLOW_UPPER = {tuple(hi)}")
        print("  (a faixa verde GREEN_* continua valendo: se a bola inteira já cabe nesta faixa, "
              "reduza GREEN_* para evitar falsos positivos)")

    # ====================================================================================
    # Utilidades (modo normal)
    # ====================================================================================
    def _log_posicao(self, ball_pos):
        agora = time.time()
        if self.debug and agora - self._ultimo_log >= LOG_INTERVAL_S:
            self._ultimo_log = agora
            d = self.hit_detector.get_distance_to_laser(ball_pos)
            print(f"[Main] Bola: X={ball_pos[0]:.2f} Y={ball_pos[1]:.2f} Z={ball_pos[2]:.2f}  dist_laser={d:.2f}m")

    def _fps(self):
        if len(self._frame_times) < 2:
            return 0.0
        return (len(self._frame_times) - 1) / (self._frame_times[-1] - self._frame_times[0])

    def _mostrar(self, frame1, frame2, det1, det2):
        self.ball_detector.draw_detections(frame1, frame2, det1, det2)
        cv2.putText(frame1, f"FPS: {self._fps():.1f}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame2, f"Acertos: {self.hit_detector.hit_count}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        # alvo (laser) projetado do mundo para o pixel de cada câmera
        for frame, pt in ((frame1, self.calibration.world_to_pixel_camera1(LASER_X, LASER_Z)),
                          (frame2, self.calibration.world_to_pixel_camera2(LASER_Z, LASER_Y))):
            if pt:
                cv2.circle(frame, (int(pt[0]), int(pt[1])), 30, (255, 0, 0), 2)
                cv2.putText(frame, "LASER ALVO", (int(pt[0]) - 50, int(pt[1]) - 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
        cv2.imshow("Camera 1 (Cima)", frame1)
        cv2.imshow("Camera 2 (Lado)", frame2)

    def _tratar_teclas(self, frame1, frame2):
        """Retorna False para encerrar."""
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            return False
        if key == ord("c"):
            print("[Main] Recalibrando...")
            self.calibration.calibrate_camera1(frame1)
            self.calibration.calibrate_camera2(frame2)
        return True

    # ====================================================================================
    def shutdown(self):
        print("\n[Main] 🛑 Encerrando...")
        self.running = False
        self.flask.stop()
        if self.cam:
            self.cam.fechar()
        self.camera_mgr.release()
        cv2.destroyAllWindows()
        if self.test_mode:
            self._resumo_teste()
        else:
            print(f"[Main] Total de acertos detectados: {self.hit_detector.hit_count}")

    def _resumo_teste(self):
        dur = max(1e-9, time.time() - (self._inicio or time.time()))
        pct = 100.0 * self.frames_com_bola / self.frames if self.frames else 0.0
        print("[Main] ---- Resumo do teste ----")
        print(f"[Main] Duração: {dur:.1f}s | frames: {self.frames} | FPS médio: {self.frames / dur:.1f}")
        print(f"[Main] Frames com bola detectada: {self.frames_com_bola} ({pct:.1f}%)")
        print(f"[Main] Acertos simulados: {self.acertos_simulados}")


def criar_parser():
    p = argparse.ArgumentParser(description="Smart Tennis Arena - visão computacional")
    p.add_argument("--test", action="store_true", help="modo teste: 1 câmera, sem Flask")
    p.add_argument("--debug", action="store_true", help="mostra anotações (círculo da bola, alvo, FPS)")
    p.add_argument("--camera", type=int, default=CAMERA1_ID, help="id da câmera (modo teste)")
    p.add_argument("--fps-limit", type=int, default=TARGET_FPS, help="FPS pedido à câmera")
    p.add_argument("--tolerancia", type=float, default=HIT_TOLERANCE,
                   help="tolerância do acerto simulado, em metros (padrão: config.HIT_TOLERANCE)")
    p.add_argument("--exposicao", type=float, default=None,
                   help="exposição manual (ex.: -5). Menor = mais FPS e imagem mais escura; use com boa luz")
    p.add_argument("--headless", action="store_true", help="sem janelas (só console)")
    p.add_argument("--segundos", type=float, default=None, help="encerra sozinho após N segundos")
    p.add_argument("--listar", action="store_true", help="lista as câmeras que abrem e sai")
    return p


def main(argv=None):
    args = criar_parser().parse_args(argv)
    if args.listar:
        achadas = listar_cameras()
        print("Câmeras encontradas:" if achadas else "Nenhuma câmera abriu.")
        for i, w, h in achadas:
            print(f"  --camera {i}   ({w}x{h})")
        return

    system = SmartTennisVision(test_mode=args.test, debug=True if args.debug else None,
                               camera_id=args.camera, fps_limit=args.fps_limit,
                               headless=args.headless, segundos=args.segundos, tolerancia=args.tolerancia,
                               exposicao=args.exposicao)
    try:
        if system.initialize():
            system.run()
    except KeyboardInterrupt:
        print("\n[Main] Interrompido pelo usuário")
    finally:
        system.shutdown()


if __name__ == "__main__":
    main()
