package com.techtennis.arena.services;

import java.util.Map;

import retrofit2.Call;
import retrofit2.http.Body;
import retrofit2.http.GET;
import retrofit2.http.POST;
import retrofit2.http.Query;

/** Endpoints da API Flask (flask_server/api.py) + modelos JSON (Gson). */
public interface ApiService {

    @GET("status")
    Call<StatusAPI> getStatus();

    @GET("comando")
    Call<RespostaAPI> enviarComando(@Query("cmd") String comando);

    /** Total de acertos que a visão registrou para o usuário. */
    @GET("acertos")
    Call<AcertosAPI> getAcertos(@Query("userID") String userID);

    /** Avisa o Flask qual nível começou: ele passa a mover o laser sozinho. */
    @POST("jogo/iniciar")
    Call<JogoAPI> iniciarJogo(@Body NivelBody body);

    /** Fim de partida: o Flask para o laser e volta ao centro. */
    @POST("jogo/parar")
    Call<JogoAPI> pararJogo();

    /** Nível, alvo e posição estimada dos servos (o laser automático). */
    @GET("laser/status")
    Call<LaserStatusAPI> statusLaser();

    @POST("acerto")
    Call<RespostaAPI> registrarAcerto(@Body AcertoData data);

    class StatusAPI {
        public String status;   // "OK"
        public String arduino;  // "CONNECTED", "SIMULATED" ou "DISCONNECTED"
        public boolean visao;   // módulo de visão computacional ativo
        public long timestamp;
    }

    class RespostaAPI {
        public String comando;
        public String resposta;
        public String status;
    }

    class AcertosAPI {
        public String userID;
        public int total;
    }

    class NivelBody {
        public String nivel;   // "facil", "medio" ou "dificil"

        public NivelBody(String nivel) {
            this.nivel = nivel;
        }
    }

    class JogoAPI {
        public String status;
        public String message;
        public String nivel;
        public String modo_laser;   // "abs", "incremental" ou "simulado"
    }

    class LaserStatusAPI {
        public String status;
        public boolean laser_ativo;
        public String nivel;
        public String modo_laser;                 // "abs", "incremental" ou "simulado"
        public Map<String, Integer> alvo;         // onde o laser DEVERIA estar: {"x":..,"y":..}
        public Map<String, Integer> angulos;      // onde os servos estão (estimado)
        public Double decorrido_s;                // segundos desde o início da partida; null se parado
    }

    class AcertoData {
        public String userID;
        public boolean acertou;
        public int x, y, z;
    }
}
