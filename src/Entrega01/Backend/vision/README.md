# Smart Tennis Arena — Visão Computacional

Duas webcams → detecção da bola por cor (HSV) → posição 3D → acerto → `POST /acerto` no Flask.
O app Android consulta o Flask durante a partida e soma os acertos.

## Executar

```bash
pip install -r requirements.txt
python test_without_cameras.py -v        # 24 testes, sem câmeras
python ../flask_server/api.py            # em outro terminal (Flask + Arduino)
python main.py                           # com as 2 câmeras conectadas
```

Teclas (com `DEBUG = True`): **q** sai, **c** recalibra. Sem janelas: Ctrl+C.

Se as câmeras estiverem trocadas, inverta `CAMERA1_ID` / `CAMERA2_ID` em `config.py`.

## Sistema de coordenadas (mundo)

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

## Limitações conhecidas (leia antes de testar com câmeras)

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
| `camera_manager.py` | 2 câmeras em threads, sempre o frame mais recente |
| `camera_calibration.py` | homografia pixel ↔ mundo |
| `ball_detector.py` | máscara amarelo OU verde, maior blob |
| `hit_detector.py` | triangulação 3D + acerto + debounce |
| `flask_client.py` | POST /acerto (em thread) + heartbeat |
| `main.py` | loop principal a 30 fps |
| `test_without_cameras.py` | testes com frames sintéticos |

## Teste rápido com 1 webcam (só para validar a detecção da bola)

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

Com 1 câmera só existem X e Z (vista de cima). O círculo azul "LASER ALVO" mostra onde segurar a bola
para dar "ACERTO SIMULADO"; o raio do círculo é a tolerância.

### O que foi medido na webcam do notebook
- Sem bola na cena, a versão anterior do detector "achava" uma bola em 36% dos frames (mancha bege esparsa
  na parede). O filtro de redondeza (`BALL_MIN_FILL`) levou isso a 0%.
- O FPS depende da **luz**, não do código: com pouca luz a exposição automática da webcam sobe e ela cai
  para ~15 FPS (a detecção custa ~16 ms/frame, teto de ~60 FPS). Com boa iluminação chegou a ~28 FPS.
  Na arena, ilumine bem a cena.
