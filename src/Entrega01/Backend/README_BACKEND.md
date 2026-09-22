# Backend

Duas aplicações Python independentes:

- **`flask_server/`** — API HTTP que expõe o hardware (Arduino) para o app e recebe os acertos
  detectados pela visão computacional.
- **`vision/`** — Detecção de bola por visão computacional (OpenCV), que envia os acertos para a
  API acima.

## Tecnologias

- Python 3.9+
- [Flask](https://flask.palletsprojects.com/) — servidor HTTP
- [pyserial](https://pyserial.readthedocs.io/) — comunicação serial com o Arduino
- [OpenCV](https://opencv.org/) (`opencv-python`) — visão computacional
- [NumPy](https://numpy.org/) — cálculo numérico / calibração de câmera
- [Requests](https://requests.readthedocs.io/) — cliente HTTP (visão → API)

## Pré-requisitos

- Python 3.9 ou superior instalado
- Arduino conectado por USB (para a API controlar o hardware de verdade; sem ele a API roda em
  modo simulado)
- 1 ou 2 webcams USB (para a visão computacional)

## Setup e execução — `flask_server`

```bash
cd flask_server
pip install -r requirements.txt
python api.py                 # tenta abrir a porta COM/serial padrão; sem Arduino, roda simulado
python api.py --porta COM5    # especificar outra porta serial
python api.py --simular       # força modo simulado, sem tentar abrir o Arduino
```

Por padrão o servidor escuta em `0.0.0.0:5000` (acessível por outros dispositivos na mesma rede,
como o celular rodando o app).

### Endpoints principais

| Método | Rota | Função |
|---|---|---|
| GET | `/status` | Status do servidor, do Arduino e da visão |
| GET | `/comando?cmd=X` | Envia um comando de 1 caractere ao Arduino |
| POST | `/jogo/iniciar` | Inicia uma partida (`{"nivel": "facil\|medio\|dificil"}`) — controla o laser automaticamente |
| POST | `/jogo/parar` | Encerra a partida e centraliza o laser |
| POST | `/jogo/modo-manual` | Move o laser para uma posição específica (`{"x": .., "y": ..}`) |
| GET | `/laser/status` | Nível atual, alvo e posição estimada do laser |
| POST | `/acerto` | Registra um acerto (chamado pelo módulo de visão) |
| POST | `/visao/heartbeat` | Sinal de que o módulo de visão está ativo |
| GET | `/acertos?userID=X` | Total de acertos registrados para um usuário |

### Testes

```bash
cd flask_server
python -m unittest teste_laser_controller -v
```

## Setup e execução — `vision`

```bash
cd vision
pip install -r requirements.txt
python main.py --listar              # lista as câmeras disponíveis
python main.py --test --debug        # modo de teste com 1 câmera, sem depender da API
python main.py                       # modo normal, com as 2 câmeras da montagem física
```

Mais detalhes de uso (teclas, opções de linha de comando, calibração) estão no `README.md` dentro
da própria pasta `vision/`.

### Testes

```bash
cd vision
python -m unittest discover -p "test_*.py" -v
```
