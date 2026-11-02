# Smart Tennis Arena — Visão Computacional

Duas webcams → detecção da bola → posição → acerto → `POST /acerto` no Flask.
O app Android consulta o Flask durante a partida e soma os acertos.

Existem dois detectores de bola neste módulo:

1. **Detecção por cor (HSV)** — `main.py` + `ball_detector.py`/`hit_detector.py`. Mais simples,
   não precisa de treino, mas sensível a iluminação e a outros objetos da mesma cor.
2. **YOLOv8 treinado (`scripts/`)** — detector por rede neural, treinado com frames reais
   capturados das próprias câmeras da montagem. Mais robusto, usado na versão atual do projeto
   (miniatura de mesa).

## Detecção por cor — executar

```bash
pip install -r requirements.txt
python test_without_cameras.py -v        # 24 testes, sem câmeras
python ../flask_server/api.py            # em outro terminal (Flask + Arduino)
python main.py                           # com as 2 câmeras conectadas
```

Teclas (com `DEBUG = True`): **q** sai, **c** recalibra. Sem janelas: Ctrl+C.

Se as câmeras estiverem trocadas, inverta `CAMERA1_ID` / `CAMERA2_ID` em `config.py`.

## Pipeline YOLOv8 (`scripts/`)

Fluxo para treinar e rodar o detector por rede neural, do zero:

```bash
cd scripts

# 1. Ver quais IDs de câmera o sistema está enxergando
python test_cameras.py

# 2. Gravar frames de uma sessão de jogo (grava nas duas câmeras ao mesmo tempo)
python capture_game_live.py --cam0 0 --cam1 1 --destino training/mesa

# 3. Rotular automaticamente os frames novos (movimento + cor da bola)
python rotular_por_movimento.py --pasta ../../dataset/training/mesa/camera0 --desde <numero_do_primeiro_frame_novo>
python rotular_por_movimento.py --pasta ../../dataset/training/mesa/camera1 --desde <numero_do_primeiro_frame_novo>

# 4. Treinar (continua do melhor checkpoint existente daquele domínio, se houver)
python train_yolo_quadra.py --dominio mesa --epocas 30

# 5. Testar o modelo treinado em tempo real com as duas câmeras
python detect_impact_live.py --cam0 0 --cam1 1
```

`--dominio` separa cenários diferentes (`quadra` = quadra real, `mesa` = miniatura de mesa): cada
um guarda seu próprio dataset (`dataset/training/<dominio>/`) e seu próprio treino
(`runs/detect/ball_detector_<dominio>/`), para um não poluir o outro.

Dataset e pesos treinados (`dataset/`, `runs/`, `*.pt`) **não fazem parte deste repositório** —
são grandes e são gerados localmente seguindo os passos acima.

## Sistema de coordenadas (mundo) — detector por cor

| Eixo | Significado | Origem |
|------|-------------|--------|
| X | lateral | 0 a 3 m (centro do gol = 1,5) |
| Y | altura | 0 = chão |
| Z | profundidade | 0 = frente do gol; negativo = para dentro/atrás |

- **Câmera 1 (cima)** enxerga **X e Z**.
- **Câmera 2 (lado)** enxerga **Z e Y**.
- Z é medido pelas duas; a triangulação usa a média.

Laser alvo: X = 1,5 · Y = 1,2 · Z = −1,0. Tolerância: ±5 cm em cada eixo (`HIT_TOLERANCE`).

## Como o Flask e o app enxergam a visão

- `POST /acerto` com `{"source":"vision","position":{X,Y,Z},"timestamp":...}` — sem `userID`;
  o acerto vale para quem estiver jogando (o app soma o contador geral ao consultar `/acertos`).
- `POST /visao/heartbeat` a cada 5 s — mantém `"visao": true` no `/status`. **Sem isso** o Flask
  considera a visão inativa após 30 s sem acerto e o app volta a gerar acertos pelo timer.

## Limitações conhecidas do detector por cor (leia antes de testar com câmeras)

1. **Calibração é provisória.** Ela assume que os 4 cantos de cada frame correspondem à região
   definida em `CAM1_*_RANGE` / `CAM2_*_RANGE` (`config.py`), com a câmera de frente para o plano.
   Câmera inclinada ou enquadramento diferente → posições erradas. Para precisão real, calibre com
   pontos marcados no chão/parede e medidos.
2. **Orientação assumida:** câmera 1 — topo da imagem = fundo do gol; câmera 2 — esquerda da
   imagem = fundo do gol. Se estiver invertido, troque a ordem nos `*_RANGE`.
3. **Laser fixo.** O laser se move com os servos, mas `LASER_X/Y/Z` é constante. O acerto só faz
   sentido se o servo estiver na posição de referência.
4. **Tolerância de ±5 cm nos 3 eixos é muito apertada** (a bola tem 6,5 cm e há erro de detecção
   e de calibração). Se nunca pontuar, aumente `HIT_TOLERANCE`.
5. **Faixa verde do HSV (H 80–120)** cobre também ciano/azul: objetos azuis podem ser detectados
   como bola. A bola amarelo-esverdeada costuma ficar em H ≈ 25–45. Ajuste em `config.py` se houver
   falsos positivos.
6. Só há acerto quando **as duas câmeras** veem a bola no mesmo frame.
7. A calibração salva (`camera*_calibration.npy`) só vale para a resolução com que foi gerada;
   o `main.py` detecta a troca e recalibra sozinho.

## Arquivos

| Arquivo | Função |
|---------|--------|
| `config.py` | medidas da arena, HSV, URLs, tolerâncias |
| `camera_manager.py` | abre as câmeras (com fallback de backend no Windows) e as mantém em threads |
| `camera_calibration.py` | homografia pixel ↔ mundo |
| `ball_detector.py` | máscara amarelo OU verde, maior blob |
| `hit_detector.py` | triangulação 3D + acerto + debounce |
| `flask_client.py` | POST /acerto (em thread) + heartbeat |
| `main.py` | loop principal a 30 fps (detector por cor) |
| `test_without_cameras.py` | testes com frames sintéticos |
| `scripts/test_cameras.py` | mostra as câmeras disponíveis lado a lado, com o ID de cada uma |
| `scripts/capture_game_live.py` | grava frames das duas câmeras durante uma sessão de jogo |
| `scripts/rotular_por_movimento.py` | rotula automaticamente os frames gravados (MOG2 + cor) |
| `scripts/train_yolo_quadra.py` | treina o YOLOv8 por domínio (`quadra` ou `mesa`) |
| `scripts/detect_impact_live.py` | roda o modelo treinado em tempo real e detecta impactos no gol |

## Teste rápido com 1 webcam (só para validar a detecção da bola por cor)

O projeto final usa **2 webcams USB**. Este modo existe para testar a detecção com uma câmera só
(a do notebook serve). Ele **não fala com o Flask** (senão o app acharia que a visão está ativa) e
**não grava calibração** (a das 2 câmeras da arena não é sobrescrita).

```bash
python main.py --listar                    # quais câmeras abrem
python main.py --test --debug              # janela com círculo da bola, alvo e FPS
python main.py --test --headless --segundos 10   # sem janela: só o resumo no console
```

Teclas: **q** sai · **c** recalibra · **s** screenshot · **d** liga/desliga anotações ·
**h** sliders HSV ao vivo (mostra a máscara) · **p** imprime as faixas HSV para colar no `config.py`.

Opções: `--camera N`, `--fps-limit N`, `--tolerancia METROS`, `--exposicao -5`.
