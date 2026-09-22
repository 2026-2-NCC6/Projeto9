package com.techtennis.arena;

import android.animation.ValueAnimator;
import android.content.Intent;
import android.content.res.ColorStateList;
import android.media.AudioAttributes;
import android.media.SoundPool;
import android.os.Bundle;
import android.os.CountDownTimer;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.View;
import android.widget.TextView;

import androidx.appcompat.app.AppCompatActivity;

import com.google.android.material.button.MaterialButton;
import com.google.android.material.progressindicator.LinearProgressIndicator;
import com.techtennis.arena.services.ApiService;
import com.techtennis.arena.services.SerialService;

import java.util.Locale;

/**
 * Partida de 60s. Fontes de acerto, por prioridade:
 *  1. Visão computacional (Flask /acertos) quando o módulo de visão está ativo;
 *  2. Timer automático (fallback) quando a visão não está ativa.
 * Cada acerto aciona buzzer (B) e LED (E) no Arduino via Flask.
 */
public class GameActivity extends AppCompatActivity {

    private static final String TAG = "GameActivity";
    private static final int DURACAO_SEGUNDOS = 60;
    private static final int PONTOS_POR_ACERTO = 10;
    private static final long POLL_MS = 1000;

    private int nivel;
    private int score = 0;
    private int acertos = 0;
    private int tempoRestante = DURACAO_SEGUNDOS;
    private boolean laserLigado = false;
    private boolean finalizado = false;
    private boolean laserParado = false;   // já mandou /jogo/parar
    private int intervaloAcertoAutomatico;
    private int ultimoSegundoComAcerto = -1;
    private int baselineVisao = -1; // total de acertos da visão no início da partida

    private CountDownTimer timer;
    private SoundPool soundPool;
    private int somAcerto;
    private SerialService serialService;
    private final Handler handler = new Handler(Looper.getMainLooper());

    private TextView timerText, scoreText, acertosText, acertoFlash;
    private LinearProgressIndicator progresso;
    private MaterialButton btnLigarLaser;
    private ColorStateList tintLigarOriginal;

    private final Runnable pollVisao = new Runnable() {
        @Override
        public void run() {
            if (finalizado) return;
            if (GlobalUser.visaoAtiva) consultarVisao();
            handler.postDelayed(this, POLL_MS);
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_game);

        nivel = getIntent().getIntExtra("nivel", 1);
        intervaloAcertoAutomatico = intervaloPorNivel(nivel);
        serialService = GlobalUser.getSerialService(this);

        timerText = findViewById(R.id.timer_text);
        scoreText = findViewById(R.id.score_text);
        acertosText = findViewById(R.id.acertos_text);
        acertoFlash = findViewById(R.id.acerto_flash);
        progresso = findViewById(R.id.tempo_progress);
        btnLigarLaser = findViewById(R.id.btn_ligar_laser);
        tintLigarOriginal = btnLigarLaser.getBackgroundTintList();

        ((TextView) findViewById(R.id.nivel_text)).setText(emojiNivel(nivel) + "  " + nomeNivel(nivel).toUpperCase() + " • Nível " + nivel);
        timerText.setText(formatarTempo(DURACAO_SEGUNDOS));

        iniciarSom();

        setupMovimento(R.id.btn_cima, "W");
        setupMovimento(R.id.btn_baixo, "S");
        setupMovimento(R.id.btn_esq, "A");
        setupMovimento(R.id.btn_dir, "D");
        if (nivel >= 2) desativarDirecional(); // MÉDIO/DIFÍCIL: o laser se move sozinho
        btnLigarLaser.setOnClickListener(v -> ligarLaser());
        findViewById(R.id.btn_desligar_laser).setOnClickListener(v -> desligarLaser());
        findViewById(R.id.btn_finalizar).setOnClickListener(v -> finalizarJogo());

        atualizarStatusVisao();
        serialService.enviarComando("@"); // inicia a sessão no Arduino
        serialService.iniciarJogo(nomeApi(nivel)); // o Flask passa a mover o laser conforme o nível
        iniciarTimer();
        handler.postDelayed(pollVisao, POLL_MS);
    }

    private void iniciarSom() {
        AudioAttributes aa = new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_GAME)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build();
        soundPool = new SoundPool.Builder().setMaxStreams(1).setAudioAttributes(aa).build();
        somAcerto = soundPool.load(this, R.raw.acerto, 1);
    }

    /** Descobre se a visão está ativa (define de onde vêm os acertos). */
    private void atualizarStatusVisao() {
        serialService.verificarStatus(new SerialService.Resultado<ApiService.StatusAPI>() {
            @Override
            public void onOk(ApiService.StatusAPI s) {
                GlobalUser.visaoAtiva = s.visao;
                Log.d(TAG, "Visão ativa: " + s.visao);
            }

            @Override
            public void onErro(String mensagem) {
                GlobalUser.visaoAtiva = false;
                Log.w(TAG, "Flask indisponível, acertos pelo timer: " + mensagem);
            }
        });
    }

    private void iniciarTimer() {
        timer = new CountDownTimer(DURACAO_SEGUNDOS * 1000L, 1000) {
            @Override
            public void onTick(long millisUntilFinished) {
                // arredonda: o primeiro tick chega um pouco antes de 60000ms
                tempoRestante = (int) Math.round(millisUntilFinished / 1000.0);
                atualizarRelogio();
                verificarAcertoAutomatico(DURACAO_SEGUNDOS - tempoRestante);
            }

            @Override
            public void onFinish() {
                tempoRestante = 0;
                atualizarRelogio();
                verificarAcertoAutomatico(DURACAO_SEGUNDOS); // onTick não dispara em 0s
                finalizarJogo();
            }
        }.start();
    }

    /** Relógio mm:ss e barra de progresso que vai de verde para amarelo e vermelho. */
    private void atualizarRelogio() {
        timerText.setText(formatarTempo(tempoRestante));
        progresso.setProgressCompat(tempoRestante, true);
        int cor = tempoRestante > 30 ? R.color.md_theme_primary
                : tempoRestante > 10 ? R.color.md_theme_secondary_dark : R.color.md_theme_error;
        progresso.setIndicatorColor(getColor(cor));
    }

    static String formatarTempo(int segundos) {
        return String.format(Locale.getDefault(), "⏱ %02d:%02d", segundos / 60, segundos % 60);
    }

    /** FALLBACK: só conta se a visão não estiver ativa. */
    private void verificarAcertoAutomatico(int decorrido) {
        if (GlobalUser.visaoAtiva) return;
        if (decorrido > 0 && decorrido % intervaloAcertoAutomatico == 0 && decorrido != ultimoSegundoComAcerto) {
            ultimoSegundoComAcerto = decorrido;
            registrarAcerto("timer");
        }
    }

    /** REAL: soma os acertos que a visão registrou no Flask desde o início da partida. */
    private void consultarVisao() {
        serialService.consultarAcertos(GlobalUser.userID, new SerialService.Resultado<ApiService.AcertosAPI>() {
            @Override
            public void onOk(ApiService.AcertosAPI r) {
                if (finalizado) return;
                if (baselineVisao < 0) {
                    baselineVisao = r.total;
                    return;
                }
                for (int i = baselineVisao; i < r.total; i++) registrarAcerto("visão");
                baselineVisao = Math.max(baselineVisao, r.total);
            }

            @Override
            public void onErro(String mensagem) {
                Log.w(TAG, "Falha ao consultar acertos: " + mensagem);
            }
        });
    }

    private void registrarAcerto(String origem) {
        int anterior = score;
        acertos++;
        score += PONTOS_POR_ACERTO;
        acertosText.setText("Acertos: " + acertos);
        animarPontos(anterior, score);
        mostrarFlashDeAcerto();

        soundPool.play(somAcerto, 1f, 1f, 0, 0, 1f);
        Nav.vibrar(this, 60);
        serialService.enviarComando("B"); // buzzer (BIP)
        serialService.enviarComando("E"); // LED
        Log.d(TAG, "Acerto (" + origem + ") | acertos=" + acertos + " score=" + score);
    }

    /** Os pontos "rolam" do valor antigo ao novo. */
    private void animarPontos(int de, int para) {
        ValueAnimator va = ValueAnimator.ofInt(de, para);
        va.setDuration(300);
        va.addUpdateListener(a -> scoreText.setText(a.getAnimatedValue() + " pts"));
        va.start();
    }

    /** Selo verde "ACERTO! +10" que aparece e some. */
    private void mostrarFlashDeAcerto() {
        acertoFlash.setText("ACERTO!  +" + PONTOS_POR_ACERTO + " pts ✓");
        acertoFlash.animate().cancel();
        acertoFlash.setScaleX(0.8f);
        acertoFlash.setScaleY(0.8f);
        acertoFlash.animate().alpha(1f).scaleX(1f).scaleY(1f).setStartDelay(0).setDuration(150)
                .withEndAction(() -> acertoFlash.animate().alpha(0f).setStartDelay(600).setDuration(300).start())
                .start();
    }

    private void setupMovimento(int id, String comando) {
        MaterialButton botao = findViewById(id);
        botao.setOnClickListener(v -> {
            serialService.enviarComando(comando);
            ColorStateList original = botao.getBackgroundTintList();
            botao.setBackgroundTintList(ColorStateList.valueOf(getColor(R.color.md_theme_primary_dark)));
            handler.postDelayed(() -> botao.setBackgroundTintList(original), 250);
        });
    }

    /** Nos níveis automáticos o direcional manual brigaria com o movimento do laser. */
    private void desativarDirecional() {
        for (int id : new int[]{R.id.btn_cima, R.id.btn_baixo, R.id.btn_esq, R.id.btn_dir}) {
            View b = findViewById(id);
            b.setEnabled(false);
            b.setAlpha(0.35f);
        }
        ((TextView) findViewById(R.id.nivel_text)).append("  •  laser automático");
    }

    /** Para o laser no Flask uma única vez (fim normal, back ou tela destruída). */
    private void pararLaser() {
        if (laserParado) return;
        laserParado = true;
        serialService.pararJogo();
    }

    private void ligarLaser() {
        if (laserLigado) return;
        laserLigado = true;
        btnLigarLaser.setBackgroundTintList(ColorStateList.valueOf(getColor(R.color.md_theme_success)));
        serialService.enviarComando("L"); // "L" alterna o laser no Arduino
    }

    private void desligarLaser() {
        if (!laserLigado) return;
        laserLigado = false;
        btnLigarLaser.setBackgroundTintList(tintLigarOriginal);
        serialService.enviarComando("L");
    }

    private void finalizarJogo() {
        if (finalizado) return;
        finalizado = true;
        if (timer != null) timer.cancel();
        handler.removeCallbacksAndMessages(null);

        if (laserLigado) serialService.enviarComando("L"); // não deixa o laser aceso
        serialService.enviarComando("#"); // pausa a sessão no Arduino
        pararLaser();

        Intent intent = new Intent(this, ResultActivity.class);
        intent.putExtra("score", score);
        intent.putExtra("acertos", acertos);
        intent.putExtra("nivel", nivel);
        intent.putExtra("tempo", DURACAO_SEGUNDOS - tempoRestante);
        Nav.fade(this, intent);
        finish();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        finalizado = true;
        if (timer != null) timer.cancel();
        handler.removeCallbacksAndMessages(null);
        pararLaser();   // saiu com "voltar" sem finalizar: não deixa o laser andando
        if (soundPool != null) {
            soundPool.release();
            soundPool = null;
        }
    }

    /** FÁCIL: 10s, MÉDIO: 5s, DIFÍCIL: 2s entre acertos automáticos. */
    static int intervaloPorNivel(int nivel) {
        return nivel == 1 ? 10 : (nivel == 2 ? 5 : 2);
    }

    /** Pontuação máxima do modo automático em 60s (6, 12 ou 30 acertos x 10). */
    static int scoreMaximo(int nivel) {
        return (DURACAO_SEGUNDOS / intervaloPorNivel(nivel)) * PONTOS_POR_ACERTO;
    }

    static String nomeNivel(int nivel) {
        switch (nivel) {
            case 1: return "Fácil";
            case 3: return "Difícil";
            default: return "Médio";
        }
    }

    /** Nome do nível como o Flask espera. */
    static String nomeApi(int nivel) {
        return nivel == 1 ? "facil" : nivel == 3 ? "dificil" : "medio";
    }

    static String emojiNivel(int nivel) {
        return nivel == 1 ? "🟢" : nivel == 3 ? "🔴" : "🟡";
    }
}
