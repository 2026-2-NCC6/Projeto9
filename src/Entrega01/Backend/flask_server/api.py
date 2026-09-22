"""
Smart Tennis Arena - API Flask (notebook).
Ponte entre o app Android (HTTP) e o Arduino (Serial USB).

Uso:
    python api.py                 # tenta abrir COM7; se falhar, roda SIMULADO
    python api.py --porta COM5    # outra porta
    python api.py --simular       # força modo simulado (sem Arduino)

Endpoints:
    GET  /status                      -> {"status","arduino","visao","timestamp"}
    GET  /comando?cmd=W               -> {"comando","resposta","status"}
    POST /acerto                      -> acerto da visão: {"source":"vision","position":{X,Y,Z}}
                                         (userID é opcional: sem ele vale para o jogador da partida atual)
    POST /visao/heartbeat             -> a visão avisa que está viva (mantém "visao": true)
    GET  /acertos?userID=abc          -> {"userID","total"} (o app consulta durante o jogo)
    GET  /configuracao                -> {"flaskURL","arduinoStatus"}

Laser automatico por nivel (ver laser_controller.py):
    POST /jogo/iniciar {"nivel":"facil|medio|dificil"}  -> comeca a mover o laser
    POST /jogo/parar                                    -> para e volta ao centro
    POST /jogo/modo-manual {"x":90,"y":90}              -> para o automatico e vai para (x, y)
    GET  /laser/status                                  -> nivel, alvo e angulos estimados
"""
import argparse
import threading
import time

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from laser_controller import LaserController, LaserDriver, Nivel, MAX_JOGO_S

try:
    import serial
except ImportError:  # pyserial ausente: só modo simulado
    serial = None

app = Flask(__name__)

COMANDOS_VALIDOS = set("ADWSLEBHRP?@#!")

lock = threading.Lock()
arduino = None            # objeto serial.Serial ou None (simulado)
acertos_por_usuario = {}  # userID -> total de acertos vindos da visão
visao_ativa = False       # vira True quando o módulo de visão registrar o primeiro acerto/heartbeat
ultimo_sinal_visao = 0.0
VISAO_TIMEOUT_S = 30      # sem sinal da visão por 30s => considera inativa


laser = LaserController()
driver = LaserDriver(laser, lambda dados: None, "simulado")   # substituído em iniciar_laser()
_ultima_limpeza = 0.0


def escrever_arduino(dados):
    """Escreve bytes SEM esperar resposta (usado pelo laço do laser, 20x/s)."""
    global _ultima_limpeza
    if arduino is None:
        return
    with lock:
        arduino.write(dados)
        agora = time.time()
        if agora - _ultima_limpeza > 1.0:
            arduino.reset_input_buffer()   # o sketch responde a cada passo; sem isso o buffer de RX enche
            _ultima_limpeza = agora


def detectar_modo_laser():
    """
    'abs'         firmware novo (arduino/hoje_com_G): responde '[POS]' ao comando P
    'incremental' sketch atual: só A/D/W/S de +-5 graus
    'simulado'    sem Arduino
    """
    if arduino is None:
        return "simulado"
    return "abs" if "[POS]" in enviar_arduino("P") else "incremental"


def iniciar_laser():
    global driver
    modo = detectar_modo_laser()
    driver = LaserDriver(laser, escrever_arduino, modo)
    driver.iniciar_thread()
    print(f"[API] Laser automatico: modo {modo}")
    if modo == "incremental":
        print("[API] AVISO: firmware sem comando G. FACIL e MEDIO funcionam; o DIFICIL fica limitado "
              "(passos de 5 graus). Grave arduino/hoje_com_G para o DIFICIL completo.")


def abrir_arduino(porta, baud, simular):
    global arduino
    if simular or serial is None:
        print("[API] Modo SIMULADO (sem Arduino)")
        return
    try:
        arduino = serial.Serial(porta, baud, timeout=0.5)
        time.sleep(2)  # o Uno reinicia ao abrir a serial
        print(f"[API] Arduino conectado em {porta}")
    except Exception as e:  # noqa: BLE001
        arduino = None
        print(f"[API] Não abriu {porta} ({e}). Rodando SIMULADO.")


def enviar_arduino(cmd):
    """
    Envia 1 caractere e devolve a resposta do Arduino (todas as linhas, unidas por " | ").
    Lê até 1s no total e para quando a serial fica 0,25s em silêncio.
    """
    if arduino is None:
        return f"[SIMULADO] {cmd}"
    with lock:
        arduino.reset_input_buffer()
        arduino.write(cmd.encode())
        arduino.flush()
        buf = b""
        limite = time.time() + 1.0
        silencio_desde = time.time()
        while time.time() < limite:
            chunk = arduino.read(arduino.in_waiting or 1)
            if chunk:
                buf += chunk
                silencio_desde = time.time()
            elif buf and time.time() - silencio_desde > 0.25:
                break
        linhas = [l.strip() for l in buf.decode(errors="ignore").splitlines() if l.strip()]
        return " | ".join(linhas)


def visao_esta_ativa():
    return visao_ativa and (time.time() - ultimo_sinal_visao) < VISAO_TIMEOUT_S


@app.get("/status")
def status():
    return jsonify(
        status="OK",
        arduino="CONNECTED" if arduino is not None else "SIMULATED",
        visao=visao_esta_ativa(),
        timestamp=int(time.time()),
    )


@app.get("/comando")
def comando():
    cmd = request.args.get("cmd", "")
    if len(cmd) != 1 or cmd not in COMANDOS_VALIDOS:
        return jsonify(comando=cmd, resposta="comando inválido", status="ERROR"), 400
    try:
        resposta = enviar_arduino(cmd)
        return jsonify(comando=cmd, resposta=resposta, status="OK")
    except Exception as e:  # noqa: BLE001
        return jsonify(comando=cmd, resposta=str(e), status="ERROR"), 500


def _marcar_visao_viva():
    global visao_ativa, ultimo_sinal_visao
    visao_ativa = True
    ultimo_sinal_visao = time.time()


@app.post("/visao/heartbeat")
def visao_heartbeat():
    """A visão chama a cada poucos segundos: sem isso o app cairia no timer automático."""
    _marcar_visao_viva()
    return jsonify(status="OK")


@app.post("/acerto")
def acerto():
    """
    Acerto da visão. Aceita o payload da visão computacional
    {"source":"vision","position":{"X","Y","Z"},"timestamp"} e o formato antigo
    {"userID","acertou","x","y","z"}. Sem userID, o acerto vai para o contador geral "*",
    que o app soma ao consultar /acertos (a visão não sabe quem está jogando).
    """
    dados = request.get_json(silent=True) or {}
    _marcar_visao_viva()

    user = dados.get("userID") or "*"
    # payload da visão só é enviado quando houve acerto
    acertou = dados.get("acertou", dados.get("source") == "vision")
    if not acertou:
        return jsonify(status="OK", pontos=0)

    acertos_por_usuario[user] = acertos_por_usuario.get(user, 0) + 1
    pos = dados.get("position") or {}
    print(f"[API] Acerto ({user}): X={pos.get('X', dados.get('x'))} "
          f"Y={pos.get('Y', dados.get('y'))} Z={pos.get('Z', dados.get('z'))}")
    return jsonify(status="OK", pontos=10)


@app.get("/acertos")
def acertos():
    user = request.args.get("userID", "")
    total = acertos_por_usuario.get(user, 0)
    if user != "*":
        total += acertos_por_usuario.get("*", 0)
    return jsonify(userID=user, total=total)


@app.errorhandler(Exception)
def erro_geral(e):
    """Qualquer erro vira JSON. 404/405 mantêm o código HTTP; o resto é 500 e vai para o console."""
    if isinstance(e, HTTPException):
        return jsonify(status="ERROR", message=e.description), e.code
    print(f"[API] Erro nao tratado: {e!r}")
    return jsonify(status="ERROR", message=str(e)), 500


@app.post("/jogo/iniciar")
def jogo_iniciar():
    dados = request.get_json(silent=True) or {}
    try:
        nivel = laser.start_game(dados.get("nivel", "facil"))
    except ValueError:
        return jsonify(status="ERROR", message="nivel invalido (use facil, medio ou dificil)"), 400
    print(f"[API] Jogo iniciado: {nivel.value} (laser {driver.modo})")
    return jsonify(status="OK", message=f"Jogo iniciado: {nivel.value}", nivel=nivel.value,
                   modo_laser=driver.modo, duracao_maxima_s=MAX_JOGO_S)


@app.post("/jogo/parar")
def jogo_parar():
    laser.stop_game()   # o laco do driver volta o laser ao centro
    return jsonify(status="OK", message="Jogo parado")


@app.post("/jogo/modo-manual")
def jogo_modo_manual():
    dados = request.get_json(silent=True) or {}
    try:
        x, y = float(dados.get("x", 90)), float(dados.get("y", 90))
    except (TypeError, ValueError):
        return jsonify(status="ERROR", message="x e y devem ser numeros"), 400
    x, y = driver.ir_para(x, y)
    return jsonify(status="OK", message="Modo manual ativado", angles={"x": x, "y": y})


@app.get("/laser/status")
def laser_status():
    x, y = laser.get_servo_angles()
    return jsonify(status="OK", laser_ativo=laser.is_active, nivel=laser.level.value,
                   modo_laser=driver.modo, alvo={"x": x, "y": y},
                   angulos={"x": driver.pos[0], "y": driver.pos[1]},
                   decorrido_s=laser.elapsed())


@app.get("/configuracao")
def configuracao():
    return jsonify(
        flaskURL=request.host_url.rstrip("/"),
        arduinoStatus="CONNECTED" if arduino is not None else "SIMULATED",
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--porta", default="COM7")
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--simular", action="store_true")
    args = ap.parse_args()
    abrir_arduino(args.porta, args.baud, args.simular)
    iniciar_laser()
    # 0.0.0.0: acessível pelo celular na mesma rede Wi-Fi
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
