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
# Faixas medidas comparando recortes reais de BOLA x PISO (dataset/training/, duas webcams USB, luz
# de ambiente). A saturação sozinha não separa bem os dois (bola e piso se sobrepõem bastante em S).
# O separador limpo é o BRILHO (V): a bola sai bem superexposta/estourada (V ~186-255, mediana 255)
# porque é clara e reflexiva, enquanto o piso de madeira fica bem mais escuro (V ~131-173). H cobre
# a faixa amarelo-esverdeada real da bola (mediana ~55-90) — mais larga que "amarelo puro" porque a
# bola de tênis é genuinamente amarelo-esverdeada, não amarela pura.
# Atenção: o piso de origem V é específico da iluminação desta sala — ao levar pra outro ambiente
# (quadra, outra luz), meça de novo (script de debug: comparar recorte da bola x fundo em HSV) antes
# de confiar nestes números.
YELLOW_LOWER = (45, 15, 180)
YELLOW_UPPER = (105, 255, 255)
GREEN_LOWER = (80, 25, 180)   # mesmo V mínimo do amarelo: sem isso, um V baixo deixava passar pontos do piso
GREEN_UPPER = (120, 255, 255)

BALL_MIN_AREA = 50        # px²: abaixo disso é ruído
# 10000 rejeitava a própria bola quando ela aparece perto da câmera (medido: ~14400px² a ~35cm da
# lente em 1280x720). 60000px² ~ bola ocupando até ~1/4 da largura do frame; ainda barra reflexos
# grandes e disformes, que o filtro de "fill" (redondeza) abaixo já rejeita de qualquer forma.
BALL_MAX_AREA = 60000     # px²: acima disso não é a bola
BALL_MIN_RADIUS = 20      # px: abaixo disso são quase sempre pontos de ruído na textura do piso (medido)
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
