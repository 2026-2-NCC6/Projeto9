"""
Constantes da Arena e do sistema de visão (medidas reais em METROS).

Sistema de coordenadas do MUNDO (usado em todo o código):
    X = lateral      (0 a GOAL_WIDTH; centro do gol em GOAL_WIDTH/2)
    Y = altura       (0 = chão)
    Z = profundidade (0 = frente do gol; negativo = para dentro/atrás do gol)

    Câmera 1 (cima) enxerga X e Z.   Câmera 2 (lado) enxerga Z e Y.
    Z é medido pelas duas e a triangulação faz a média.
"""
import os
import sys

# Consoles Windows (cp1252) não codificam emoji: sem isto, um print("✅ ...") levanta
# UnicodeEncodeError e derruba o loop de visão. Com errors="replace" vira "?".
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

# --- Arena -----------------------------------------------------------------
CAMERA1_HEIGHT = 2.8      # câmera de cima: altura do chão
CAMERA1_FOV = 4.2         # câmera de cima: raio de visão
CAMERA2_HEIGHT = 1.2      # câmera lateral: altura do chão
CAMERA2_FOV = 5.5         # câmera lateral: raio de visão

LASER_X = 1.5             # centro do gol
LASER_Y = 1.2             # altura do laser
LASER_Z = -1.0            # atrás da frente do gol

GOAL_HEIGHT = 2.0
GOAL_WIDTH = 3.0
GOAL_DEPTH_MIN = 0.0      # frente do gol
GOAL_DEPTH_MAX = -3.0     # fundo do gol

BALL_DIAMETER_CM = 6.5
BALL_DIAMETER_M = 0.065

# --- Região do mundo que cada câmera enxerga --------------------------------
# A calibração padrão mapeia os 4 cantos do frame para estes retângulos.
# Ajuste conforme o enquadramento real das câmeras.
CAM1_X_RANGE = (0.0, GOAL_WIDTH)                    # esquerda -> direita da imagem
CAM1_Z_RANGE = (GOAL_DEPTH_MAX, GOAL_DEPTH_MIN)     # topo da imagem = fundo do gol, base = frente
CAM2_Z_RANGE = (GOAL_DEPTH_MAX, GOAL_DEPTH_MIN)     # esquerda da imagem = fundo, direita = frente
CAM2_Y_RANGE = (0.0, GOAL_HEIGHT)                   # base da imagem = chão, topo = GOAL_HEIGHT

# --- Cor da bola (escala HSV do OpenCV: H 0-179, S/V 0-255) ------------------
YELLOW_LOWER = (20, 80, 100)
YELLOW_UPPER = (40, 255, 255)
GREEN_LOWER = (80, 60, 80)
GREEN_UPPER = (120, 255, 255)

BALL_MIN_AREA = 50        # px²: abaixo disso é ruído
BALL_MAX_AREA = 10000     # px²: acima disso não é a bola
BALL_MIN_RADIUS = 5       # px
BALL_MIN_FILL = 0.4       # área do blob / área do círculo que o envolve: bola é redonda (~0,8+);
                          # mancha esparsa (parede, pele) fica perto de 0,1. 0,4 tolera bola borrada 2,5:1

# --- Bola rápida (borrão de movimento) ---------------------------------------------------
MAX_FRAMES_PERDIDOS = 5   # frames que o rastreador espera a bola reaparecer antes de desistir
ROI_FATOR_S = 0.5         # na busca por perto da posição prevista, S mínimo cai para 50%...
ROI_FATOR_V = 0.6         # ...e V mínimo para 60% (a bola borrada perde cor e brilho)
BALL_MIN_FILL_ROI = 0.2   # na busca por perto aceita-se um blob mais alongado (faixa borrada)
TRAJETORIA_MAX_S = 0.15   # duas detecções mais distantes no tempo que isto não formam trajetória

# --- Acerto ------------------------------------------------------------------
HIT_TOLERANCE = 0.05      # metros, em cada eixo
HIT_DEBOUNCE_S = 0.5      # evita contar o mesmo movimento várias vezes

# --- Captura -----------------------------------------------------------------
TARGET_FPS = 30
CAMERA1_ID = 0            # webcam de cima
CAMERA2_ID = 1            # webcam lateral
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720

# --- Flask -------------------------------------------------------------------
FLASK_BASE_URL = "http://127.0.0.1:5000"
FLASK_URL = FLASK_BASE_URL + "/acerto"
FLASK_HEARTBEAT_URL = FLASK_BASE_URL + "/visao/heartbeat"
FLASK_TIMEOUT = 2.0
HEARTBEAT_INTERVAL_S = 5.0   # o Flask considera a visão inativa após 30s sem sinal

# --- Debug / arquivos --------------------------------------------------------
DEBUG = True              # mostra janelas com anotações
LOG_INTERVAL_S = 1.0      # com DEBUG, imprime a posição da bola no máximo 1x por intervalo
SAVE_CALIBRATION = True
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CALIBRATION_FILE_1 = os.path.join(BASE_DIR, "camera1_calibration.npy")
CALIBRATION_FILE_2 = os.path.join(BASE_DIR, "camera2_calibration.npy")
