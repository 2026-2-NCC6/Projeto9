import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VISION_DIR = os.path.dirname(SCRIPT_DIR)
ROOT_DIR = os.path.dirname(VISION_DIR)
sys.path.insert(0, VISION_DIR)

import cv2
import numpy as np

try:
    import winsound
except ImportError:
    winsound = None

from camera_manager import abrir_captura

WIDTH, HEIGHT, FPS = 1280, 720, 30
MAX_DISPLAY_WIDTH = 1500
WIN_NAME = "Impacto no gol - Quadra"
RUNS_DIR = os.path.join(ROOT_DIR, "runs", "detect")
CALIB_JSON = os.path.join(ROOT_DIR, "vision", "calibracao_quadra.json")
LOG_CSV = os.path.join(ROOT_DIR, "vision", "impactos_log.csv")

GOL_LARGURA_CM = 32.0   # vao interno da moldura (mesa em miniatura)
GOL_ALTURA_CM = 26.0
TOLERANCIA_LINHA_CM = 3.0   # escala bem menor que a quadra real (era 10cm pra um gol de 310cm) -- ajuste apos testar ao vivo
FRAMES_PARA_CONFIRMAR_IMPACTO = 3


def _ler_seguro(cap):
    try:
        return cap.read()
    except cv2.error as e:
        print(f"Aviso: erro ao ler frame ({e}); tentando continuar")
        return False, None


def _abrir_e_configurar(cam_id):
    cap = abrir_captura(cam_id)
    if cap is None:
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, FPS)
    ok, _ = _ler_seguro(cap)
    if ok:
        return cap
    print(f"Câmera {cam_id}: não aceitou {WIDTH}x{HEIGHT}, reabrindo na resolução nativa")
    cap.release()
    return abrir_captura(cam_id)


def _ajustar_para_tela(frame):
    if frame.shape[1] > MAX_DISPLAY_WIDTH:
        escala = MAX_DISPLAY_WIDTH / frame.shape[1]
        frame = cv2.resize(frame, (MAX_DISPLAY_WIDTH, int(frame.shape[0] * escala)))
    return frame


def _modelo_mais_recente():
    melhor, melhor_tempo = None, -1
    if not os.path.isdir(RUNS_DIR):
        return None
    for nome in os.listdir(RUNS_DIR):
        caminho = os.path.join(RUNS_DIR, nome, "weights", "best.pt")
        if os.path.isfile(caminho):
            t = os.path.getmtime(caminho)
            if t > melhor_tempo:
                melhor, melhor_tempo = caminho, t
    return melhor


def _carregar_calibracao():
    """
    A calibracao 'overhead' foi feita com pontos NO CHAO: ela so da a posicao real de algo que
    esta encostado no chao. A bola no ar, batendo no gol, nao esta no chao -- a conta erra por
    paralaxe (quanto mais alto, mais o pixel "mente" sobre a posicao real). Por isso o X dela so
    serve pra mostrar a posicao lateral aproximada, NUNCA pra decidir se houve impacto.

    Quem decide "a bola chegou na linha do gol" e a camera LATERAL, que ve de lado e nao sofre
    desse problema -- desde que esteja calibrada com profundidade (Z) alem da altura (Y). Se essa
    calibracao completa ('lateral' com 4 pontos, nao so 'lateral_altura' com 2) ainda nao existe,
    cai de volta pro metodo antigo (usando o Z da camera de cima) e avisa que ele e so aproximado.
    """
    if not os.path.isfile(CALIB_JSON):
        raise SystemExit("Sem calibração. Rode calibrar_quadra.py (cima) e calibrar_altura_poste.py (lateral).")
    with open(CALIB_JSON, encoding="utf-8") as f:
        dados = json.load(f)
    if "overhead" not in dados or "lateral_altura" not in dados:
        raise SystemExit("Calibração incompleta: faltam 'overhead' e/ou 'lateral_altura' em calibracao_quadra.json")
    H_overhead = np.array(dados["overhead"]["H"], dtype=np.float32)
    alt = dados["lateral_altura"]
    H_lateral = None
    if "lateral" in dados:
        H_lateral = np.array(dados["lateral"]["H"], dtype=np.float32)
    return H_overhead, alt["y_base"], alt["y_topo"], alt["altura_topo_cm"], H_lateral


def _beep():
    if winsound:
        try:
            winsound.Beep(1200, 150)
            return
        except RuntimeError:
            pass
    print("\a", end="", flush=True)


def _detectar(frame, modelo):
    resultados = modelo(frame, verbose=False)[0]
    if len(resultados.boxes) == 0:
        return None
    caixa = resultados.boxes[int(resultados.boxes.conf.argmax())]
    x1, y1, x2, y2 = map(int, caixa.xyxy[0])
    return x1, y1, x2, y2, float(caixa.conf[0])


def _chao_cm(H, cx, cy):
    ponto = np.array([[[cx, cy]]], dtype=np.float32)
    X, Z = cv2.perspectiveTransform(ponto, H)[0][0]
    return float(X), float(Z)


def _altura_cm(y_base, y_topo, altura_topo, cy):
    return (y_base - cy) / (y_base - y_topo) * altura_topo


def detect_impact_live(id0=2, id1=1):
    H, y_base, y_topo, altura_topo, H_lateral = _carregar_calibracao()
    if H_lateral is None:
        print("AVISO: calibração 'lateral' (4 pontos, profundidade+altura) ainda não existe.")
        print("       Usando o Z da câmera de cima (só serve de aproximação p/ bola no ar).")
        print("       Rode calibrar_quadra.py --nome lateral pra corrigir isso.")

    caminho_modelo = _modelo_mais_recente()
    if caminho_modelo is None:
        print("Nenhum modelo treinado encontrado.")
        return
    print(f"Modelo: {caminho_modelo}")

    from ultralytics import YOLO
    modelo = YOLO(caminho_modelo)

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
    cv2.moveWindow(WIN_NAME, 0, 0)

    impactos = []
    total_deteccoes = 0
    streak = 0
    falhas = 0
    novo_csv = not os.path.isfile(LOG_CSV)
    log = open(LOG_CSV, "a", newline="", encoding="utf-8")
    escritor = csv.writer(log)
    if novo_csv:
        escritor.writerow(["data_hora", "x_cm", "altura_cm", "dentro_do_gol"])

    try:
        while True:
            ok0, frame0 = _ler_seguro(cap0)
            ok1, frame1 = _ler_seguro(cap1)
            if not ok0 or not ok1:
                falhas += 1
                if falhas > 30:
                    print("Erro ao ler frame (repetido) — encerrando")
                    break
                cv2.waitKey(30)
                continue
            falhas = 0

            if frame0.shape[:2] != (HEIGHT, WIDTH):
                frame0 = cv2.resize(frame0, (WIDTH, HEIGHT))
            if frame1.shape[:2] != (HEIGHT, WIDTH):
                frame1 = cv2.resize(frame1, (WIDTH, HEIGHT))

            det0 = _detectar(frame0, modelo)
            det1 = _detectar(frame1, modelo)

            X = Z = altura = None
            Z_lateral = None
            if det0:
                x1, y1, x2, y2, conf = det0
                total_deteccoes += 1
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                X, Z = _chao_cm(H, cx, cy)
                cv2.rectangle(frame0, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.circle(frame0, (int(cx), int(cy)), 5, (0, 255, 0), -1)
                cv2.putText(frame0, f"X={X:.0f}cm Z={Z:.0f}cm", (x1, max(20, y1 - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            if det1:
                x1, y1, x2, y2, conf = det1
                cx1, cy1 = (x1 + x2) / 2, (y1 + y2) / 2
                if H_lateral is not None:
                    # calibração completa da lateral: Z_lateral = profundidade real (0 = plano do gol),
                    # altura = já corrigida pela mesma homografia (melhor que a conta de 2 pontos)
                    Z_lateral, altura = _chao_cm(H_lateral, cx1, cy1)
                else:
                    altura = _altura_cm(y_base, y_topo, altura_topo, cy1)
                cv2.rectangle(frame1, (x1, y1), (x2, y2), (255, 0, 0), 2)
                texto = f"altura={altura:.0f}cm"
                if Z_lateral is not None:
                    texto += f" prof={Z_lateral:.0f}cm"
                cv2.putText(frame1, texto, (x1, max(20, y1 - 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

            # a profundidade (ela decide se a bola CHEGOU no plano do gol) vem da lateral quando
            # a calibração completa existe; só cai pro Z da camera de cima (impreciso p/ bola no ar)
            # se a lateral ainda não foi calibrada com os 4 pontos.
            if Z_lateral is not None:
                na_linha = abs(Z_lateral) <= TOLERANCIA_LINHA_CM
            else:
                na_linha = X is not None and abs(Z) <= TOLERANCIA_LINHA_CM
            streak = streak + 1 if na_linha else 0

            impacto_agora = False
            if streak == FRAMES_PARA_CONFIRMAR_IMPACTO:
                # X pode faltar se a câmera de cima perdeu a bola nesse frame exato (a decisão de
                # impacto agora é da lateral); sem X não dá pra dizer se foi dentro da largura do gol.
                dentro = (X is not None and 0 <= X <= GOL_LARGURA_CM) and (altura is None or 0 <= altura <= GOL_ALTURA_CM)
                impactos.append((X, altura, dentro))
                escritor.writerow([datetime.now().isoformat(timespec="seconds"),
                                   "" if X is None else f"{X:.1f}",
                                   "" if altura is None else f"{altura:.1f}", int(dentro)])
                log.flush()
                impacto_agora = True
                _beep()
                print(f"IMPACTO: X={'?' if X is None else f'{X:.1f}'} cm, "
                      f"altura={'?' if altura is None else f'{altura:.1f}'} cm "
                      f"-> {'DENTRO' if dentro else 'FORA'} do gol")

            if impacto_agora or streak >= FRAMES_PARA_CONFIRMAR_IMPACTO:
                cv2.putText(frame0, "IMPACTO NO GOL!", (10, frame0.shape[0] - 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)

            cv2.putText(frame0, "CAMERA CIMA", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(frame1, "CAMERA LATERAL", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
            cv2.putText(frame0, f"Deteccoes: {total_deteccoes}  Impactos: {len(impactos)}", (10, 65),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            combinado = cv2.hconcat([frame0, frame1])
            combinado = _ajustar_para_tela(combinado)
            cv2.imshow(WIN_NAME, combinado)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        log.close()
        cap0.release()
        cap1.release()
        cv2.destroyAllWindows()

    print("--- Resultado ---")
    print(f"Detecções (cima): {total_deteccoes}")
    print(f"Impactos: {len(impactos)} (dentro do gol: {sum(1 for i in impactos if i[2])})")
    print(f"Log: {LOG_CSV}")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument("--cam0", type=int, default=2, help="ID da câmera de cima")
    ap.add_argument("--cam1", type=int, default=1, help="ID da câmera lateral")
    args = ap.parse_args()
    detect_impact_live(args.cam0, args.cam1)
