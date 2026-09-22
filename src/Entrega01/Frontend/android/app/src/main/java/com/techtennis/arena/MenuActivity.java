package com.techtennis.arena;

import android.animation.Animator;
import android.animation.AnimatorInflater;
import android.content.Intent;
import android.content.res.ColorStateList;
import android.os.Bundle;
import android.util.Log;
import android.view.View;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.graphics.ColorUtils;

import com.google.android.material.card.MaterialCardView;
import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.firestore.FirebaseFirestore;

/** Menu principal: nível, melhor score, histórico e início do jogo. */
public class MenuActivity extends AppCompatActivity {

    private static final String TAG = "MenuActivity";

    private MaterialCardView cardFacil, cardMedio, cardDificil;
    private View btnJogar;
    private TextView nivelText, melhorScoreText;
    private Animator pulso;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_menu);

        ((TextView) findViewById(R.id.usuario_nome)).setText("Bem-vindo, " + GlobalUser.nomeUsuario + "! 👋");
        nivelText = findViewById(R.id.nivel_selecionado_text);
        melhorScoreText = findViewById(R.id.melhor_score_text);
        btnJogar = findViewById(R.id.btn_jogar);

        cardFacil = findViewById(R.id.btn_facil);
        cardMedio = findViewById(R.id.btn_medio);
        cardDificil = findViewById(R.id.btn_dificil);
        cardFacil.setOnClickListener(v -> selecionarNivel(1));
        cardMedio.setOnClickListener(v -> selecionarNivel(2));
        cardDificil.setOnClickListener(v -> selecionarNivel(3));
        pintarCards();
        animarEntradaDosCards();

        btnJogar.setOnClickListener(v -> iniciarJogo());
        findViewById(R.id.btn_historico).setOnClickListener(v ->
                Nav.subir(this, new Intent(this, HistoricoActivity.class)));
        findViewById(R.id.btn_arduino).setOnClickListener(v ->
                Nav.subir(this, new Intent(this, MainActivity.class)));
        findViewById(R.id.btn_sair).setOnClickListener(v -> logout());

        carregarMelhorScore();
    }

    @Override
    protected void onResume() {
        super.onResume();
        // botão JOGAR "respira"
        pulso = AnimatorInflater.loadAnimator(this, R.animator.pulse);
        pulso.setTarget(btnJogar);
        pulso.start();
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (pulso != null) pulso.cancel();
        btnJogar.setScaleX(1f);
        btnJogar.setScaleY(1f);
    }

    /** Os 3 cards de nível entram com escala + fade, um após o outro. */
    private void animarEntradaDosCards() {
        MaterialCardView[] cards = {cardFacil, cardMedio, cardDificil};
        for (int i = 0; i < cards.length; i++) {
            cards[i].setAlpha(0f);
            cards[i].setScaleX(0.92f);
            cards[i].setScaleY(0.92f);
            cards[i].animate().alpha(1f).scaleX(1f).scaleY(1f)
                    .setStartDelay(80L * i).setDuration(200).start();
        }
    }

    private void selecionarNivel(int nivel) {
        GlobalUser.nivelSelecionado = nivel;
        pintarCards();
        nivelText.setText("✓ Nível " + GameActivity.nomeNivel(nivel) + " selecionado");
        Toast.makeText(this, "Bora treinar! 💪", Toast.LENGTH_SHORT).show();
    }

    /** Card selecionado: borda grossa e fundo na cor do nível; os demais ficam neutros. */
    private void pintarCards() {
        int n = GlobalUser.nivelSelecionado;
        estilizar(cardFacil, n == 1, getColor(R.color.nivel_facil));
        estilizar(cardMedio, n == 2, getColor(R.color.nivel_medio));
        estilizar(cardDificil, n == 3, getColor(R.color.nivel_dificil));
    }

    private void estilizar(MaterialCardView card, boolean selecionado, int cor) {
        float d = getResources().getDisplayMetrics().density;
        card.setStrokeColor(selecionado ? cor : getColor(R.color.md_theme_outline_variant));
        card.setStrokeWidth((int) ((selecionado ? 3 : 1) * d));
        int fundo = getColor(R.color.md_theme_background);
        card.setCardBackgroundColor(ColorStateList.valueOf(selecionado
                ? ColorUtils.blendARGB(fundo, cor, 0.12f) : fundo));   // opaco: sem sombra vazando
        card.setCardElevation(0);
    }

    private void iniciarJogo() {
        if (GlobalUser.nivelSelecionado == 0) {
            Toast.makeText(this, "Selecione um nível!", Toast.LENGTH_SHORT).show();
            findViewById(R.id.nivel_selecionado_text).startAnimation(
                    android.view.animation.AnimationUtils.loadAnimation(this, R.anim.shake));
            return;
        }
        Intent intent = new Intent(this, GameActivity.class);
        intent.putExtra("nivel", GlobalUser.nivelSelecionado);
        Nav.escalar(this, intent);
        finish();
    }

    private void carregarMelhorScore() {
        if (GlobalUser.userID == null || !GlobalUser.firebaseConfigurado(this)) return;
        FirebaseFirestore.getInstance().collection("usuarios").document(GlobalUser.userID).get()
                .addOnSuccessListener(doc -> {
                    Long melhor = doc.exists() ? doc.getLong("melhorScore") : null;
                    melhorScoreText.setText(melhor != null && melhor > 0
                            ? melhor + " pts" : "Comece a jogar!");
                })
                .addOnFailureListener(e -> Log.e(TAG, "Erro ao ler melhor score", e));
    }

    private void logout() {
        FirebaseAuth.getInstance().signOut();
        GlobalUser.limpar();
        Nav.fade(this, new Intent(this, LoginActivity.class));
        finishAffinity();
    }
}
