package com.techtennis.arena;

import android.animation.Animator;
import android.animation.AnimatorInflater;
import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.EditText;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

import com.google.android.material.appbar.MaterialToolbar;
import com.google.android.material.button.MaterialButton;
import com.google.android.material.card.MaterialCardView;
import com.google.firebase.auth.FirebaseAuth;
import com.techtennis.arena.services.ApiService;
import com.techtennis.arena.services.SerialService;

/** Conexão com a API Flask do notebook (que fala com o Arduino). */
public class MainActivity extends AppCompatActivity {

    private SerialService serialService;
    private MaterialCardView statusCard;
    private TextView statusText, statusTextSegundo;
    private View statusDot;
    private EditText flaskUrlInput;
    private MaterialButton btnConectar, btnControle;
    private ProgressBar loading;
    private Animator piscar;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        if (GlobalUser.email == null) { // sessão perdida: volta ao login
            startActivity(new Intent(this, LoginActivity.class));
            finish();
            return;
        }

        MaterialToolbar toolbar = findViewById(R.id.toolbar);
        toolbar.setNavigationOnClickListener(v -> finish());

        serialService = GlobalUser.getSerialService(this);
        statusCard = findViewById(R.id.status_card);
        statusText = findViewById(R.id.status_text);
        statusTextSegundo = findViewById(R.id.status_text_segundo);
        statusDot = findViewById(R.id.status_dot);
        flaskUrlInput = findViewById(R.id.flask_url_input);
        btnConectar = findViewById(R.id.btn_conectar);
        btnControle = findViewById(R.id.btn_controle);
        loading = findViewById(R.id.loading);

        flaskUrlInput.setText(GlobalUser.flaskURL);
        btnConectar.setOnClickListener(v -> testarFlask());
        btnControle.setOnClickListener(v -> irParaControle());
        findViewById(R.id.btn_sair).setOnClickListener(v -> logout());

        piscar = AnimatorInflater.loadAnimator(this, R.animator.blink);
        piscar.setTarget(statusDot);
        piscar.start();

        testarFlask();
    }

    @Override
    public void finish() {
        super.finish();
        Nav.aoFechar(this);
    }

    private void testarFlask() {
        String url = flaskUrlInput.getText().toString().trim();
        if (url.isEmpty()) {
            Toast.makeText(this, "Informe o endereço do Flask", Toast.LENGTH_SHORT).show();
            return;
        }
        GlobalUser.salvarFlaskURL(this, url); // salva e recria o cliente HTTP
        serialService = GlobalUser.getSerialService(this);

        setCarregando(true);
        serialService.verificarStatus(new SerialService.Resultado<ApiService.StatusAPI>() {
            @Override
            public void onOk(ApiService.StatusAPI s) {
                setCarregando(false);
                GlobalUser.visaoAtiva = s.visao;
                mostrarStatus(true, "✓ Flask conectado",
                        "Arduino: " + s.arduino + "  •  Visão: " + (s.visao ? "ativa" : "inativa (timer)"));
            }

            @Override
            public void onErro(String mensagem) {
                setCarregando(false);
                GlobalUser.visaoAtiva = false;
                mostrarStatus(false, "✗ Flask indisponível", "Verifique se o notebook está ligado e na mesma rede");
                statusCard.startAnimation(android.view.animation.AnimationUtils.loadAnimation(
                        MainActivity.this, R.anim.shake));
            }
        });
    }

    private void mostrarStatus(boolean ok, String titulo, String detalhe) {
        statusCard.setCardBackgroundColor(getColor(ok ? R.color.md_theme_primary : R.color.md_theme_error));
        statusText.setText(titulo);
        statusTextSegundo.setText(detalhe);
        btnControle.setEnabled(ok);
    }

    private void setCarregando(boolean ativo) {
        loading.setVisibility(ativo ? View.VISIBLE : View.GONE);
        btnConectar.setEnabled(!ativo);
    }

    private void irParaControle() {
        Nav.avancar(this, new Intent(this, ControlActivity.class));
    }

    private void logout() {
        FirebaseAuth.getInstance().signOut();
        GlobalUser.limpar();
        Nav.fade(this, new Intent(this, LoginActivity.class));
        finishAffinity();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (piscar != null) piscar.cancel();
    }
}
