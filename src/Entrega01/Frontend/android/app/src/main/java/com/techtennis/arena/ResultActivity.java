package com.techtennis.arena;

import android.animation.ValueAnimator;
import android.content.Intent;
import android.os.Bundle;
import android.util.Log;
import android.view.View;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

import com.google.firebase.firestore.DocumentReference;
import com.google.firebase.firestore.DocumentSnapshot;
import com.google.firebase.firestore.FieldValue;
import com.google.firebase.firestore.FirebaseFirestore;
import com.google.firebase.firestore.SetOptions;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/** Resultado da partida: análise, histórico no Firestore e compartilhamento. */
public class ResultActivity extends AppCompatActivity {

    private static final String TAG = "ResultActivity";

    private int score, acertos, nivel, tempo;
    private double aproveitamento; // score / máximo do nível (0 a 1+)

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_result);

        Intent in = getIntent();
        score = in.getIntExtra("score", 0);
        acertos = in.getIntExtra("acertos", 0);
        nivel = in.getIntExtra("nivel", 1);
        tempo = in.getIntExtra("tempo", 0);
        aproveitamento = (double) score / GameActivity.scoreMaximo(nivel);

        boolean boaPartida = aproveitamento >= 0.5;
        ((TextView) findViewById(R.id.titulo_resultado)).setText(boaPartida ? "PARABÉNS!" : "BOM TREINO!");
        ((TextView) findViewById(R.id.acertos_text)).setText("Acertos: " + acertos);
        ((TextView) findViewById(R.id.tempo_text)).setText("Tempo: " + tempo + "s");
        ((TextView) findViewById(R.id.taxa_text)).setText(
                "Aproveitamento: " + Math.min(100, Math.round(aproveitamento * 100)) + "% do máximo");
        ((TextView) findViewById(R.id.nivel_final)).setText("Nível: " + getNomeNivel(nivel));
        mostrarAnalise();

        animarPontos();
        animarEntradaDaAnalise();
        if (boaPartida) {
            com.techtennis.arena.ConfettiView confete = findViewById(R.id.confetti);
            confete.iniciar();
        }

        salvarResultado();

        findViewById(R.id.btn_novo).setOnClickListener(v -> voltarMenu());
        findViewById(R.id.btn_historico_res).setOnClickListener(v ->
                Nav.subir(this, new Intent(this, HistoricoActivity.class)));
        findViewById(R.id.btn_compartilhar).setOnClickListener(v -> compartilharResultado());
    }

    /** Pontuação sobe de 0 até o valor final. */
    private void animarPontos() {
        TextView scoreFinal = findViewById(R.id.score_final);
        ValueAnimator va = ValueAnimator.ofInt(0, score);
        va.setDuration(score == 0 ? 1 : 900);
        va.addUpdateListener(a -> scoreFinal.setText("🏆 " + a.getAnimatedValue() + " PONTOS 🏆"));
        va.start();
    }

    private void animarEntradaDaAnalise() {
        View card = findViewById(R.id.card_analise);
        card.setAlpha(0f);
        card.setTranslationY(60f);
        card.animate().alpha(1f).translationY(0f).setStartDelay(400).setDuration(400).start();
    }

    /** Faixas relativas ao máximo do nível (FÁCIL 60, MÉDIO 120, DIFÍCIL 300). */
    private void mostrarAnalise() {
        String[] titulos;
        switch (nivel) {
            case 1:
                titulos = new String[]{"🏆 EXCELENTE! Você domina o nível fácil!", "🎯 Muito bom! Continue assim!",
                        "👍 Bom começo! Continue treinando!", "📈 Pratique mais para melhorar!"};
                break;
            case 2:
                titulos = new String[]{"🏆 INCRÍVEL! Nível médio dominado!", "🎯 Excelente desempenho!",
                        "👍 Bom! Suba para difícil!", "📈 Continue praticando!"};
                break;
            default:
                titulos = new String[]{"🏆 SENSACIONAL! Você é um mestre!", "🎯 Fantástico desempenho!",
                        "👍 Excelente! Muito bom!", "📈 Continue treinando!"};
        }
        int faixa = aproveitamento >= 0.9 ? 0 : aproveitamento >= 0.7 ? 1 : aproveitamento >= 0.5 ? 2 : 3;
        String proximo = nivel < 3 ? "• Tente o nível " + GameActivity.nomeNivel(nivel + 1).toLowerCase()
                : "• Você está no nível máximo: bata seu recorde!";
        String[] dicas = {
                "✓ Ótima precisão!\n" + proximo,
                "✓ Bom ritmo de acertos\n• Mantenha a consistência para chegar ao topo",
                "✓ Boa base de treino\n• Foque em acertar mais rápido",
                "• Treine o controle do laser com calma\n• O nível fácil ajuda a ganhar confiança"};

        ((TextView) findViewById(R.id.analise_text)).setText(titulos[faixa]);
        ((TextView) findViewById(R.id.analise_dicas)).setText(dicas[faixa]);
    }

    /** Grava a sessão em usuarios/{uid}/resultados e depois atualiza as estatísticas do usuário. */
    private void salvarResultado() {
        if (!GlobalUser.firebaseConfigurado(this) || GlobalUser.userID == null) {
            Log.w(TAG, "Firebase indisponível ou sem usuário: resultado não salvo");
            return;
        }
        String dataHora = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault()).format(new Date());
        Map<String, Object> resultado = new HashMap<>();
        resultado.put("userID", GlobalUser.userID);
        resultado.put("email", GlobalUser.email);
        resultado.put("score", score);
        resultado.put("acertos", acertos);
        resultado.put("nivel", getNomeNivel(nivel));
        resultado.put("tempo", tempo);
        resultado.put("dataHora", dataHora);
        resultado.put("timestamp", FieldValue.serverTimestamp());

        FirebaseFirestore.getInstance()
                .collection("usuarios").document(GlobalUser.userID).collection("resultados")
                .add(resultado)
                .addOnSuccessListener(ref -> {
                    Log.d(TAG, "Resultado salvo: " + ref.getId());
                    atualizarEstatisticasUsuario();
                })
                .addOnFailureListener(e -> {
                    Log.e(TAG, "Erro ao salvar", e);
                    Toast.makeText(this, "Erro ao salvar resultado", Toast.LENGTH_SHORT).show();
                });
    }

    /** Transação: evita perder atualização se duas sessões terminarem juntas; cria o doc se faltar. */
    private void atualizarEstatisticasUsuario() {
        FirebaseFirestore db = FirebaseFirestore.getInstance();
        DocumentReference ref = db.collection("usuarios").document(GlobalUser.userID);
        db.runTransaction(tx -> {
            DocumentSnapshot d = tx.get(ref);
            long total = d.getLong("totalSessoes") != null ? d.getLong("totalSessoes") : 0;
            long melhor = d.getLong("melhorScore") != null ? d.getLong("melhorScore") : 0;
            double media = d.getDouble("mediaScore") != null ? d.getDouble("mediaScore") : 0.0;

            Map<String, Object> upd = new HashMap<>();
            upd.put("email", GlobalUser.email);
            upd.put("totalSessoes", total + 1);
            upd.put("melhorScore", Math.max(melhor, score));
            upd.put("mediaScore", (media * total + score) / (total + 1));
            upd.put("ultimoAcesso", FieldValue.serverTimestamp());
            tx.set(ref, upd, SetOptions.merge());
            return null;
        }).addOnFailureListener(e -> Log.e(TAG, "Erro ao atualizar estatísticas", e));
    }

    private void compartilharResultado() {
        String texto = "🎾 Smart Tennis Arena\n\n"
                + "📊 Resultado:\n"
                + "Score: " + score + " pontos\n"
                + "Acertos: " + acertos + "\n"
                + "Nível: " + getNomeNivel(nivel) + "\n"
                + "Tempo: " + tempo + "s\n\n"
                + "Desafie seus amigos! 🏆";
        Intent share = new Intent(Intent.ACTION_SEND);
        share.setType("text/plain");
        share.putExtra(Intent.EXTRA_SUBJECT, "Meu resultado no Smart Tennis Arena!");
        share.putExtra(Intent.EXTRA_TEXT, texto);
        startActivity(Intent.createChooser(share, "Compartilhar com..."));
    }

    private void voltarMenu() {
        Nav.voltar(this, new Intent(this, MenuActivity.class));
        finish();
    }

    @Override
    public void onBackPressed() {
        voltarMenu(); // o Jogo já foi fechado: "voltar" leva ao Menu, não sai do app
    }

    private String getNomeNivel(int nivel) {
        if (nivel == 1) return "FÁCIL 🟢";
        if (nivel == 2) return "MÉDIO 🟡";
        if (nivel == 3) return "DIFÍCIL 🔴";
        return "DESCONHECIDO";
    }
}
