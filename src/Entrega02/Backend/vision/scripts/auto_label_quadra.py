"""Rotula os frames capturados em dataset/training/quadra/cameraN/ usando o MODELO YA TREINADO
(nao o detector de cor -- ele foi calibrado pra luz/piso de casa, nao serve pra quadra). O modelo
ja aprendeu a cara da bolinha; usa a propria deteccao dele como rotulo pra continuar o treino
(pseudo-rotulagem / fine-tuning)."""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VISION_DIR = os.path.dirname(SCRIPT_DIR)
ROOT_DIR = os.path.dirname(VISION_DIR)
RUNS_DIR = os.path.join(ROOT_DIR, "runs", "detect")
QUADRA_DIR = os.path.join(ROOT_DIR, "dataset", "training", "quadra")
CONF_MINIMA = 0.05


def modelo_mais_recente():
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


def linha_yolo(resultado):
    if len(resultado.boxes) == 0:
        return ""
    caixa = resultado.boxes[int(resultado.boxes.conf.argmax())]
    if float(caixa.conf[0]) < CONF_MINIMA:   # abaixo disso e ruido; o modelo atual acha pouca bola com confianca alta
        return ""
    xc, yc, bw, bh = [float(v) for v in caixa.xywhn[0]]
    return f"0 {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}\n"


MARCADOR_RETOMADA = os.path.join(VISION_DIR, "rotulagem_retomar.txt")


def rotular(pasta, modelo, corte=None):
    if not os.path.isdir(pasta):
        print(f"{pasta}: não existe, pulando")
        return
    arquivos = sorted(f for f in os.listdir(pasta) if f.endswith(".jpg"))
    if not arquivos:
        print(f"{pasta}: nenhuma imagem")
        return
    com_bola = 0
    pulados = 0
    for f in arquivos:
        txt = os.path.join(pasta, f.replace(".jpg", ".txt"))
        if corte is not None and os.path.isfile(txt) and os.path.getmtime(txt) >= corte:
            pulados += 1
            continue
        resultado = modelo(os.path.join(pasta, f), verbose=False)[0]
        linha = linha_yolo(resultado)
        if linha:
            com_bola += 1
        with open(txt, "w") as fh:
            fh.write(linha)
    feitos = len(arquivos) - pulados
    print(f"{pasta}: {feitos} rotulados agora ({com_bola} com bola), {pulados} já feitos antes | total {len(arquivos)}")


if __name__ == "__main__":
    caminho_modelo = modelo_mais_recente()
    if caminho_modelo is None:
        print("Nenhum modelo treinado encontrado em runs/detect/*/weights/best.pt")
        sys.exit(1)
    print(f"Usando modelo: {caminho_modelo}")

    from ultralytics import YOLO
    modelo = YOLO(caminho_modelo)

    corte = None
    if "--retomar" in sys.argv and os.path.isfile(MARCADOR_RETOMADA):
        with open(MARCADOR_RETOMADA, encoding="utf-8-sig") as fh:
            corte = float(fh.read().strip())
        print("Retomando: pulando as fotos rotuladas depois de", corte)

    for cam in ("camera0", "camera1"):
        rotular(os.path.join(QUADRA_DIR, cam), modelo, corte)
