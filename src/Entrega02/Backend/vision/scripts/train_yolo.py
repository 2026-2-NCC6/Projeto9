import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VISION_DIR = os.path.dirname(SCRIPT_DIR)
ROOT_DIR = os.path.dirname(VISION_DIR)

DATASET_DIR = os.path.join(ROOT_DIR, "dataset")
CAMERA0_DIR = os.path.join(DATASET_DIR, "training", "camera0")
CAMERA1_DIR = os.path.join(DATASET_DIR, "training", "camera1")
YAML_PATH = os.path.join(DATASET_DIR, "dataset.yaml")
RUNS_DIR = os.path.join(ROOT_DIR, "runs", "detect")

# A câmera 1 (lateral), nesta sala, tem um chinelo branco e um reflexo forte do piso no campo de
# visão que o auto-rotulador confunde com a bola na maioria das vezes (medido: ~81% das "detecções"
# caem bem em cima desses dois pontos fixos, não espalhadas pela sala como a bola de verdade seria).
# Treinar com isso ensinaria o modelo a reconhecer chinelo, não bola. Até mover esses objetos pra
# fora do quadro (ou reduzir o reflexo) e recapturar, treina só com a câmera 0, que auditada saiu
# limpa. Troque para True depois de confirmar visualmente que a câmera 1 está confiável de novo.
USAR_CAMERA1 = False


def _contar_imagens(pasta):
    if not os.path.isdir(pasta):
        return 0
    return len([f for f in os.listdir(pasta) if f.lower().endswith((".jpg", ".jpeg", ".png"))])


def _criar_yaml(cameras):
    # path absoluto: evita a resolução relativa do ultralytics (que usa um datasets_dir global em
    # runs/settings.yaml e às vezes não é o que se espera) apontar para o lugar errado.
    linhas_train = "".join(f"  - training/{c}\n" for c in cameras)
    conteudo = (
        f"path: {DATASET_DIR}\n"
        f"train:\n{linhas_train}"
        f"val:\n{linhas_train}"
        "\n"
        "nc: 1\n"
        "names: ['ball']\n"
    )
    with open(YAML_PATH, "w", encoding="utf-8") as f:
        f.write(conteudo)


def train_yolo():
    print("TREINO YOLOV8 - DETECCAO DE BOLINHA")

    if not os.path.isdir(CAMERA0_DIR) and not os.path.isdir(CAMERA1_DIR):
        print("Execute primeiro: python vision/scripts/capture_dataset.py")
        return

    cameras = ["camera0"] + (["camera1"] if USAR_CAMERA1 else [])
    if not USAR_CAMERA1:
        print("Câmera 1 (lateral) excluída deste treino: dados não confiáveis nesta sala (veja o comentário no topo do script).")

    n0 = _contar_imagens(CAMERA0_DIR)
    n1 = _contar_imagens(CAMERA1_DIR) if USAR_CAMERA1 else 0
    total_imagens = n0 + n1
    if total_imagens < 10:
        print("Capture pelo menos 50 imagens antes de treinar")
        return

    print(f"{n0} imagens da câmera 0" + (f" + {n1} da câmera 1" if USAR_CAMERA1 else "") + f" = {total_imagens} para treino")
    _criar_yaml(cameras)

    from ultralytics import YOLO
    try:
        import torch
        device = 0 if torch.cuda.is_available() else "cpu"
    except ImportError:
        device = "cpu"

    print(f"Dispositivo: {'GPU' if device == 0 else 'CPU'}")
    if device == "cpu":
        print("Sem GPU disponível: o treino no CPU é bem mais lento que os 30-60 min estimados.")
    print("Iniciando treino...")

    modelo = YOLO("yolov8n.pt")
    modelo.train(
        data=YAML_PATH,
        epochs=50,
        imgsz=640,
        batch=8,
        patience=10,
        device=device,
        project=RUNS_DIR,
        name="ball_detector_v1",
        exist_ok=True,   # re-treinar (mais dados, nova sessão) SOBRESCREVE em vez de criar
                          # ball_detector_v12, v13...; senão detect_realtime.py ficaria apontando
                          # pro modelo velho depois de "mais uns treinos"
        verbose=True,
    )

    print("TREINO CONCLUIDO")
    print(f"Caminho: {os.path.join(RUNS_DIR, 'ball_detector_v1', 'weights', 'best.pt')}")
    print("Epochs: 50")
    print(f"Imagens usadas: {total_imagens}")


if __name__ == '__main__':
    train_yolo()
