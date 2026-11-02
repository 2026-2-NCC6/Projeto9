"""
Movimento automático do laser por nível de dificuldade.

  FÁCIL   : laser no centro (90°, 90°); o operador ainda pode ajustar pelo app.
  MÉDIO   : círculo lento (período 10 s, ±35° em X e ±25° em Y).
  DIFÍCIL : novo alvo aleatório a cada 2 s (30°-150°), com transição suave de 0,5 s.

Duas camadas:
  LaserController  lógica PURA: (nível, tempo decorrido) -> ângulos. Sem serial, sem threads.
  LaserDriver      leva os ângulos ao Arduino, em 20 Hz, de duas formas:
                     "abs"         comando  G<x>,<y>  (firmware novo, ver arduino/hoje_com_G)
                     "incremental" passos A/D/W/S de ±5° (sketch atual: mais lento)
                     "simulado"    sem Arduino: só acompanha as posições

Por segurança o jogo expira sozinho após MAX_JOGO_S (o app pode cair sem mandar /jogo/parar).
"""
import math
import random
import threading
import time
from enum import Enum

CENTRO = 90
MAX_JOGO_S = 70.0   # uma partida dura 60 s


class Nivel(Enum):
    FACIL = "facil"
    MEDIO = "medio"
    DIFICIL = "dificil"


def _lerp(a, b, t):
    return a + (b - a) * t


def _limitar(v, lo=0, hi=180):
    return max(lo, min(hi, v))


class LaserController:
    """Calcula onde o laser deve estar. Função pura do tempo decorrido (testável sem relógio)."""

    PERIODO_MEDIO = 10.0
    AMPLITUDE_X = 35
    AMPLITUDE_Y = 25
    RAMPA_MEDIO = 1.0       # o círculo "abre" a partir do centro no 1º segundo
    CICLO_DIFICIL = 2.0
    TRANSICAO_DIFICIL = 0.5
    FAIXA_DIFICIL = (30, 150)

    def __init__(self, seed=None, relogio=time.monotonic):
        self._lock = threading.Lock()
        self._relogio = relogio
        self._seed_fixa = seed is not None
        self._seed = seed if seed is not None else 0
        self.level = Nivel.FACIL
        self._inicio = None

    # --- ciclo de vida ------------------------------------------------------------
    def start_game(self, nivel):
        """Aceita 'facil'/'medio'/'dificil' (ou um Nivel). ValueError se for outro valor."""
        n = nivel if isinstance(nivel, Nivel) else Nivel(str(nivel).strip().lower())
        with self._lock:
            self.level = n
            self._inicio = self._relogio()
            if not self._seed_fixa:
                self._seed = random.getrandbits(32)   # cada partida tem seus próprios alvos
        return n

    def stop_game(self):
        with self._lock:
            self._inicio = None

    def elapsed(self):
        with self._lock:
            return None if self._inicio is None else self._relogio() - self._inicio

    @property
    def is_active(self):
        e = self.elapsed()
        return e is not None and e <= MAX_JOGO_S   # expira sozinho

    # --- posição ------------------------------------------------------------------------
    def get_servo_angles(self, elapsed=None):
        """(servo1, servo2) em graus para o instante `elapsed` (padrão: agora)."""
        if elapsed is None:
            elapsed = self.elapsed()
            if elapsed is None:
                return CENTRO, CENTRO
        if self.level == Nivel.MEDIO:
            x, y = self._medio(elapsed)
        elif self.level == Nivel.DIFICIL:
            x, y = self._dificil(elapsed)
        else:
            x, y = CENTRO, CENTRO
        return int(round(_limitar(x))), int(round(_limitar(y)))

    def _medio(self, t):
        angulo = 2 * math.pi * (t % self.PERIODO_MEDIO) / self.PERIODO_MEDIO
        rampa = min(1.0, t / self.RAMPA_MEDIO)
        return (CENTRO + rampa * self.AMPLITUDE_X * math.cos(angulo),
                CENTRO + rampa * self.AMPLITUDE_Y * math.sin(angulo))

    def alvo_dificil(self, ciclo):
        """Alvo do ciclo `ciclo` (0, 1, 2...): determinístico para a semente da partida."""
        rng = random.Random(f"{self._seed}:{ciclo}")
        lo, hi = self.FAIXA_DIFICIL
        return rng.randint(lo, hi), rng.randint(lo, hi)

    def _dificil(self, t):
        ciclo = int(t // self.CICLO_DIFICIL)
        fase = t - ciclo * self.CICLO_DIFICIL
        atual = self.alvo_dificil(ciclo)
        anterior = (CENTRO, CENTRO) if ciclo == 0 else self.alvo_dificil(ciclo - 1)
        if fase < self.TRANSICAO_DIFICIL:
            p = fase / self.TRANSICAO_DIFICIL
            return _lerp(anterior[0], atual[0], p), _lerp(anterior[1], atual[1], p)
        return atual


class LaserDriver:
    """Leva a posição calculada pelo LaserController até o Arduino."""

    PASSO = 5  # graus por comando A/D/W/S no sketch atual

    def __init__(self, controller, escrever, modo, taxa_hz=20):
        self.controller = controller
        self._escrever = escrever          # escrever(bytes): sem ler resposta
        self.modo = modo                   # "abs" | "incremental" | "simulado"
        self.taxa_hz = taxa_hz
        self.pos = [CENTRO, CENTRO]        # posição ESTIMADA dos servos
        self._lock = threading.Lock()
        self._estava_ativo = False
        self._ultimo_enviado = None
        self._thread = None

    # --- comandos de baixo nível --------------------------------------------------------
    def _mover(self, x, y):
        if self.modo == "abs":
            if (x, y) != self._ultimo_enviado:
                self._escrever(f"G{x},{y}\n".encode())
                self._ultimo_enviado = (x, y)
            self.pos = [x, y]
        elif self.modo == "incremental":
            # 1 passo de 5° por eixo por ciclo (sketch: A/W somam, D/S subtraem)
            cmds = ""
            for i, (menos, mais) in enumerate((("D", "A"), ("S", "W"))):
                dif = (x, y)[i] - self.pos[i]
                if dif >= self.PASSO:
                    cmds += mais
                    self.pos[i] = min(180, self.pos[i] + self.PASSO)
                elif dif <= -self.PASSO:
                    cmds += menos
                    self.pos[i] = max(0, self.pos[i] - self.PASSO)
            if cmds:
                self._escrever(cmds.encode())
        else:
            self.pos = [x, y]

    def _centralizar(self):
        """Volta ao centro de uma vez (início e fim da partida)."""
        if self.modo == "abs":
            self._escrever(f"G{CENTRO},{CENTRO}\n".encode())
        elif self.modo == "incremental":
            self._escrever(b"R")           # sketch: R = servos em 90°
        self.pos = [CENTRO, CENTRO]
        self._ultimo_enviado = (CENTRO, CENTRO)

    def ir_para(self, x, y):
        """Modo manual: para o jogo automático e vai para (x, y)."""
        x, y = int(_limitar(x)), int(_limitar(y))
        with self._lock:
            self.controller.stop_game()
            self._estava_ativo = False     # sem isso o "fim de jogo" recentralizaria por cima
            if self.modo == "abs":
                self._escrever(f"G{x},{y}\n".encode())
                self._ultimo_enviado = (x, y)
            elif self.modo == "incremental":
                cmds = ""
                for i, (menos, mais) in enumerate((("D", "A"), ("S", "W"))):
                    n = round(((x, y)[i] - self.pos[i]) / self.PASSO)
                    cmds += (mais if n > 0 else menos) * abs(n)
                if cmds:
                    self._escrever(cmds.encode())
                x = _limitar(self.pos[0] + round((x - self.pos[0]) / self.PASSO) * self.PASSO)
                y = _limitar(self.pos[1] + round((y - self.pos[1]) / self.PASSO) * self.PASSO)
            self.pos = [x, y]
        return x, y

    # --- laço de controle -----------------------------------------------------------------
    def passo(self):
        """Um ciclo de controle (chamado ~20x/s pela thread; público para testes)."""
        with self._lock:
            ativo = self.controller.is_active
            if ativo and not self._estava_ativo:
                self._centralizar()                      # começou: parte do centro
            elif self._estava_ativo and not ativo:
                self._centralizar()                      # acabou (ou expirou): volta ao centro
            self._estava_ativo = ativo
            if not ativo or self.controller.level == Nivel.FACIL:
                return                                   # FÁCIL: só centraliza, não segura o laser
            x, y = self.controller.get_servo_angles()
            self._mover(x, y)

    def iniciar_thread(self):
        def laco():
            while True:
                try:
                    self.passo()
                except Exception as e:  # noqa: BLE001 - o laço não pode morrer
                    print(f"[LaserDriver] erro no laço: {e}")
                time.sleep(1.0 / self.taxa_hz)

        self._thread = threading.Thread(target=laco, daemon=True, name="laser-driver")
        self._thread.start()
