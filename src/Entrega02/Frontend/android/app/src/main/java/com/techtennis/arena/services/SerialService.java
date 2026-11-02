package com.techtennis.arena.services;

import android.util.Log;

import java.util.concurrent.TimeUnit;

import okhttp3.OkHttpClient;
import retrofit2.Call;
import retrofit2.Callback;
import retrofit2.Response;
import retrofit2.Retrofit;
import retrofit2.converter.gson.GsonConverterFactory;

/**
 * Fala com o Arduino via API Flask do notebook (HTTP). Todas as chamadas são assíncronas;
 * os callbacks rodam na thread principal.
 */
public class SerialService {

    private static final String TAG = "SerialService";

    /** Callback simples de sucesso/erro. */
    public interface Resultado<T> {
        void onOk(T resposta);
        void onErro(String mensagem);
    }

    private ApiService api;
    private volatile boolean conectado = false;

    public SerialService(String baseUrl) {
        configurar(baseUrl);
    }

    /** (Re)cria o cliente HTTP para a URL informada. Retorna false se a URL for inválida. */
    public synchronized boolean configurar(String baseUrl) {
        try {
            String url = baseUrl.trim();
            if (!url.startsWith("http://") && !url.startsWith("https://")) url = "http://" + url;
            if (!url.endsWith("/")) url += "/";

            OkHttpClient client = new OkHttpClient.Builder()
                    .connectTimeout(3, TimeUnit.SECONDS)
                    .readTimeout(5, TimeUnit.SECONDS)
                    .build();
            api = new Retrofit.Builder()
                    .baseUrl(url)
                    .client(client)
                    .addConverterFactory(GsonConverterFactory.create())
                    .build()
                    .create(ApiService.class);
            conectado = false;
            return true;
        } catch (IllegalArgumentException e) {
            Log.e(TAG, "URL inválida: " + baseUrl, e);
            return false;
        }
    }

    public boolean isConnected() {
        return conectado;
    }

    /** GET /status: atualiza o estado de conexão. */
    public void verificarStatus(Resultado<ApiService.StatusAPI> cb) {
        api.getStatus().enqueue(new Callback<ApiService.StatusAPI>() {
            @Override
            public void onResponse(Call<ApiService.StatusAPI> call, Response<ApiService.StatusAPI> r) {
                if (r.isSuccessful() && r.body() != null && "OK".equals(r.body().status)) {
                    conectado = true;
                    cb.onOk(r.body());
                } else {
                    conectado = false;
                    cb.onErro("Flask respondeu " + r.code());
                }
            }

            @Override
            public void onFailure(Call<ApiService.StatusAPI> call, Throwable t) {
                conectado = false;
                cb.onErro(t.getMessage());
            }
        });
    }

    /** GET /comando?cmd=X: repassa 1 caractere ao Arduino. */
    public void enviarComando(String comando, Resultado<ApiService.RespostaAPI> cb) {
        api.enviarComando(comando).enqueue(new Callback<ApiService.RespostaAPI>() {
            @Override
            public void onResponse(Call<ApiService.RespostaAPI> call, Response<ApiService.RespostaAPI> r) {
                if (r.isSuccessful() && r.body() != null) {
                    Log.d(TAG, "Arduino recebeu: " + comando + " -> " + r.body().resposta);
                    if (cb != null) cb.onOk(r.body());
                } else {
                    Log.e(TAG, "Flask recusou '" + comando + "': " + r.code());
                    if (cb != null) cb.onErro("Flask respondeu " + r.code());
                }
            }

            @Override
            public void onFailure(Call<ApiService.RespostaAPI> call, Throwable t) {
                Log.e(TAG, "Erro ao conectar Flask", t);
                conectado = false;
                if (cb != null) cb.onErro(t.getMessage());
            }
        });
    }

    /** Versão "dispara e esquece" (só registra no log). */
    public void enviarComando(String comando) {
        enviarComando(comando, null);
    }

    /** POST /jogo/iniciar: o Flask começa o movimento automático do laser. Falhas só vão para o log. */
    public void iniciarJogo(String nivel) {
        api.iniciarJogo(new ApiService.NivelBody(nivel)).enqueue(new Callback<ApiService.JogoAPI>() {
            @Override
            public void onResponse(Call<ApiService.JogoAPI> call, Response<ApiService.JogoAPI> r) {
                Log.d(TAG, "Jogo iniciado no Flask (" + nivel + "): " + r.code()
                        + (r.body() != null ? " laser=" + r.body().modo_laser : ""));
            }

            @Override
            public void onFailure(Call<ApiService.JogoAPI> call, Throwable t) {
                Log.w(TAG, "Não avisou o Flask do início do jogo: " + t.getMessage());
            }
        });
    }

    /** POST /jogo/parar: para o laser. O Flask também para sozinho após 70 s. */
    public void pararJogo() {
        api.pararJogo().enqueue(new Callback<ApiService.JogoAPI>() {
            @Override
            public void onResponse(Call<ApiService.JogoAPI> call, Response<ApiService.JogoAPI> r) {
                Log.d(TAG, "Jogo parado no Flask: " + r.code());
            }

            @Override
            public void onFailure(Call<ApiService.JogoAPI> call, Throwable t) {
                Log.w(TAG, "Não avisou o Flask do fim do jogo: " + t.getMessage());
            }
        });
    }

    /** GET /acertos?userID=X: total de acertos da visão para o usuário. */
    public void consultarAcertos(String userID, Resultado<ApiService.AcertosAPI> cb) {
        api.getAcertos(userID).enqueue(new Callback<ApiService.AcertosAPI>() {
            @Override
            public void onResponse(Call<ApiService.AcertosAPI> call, Response<ApiService.AcertosAPI> r) {
                if (r.isSuccessful() && r.body() != null) cb.onOk(r.body());
                else cb.onErro("Flask respondeu " + r.code());
            }

            @Override
            public void onFailure(Call<ApiService.AcertosAPI> call, Throwable t) {
                cb.onErro(t.getMessage());
            }
        });
    }
}
