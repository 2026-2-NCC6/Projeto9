import threading
import time

import requests

from config import (FLASK_URL, FLASK_HEARTBEAT_URL, FLASK_TIMEOUT, HEARTBEAT_INTERVAL_S, DEBUG)


class FlaskClient:
    """
    Fala com a API Flask.
      - send_hit: POST /acerto (em thread, para não travar o loop de 30 fps)
      - heartbeat: POST /visao/heartbeat a cada poucos segundos. Sem ele o Flask marca a
        visão como inativa após 30s sem acerto e o app volta a gerar acertos falsos pelo timer.
    """

    def __init__(self, url=FLASK_URL, heartbeat_url=FLASK_HEARTBEAT_URL):
        self.url = url
        self.heartbeat_url = heartbeat_url
        self._stop = threading.Event()
        self._thread = None

    @staticmethod
    def build_payload(ball_pos, timestamp=None):
        x, y, z = ball_pos
        return {
            "source": "vision",
            "acertou": True,
            "position": {"X": round(x, 3), "Y": round(y, 3), "Z": round(z, 3)},
            "timestamp": time.time() if timestamp is None else timestamp,
        }

    def send_hit(self, ball_pos):
        """Envia o acerto de forma síncrona. Retorna True se o Flask respondeu 200."""
        if ball_pos is None:
            return False
        try:
            r = requests.post(self.url, json=self.build_payload(ball_pos), timeout=FLASK_TIMEOUT)
        except requests.exceptions.RequestException as e:
            print(f"[FlaskClient] ❌ Erro ao conectar no Flask: {e}")
            return False
        if r.status_code != 200:
            print(f"[FlaskClient] ❌ Flask retornou {r.status_code}")
            return False
        if DEBUG:
            x, y, z = ball_pos
            print(f"[FlaskClient] ✅ Acerto enviado: X={x:.2f} Y={y:.2f} Z={z:.2f}")
        return True

    def send_hit_async(self, ball_pos):
        threading.Thread(target=self.send_hit, args=(ball_pos,), daemon=True).start()

    def start_heartbeat(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._thread.start()

    def _heartbeat_loop(self):
        avisou_erro = False
        while not self._stop.is_set():
            try:
                requests.post(self.heartbeat_url, timeout=FLASK_TIMEOUT)
                avisou_erro = False
            except requests.exceptions.RequestException:
                if not avisou_erro:  # não polui o console a cada 5s
                    print("[FlaskClient] ⚠️ Flask indisponível (heartbeat); tentando de novo...")
                    avisou_erro = True
            self._stop.wait(HEARTBEAT_INTERVAL_S)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
