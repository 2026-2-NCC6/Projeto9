package com.techtennis.arena;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

import android.os.Bundle;
import android.util.Log;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;

import com.techtennis.arena.services.ApiService;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;

import java.io.IOException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.TimeUnit;

import okhttp3.OkHttpClient;
import retrofit2.Response;
import retrofit2.Retrofit;
import retrofit2.converter.gson.GsonConverterFactory;

/**
 * Integração real: ESTE teste roda DENTRO do celular e fala com o Flask do notebook pela rede
 * (WiFi), que por sua vez comanda o Arduino. Não use `adb reverse` ao rodar: o objetivo é exercitar o WiFi.
 *
 * Endereço do Flask (padrão http://192.168.1.100:5000), sobrescrevível:
 *   gradlew connectedDebugAndroidTest -Pandroid.testInstrumentationRunnerArguments.flaskUrl=http://<ip-do-servidor>:5000
 * Sem Arduino real (Flask simulado):  ... -Pandroid.testInstrumentationRunnerArguments.arduino=any
 *
 * ATENÇÃO: os testes de MÉDIO/DIFÍCIL movem os servos por alguns segundos. O laser (L) nunca é ligado.
 */
@RunWith(AndroidJUnit4.class)
public class FlaskWifiTest {

    private static final String TAG = "FlaskWifiTest";
    private static final String URL_PADRAO = "http://192.168.1.100:5000/";

    private ApiService api;
    private boolean exigirArduino;

    @Before
    public void preparar() {
        Bundle args = InstrumentationRegistry.getArguments();
        String url = args.getString("flaskUrl", URL_PADRAO);
        if (!url.endsWith("/")) url += "/";
        exigirArduino = !"any".equals(args.getString("arduino", "CONNECTED"));

        OkHttpClient client = new OkHttpClient.Builder()
                .connectTimeout(5, TimeUnit.SECONDS)
                .readTimeout(8, TimeUnit.SECONDS)
                .build();
        api = new Retrofit.Builder().baseUrl(url).client(client)
                .addConverterFactory(GsonConverterFactory.create()).build().create(ApiService.class);
        Log.i(TAG, "Flask em " + url);
    }

    /** Sempre deixa o laser parado e os servos no centro, mesmo se o teste falhar. */
    @After
    public void limpar() {
        try {
            api.pararJogo().execute();
        } catch (IOException ignored) {
            // Flask fora do ar: nada a limpar
        }
    }

    @Test
    public void flaskAcessivelPeloWifi() throws IOException {
        Response<ApiService.StatusAPI> r = api.getStatus().execute();
        assertTrue("Flask inacessível (firewall na porta 5000? mesma rede?): HTTP " + r.code(), r.isSuccessful());
        assertEquals("OK", r.body().status);
        if (exigirArduino) {
            assertEquals("Arduino deve estar conectado ao Flask", "CONNECTED", r.body().arduino);
        }
    }

    /** Métrica do projeto: latência < 200 ms na maioria das chamadas. */
    @Test
    public void latenciaDeIdaEVolta() throws IOException {
        List<Long> ms = new ArrayList<>();
        for (int i = 0; i < 30; i++) {
            long t0 = System.nanoTime();
            assertTrue(api.getStatus().execute().isSuccessful());
            ms.add((System.nanoTime() - t0) / 1_000_000);
        }
        Collections.sort(ms);
        long mediana = ms.get(ms.size() / 2);
        long p95 = ms.get((int) (ms.size() * 0.95) - 1);
        Log.i(TAG, "LATENCIA /status: mediana=" + mediana + "ms  p95=" + p95 + "ms  max=" + ms.get(ms.size() - 1) + "ms");
        assertTrue("mediana " + mediana + "ms (meta < 200ms)", mediana < 200);
        assertTrue("p95 " + p95 + "ms (meta < 500ms)", p95 < 500);
    }

    /** Comando somente-leitura ao Arduino ('?' mostra o menu; não move nada). */
    @Test
    public void comandoChegaAoArduinoEVoltaAResposta() throws IOException {
        Response<ApiService.RespostaAPI> r = api.enviarComando("?").execute();
        assertTrue(r.isSuccessful());
        assertEquals("OK", r.body().status);
        if (exigirArduino) {
            assertTrue("resposta do Arduino: " + r.body().resposta, r.body().resposta.contains("COMANDOS"));
        }
    }

    @Test
    public void nivelInvalidoRetorna400() throws IOException {
        Response<ApiService.JogoAPI> r = api.iniciarJogo(new ApiService.NivelBody("impossivel")).execute();
        assertEquals(400, r.code());
    }

    @Test
    public void facilCentralizaOLaser() throws Exception {
        Response<ApiService.JogoAPI> r = api.iniciarJogo(new ApiService.NivelBody("facil")).execute();
        assertTrue(r.isSuccessful());
        assertEquals("facil", r.body().nivel);
        Thread.sleep(1000);

        ApiService.LaserStatusAPI s = api.statusLaser().execute().body();
        assertTrue(s.laser_ativo);
        assertEquals("facil", s.nivel);
        assertEquals(Integer.valueOf(90), s.angulos.get("x"));
        assertEquals(Integer.valueOf(90), s.angulos.get("y"));
    }

    @Test
    public void medioMoveOLaserEmCirculo() throws Exception {
        assertTrue(api.iniciarJogo(new ApiService.NivelBody("medio")).execute().isSuccessful());
        Thread.sleep(2500);
        ApiService.LaserStatusAPI a = api.statusLaser().execute().body();
        Thread.sleep(1000);
        ApiService.LaserStatusAPI b = api.statusLaser().execute().body();

        assertTrue(a.laser_ativo && b.laser_ativo);
        assertEquals("medio", b.nivel);
        int dx = Math.abs(a.angulos.get("x") - b.angulos.get("x"));
        int dy = Math.abs(a.angulos.get("y") - b.angulos.get("y"));
        Log.i(TAG, "MEDIO: (" + a.angulos + ") -> (" + b.angulos + ")  modo=" + b.modo_laser);
        assertTrue("o laser deveria ter se movido em 1 s", dx + dy >= 5);
        // círculo de +-35 graus em X e +-25 em Y ao redor de 90 (com folga de 5 graus)
        for (ApiService.LaserStatusAPI s : new ApiService.LaserStatusAPI[]{a, b}) {
            assertTrue(s.angulos.get("x") >= 50 && s.angulos.get("x") <= 130);
            assertTrue(s.angulos.get("y") >= 60 && s.angulos.get("y") <= 120);
        }
    }

    @Test
    public void dificilMudaDeAlvoAoLongoDoTempo() throws Exception {
        assertTrue(api.iniciarJogo(new ApiService.NivelBody("dificil")).execute().isSuccessful());
        Set<String> alvos = new HashSet<>();
        for (int i = 0; i < 4; i++) {
            Thread.sleep(1300);
            ApiService.LaserStatusAPI s = api.statusLaser().execute().body();
            assertTrue(s.laser_ativo);
            int x = s.alvo.get("x"), y = s.alvo.get("y");
            assertTrue("alvo fora da faixa dos servos: " + x + "," + y, x >= 30 && x <= 150 && y >= 30 && y <= 150);
            alvos.add(x + "," + y);
        }
        Log.i(TAG, "DIFICIL alvos: " + alvos);
        assertTrue("o alvo do DIFÍCIL deveria mudar", alvos.size() >= 2);
    }

    @Test
    public void pararDevolveOLaserAoCentro() throws Exception {
        assertTrue(api.iniciarJogo(new ApiService.NivelBody("medio")).execute().isSuccessful());
        Thread.sleep(3000);
        assertTrue(api.pararJogo().execute().isSuccessful());
        Thread.sleep(1500);

        ApiService.LaserStatusAPI s = api.statusLaser().execute().body();
        assertFalse("o jogo deveria estar parado", s.laser_ativo);
        assertEquals(Integer.valueOf(90), s.angulos.get("x"));
        assertEquals(Integer.valueOf(90), s.angulos.get("y"));
    }

    /** Leitura pura: não usa POST /acerto porque isso marcaria a visão como ativa e desligaria o timer do app. */
    @Test
    public void contadorDeAcertosEhLegivel() throws IOException {
        Response<ApiService.AcertosAPI> r = api.getAcertos("teste-integracao").execute();
        assertTrue(r.isSuccessful());
        assertNotNull(r.body());
        assertTrue(r.body().total >= 0);
    }
}
