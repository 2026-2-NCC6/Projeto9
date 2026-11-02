"""Treino por dominio (quadra ou mesa): continua do melhor modelo DO MESMO dominio (ou, se nao
existir, do modelo mais recente de qualquer dominio) e usa uma validacao SEPARADA do treino. A
validacao vem de dataset/validacao/<dominio>/ (sessoes gravadas com
capture_game_live.py --destino validacao/<dominio>). Sem essa pasta, reserva os ultimos 20% dos
frames de cada camera pra validacao.

Dominios diferentes (quadra = quadra real, mesa = miniatura de mesa) tem cenas totalmente diferentes
(fundo, escala, iluminacao) -- por isso cada um guarda seu proprio dataset e seu proprio run, pra um
nao poluir o treino do outro."""
import argparse
import glob
import os
import random
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VISION_DIR = os.path.dirname(SCRIPT_DIR)
ROOT_DIR = os.path.dirname(VISION_DIR)

DATASET_DIR = os.path.join(ROOT_DIR, "dataset")
RUNS_DIR = os.path.join(ROOT_DIR, "runs", "detect")
FRACAO_VAL_SEM_SESSAO = 0.2
RAZAO_NEGATIVOS_PADRAO = 3.0   # no maximo N imagens "vazias" (sem bola) pra cada imagem com bola


def _caminhos(dominio):
    return {
        "treino": os.path.join(DATASET_DIR, "training", dominio),
        "validacao": os.path.join(DATASET_DIR, "validacao", dominio),
        "train_txt": os.path.join(DATASET_DIR, f"lista_treino_{dominio}.txt"),
        "val_txt": os.path.join(DATASET_DIR, f"lista_validacao_{dominio}.txt"),
        "yaml": os.path.join(DATASET_DIR, f"dataset_{dominio}.yaml"),
        "nome_run": f"ball_detector_{dominio}",
    }


def _modelo_base(nome_run):
    """Prioridade: o melhor modelo do MESMO dominio (continuar o que ja aprendeu nessa cena).
    So cai pro modelo mais recente de outro dominio se ainda nao existir treino desse dominio."""
    caminho_proprio = os.path.join(RUNS_DIR, nome_run, "weights", "best.pt")
    if os.path.isfile(caminho_proprio):
        return caminho_proprio
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


def _frames_ordenados(pasta):
    """jpgs da pasta em ordem de numero de frame (frame_0001 < frame_0002 ...)."""
    if not os.path.isdir(pasta):
        return []
    arquivos = [f for f in os.listdir(pasta) if f.lower().endswith(".jpg")]

    def numero(nome):
        m = re.search(r"(\d+)", nome)
        return int(m.group(1)) if m else 0
    return [os.path.join(pasta, f) for f in sorted(arquivos, key=numero)]


def _tem_bola(caminho_jpg):
    txt = caminho_jpg[:-4] + ".txt"
    return os.path.isfile(txt) and os.path.getsize(txt) > 0


def _limitar_negativos(frames, razao_max, semente=0):
    """Mantem todas as imagens com bola, mas sorteia so ate razao_max*positivas imagens vazias.
    Treinar com 20x mais imagem vazia que imagem com bola so deixa cada epoca mais lenta sem
    ensinar nada de novo -- um pouco de fundo negativo basta pro modelo aprender a nao alucinar bola."""
    positivas = [f for f in frames if _tem_bola(f)]
    negativas = [f for f in frames if not _tem_bola(f)]
    limite = int(len(positivas) * razao_max)
    if len(negativas) > limite:
        random.Random(semente).shuffle(negativas)
        negativas = negativas[:limite]
    return positivas + negativas


def _separar_listas(caminhos, razao_negativos):
    """Devolve (treino, validacao) como listas de caminhos de imagem."""
    treino, validacao = [], []
    for cam in ("camera0", "camera1"):
        pasta_val = os.path.join(caminhos["validacao"], cam)
        if _frames_ordenados(pasta_val):
            validacao += _frames_ordenados(pasta_val)
            treino += _frames_ordenados(os.path.join(caminhos["treino"], cam))
        else:
            frames = _frames_ordenados(os.path.join(caminhos["treino"], cam))
            corte = int(len(frames) * (1 - FRACAO_VAL_SEM_SESSAO))
            treino += frames[:corte]
            validacao += frames[corte:]
    if razao_negativos is not None:
        treino = _limitar_negativos(treino, razao_negativos)
        validacao = _limitar_negativos(validacao, razao_negativos)
    return treino, validacao


def _escrever_listas(caminhos, treino, validacao):
    with open(caminhos["train_txt"], "w", encoding="utf-8") as f:
        f.write("\n".join(os.path.abspath(p) for p in treino) + "\n")
    with open(caminhos["val_txt"], "w", encoding="utf-8") as f:
        f.write("\n".join(os.path.abspath(p) for p in validacao) + "\n")
    conteudo = (
        f"train: {caminhos['train_txt']}\n"
        f"val: {caminhos['val_txt']}\n"
        "\nnc: 1\nnames: ['ball']\n"
    )
    with open(caminhos["yaml"], "w", encoding="utf-8") as f:
        f.write(conteudo)


def train_yolo_quadra(epocas=30, dominio="quadra", razao_negativos=RAZAO_NEGATIVOS_PADRAO):
    print(f"TREINO - domínio: {dominio}")
    caminhos = _caminhos(dominio)

    treino, validacao = _separar_listas(caminhos, razao_negativos)
    if len(treino) < 10:
        print(f"Poucos dados de treino. Rode capture_game_live.py --destino training/{dominio} e rotular_por_movimento.py primeiro.")
        return
    if not validacao:
        print(f"Sem dados de validação. Grave uma sessão com --destino validacao/{dominio}.")
        return

    base = _modelo_base(caminhos["nome_run"])
    if base is None:
        print("Nenhum modelo anterior encontrado — treinando do zero (mais lento).")
        base = "yolov8n.pt"
    else:
        print(f"Continuando a partir de: {base}")

    origem_val = "pasta de validação separada" if os.path.isdir(caminhos["validacao"]) and os.listdir(caminhos["validacao"]) \
        else f"últimos {int(FRACAO_VAL_SEM_SESSAO * 100)}% dos frames (sem sessão de validação separada)"
    print(f"Treino: {len(treino)} imagens | Validação: {len(validacao)} imagens ({origem_val})")
    _escrever_listas(caminhos, treino, validacao)

    from ultralytics import YOLO
    try:
        import torch
        device = 0 if torch.cuda.is_available() else "cpu"
    except ImportError:
        device = "cpu"
    print(f"Dispositivo: {'GPU' if device == 0 else 'CPU'}")

    modelo = YOLO(base)
    modelo.train(
        data=caminhos["yaml"],
        epochs=epocas,
        imgsz=640,
        batch=8,
        patience=8,
        device=device,
        project=RUNS_DIR,
        name=caminhos["nome_run"],
        exist_ok=True,
        verbose=True,
    )

    print("TREINO CONCLUIDO")
    print(f"Caminho: {os.path.join(RUNS_DIR, caminhos['nome_run'], 'weights', 'best.pt')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--epocas", type=int, default=30)
    ap.add_argument("--dominio", default="quadra", help="quadra (padrão) ou mesa")
    ap.add_argument("--razao-negativos", type=float, default=RAZAO_NEGATIVOS_PADRAO,
                    help=f"máx. imagens vazias por imagem com bola (padrão {RAZAO_NEGATIVOS_PADRAO}); 0 = usa tudo")
    args = ap.parse_args()
    razao = None if args.razao_negativos <= 0 else args.razao_negativos
    train_yolo_quadra(args.epocas, args.dominio, razao)
