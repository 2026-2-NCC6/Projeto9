package com.techtennis.arena;

import android.animation.Animator;
import android.animation.AnimatorInflater;
import android.content.res.ColorStateList;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.animation.AnimationUtils;
import android.widget.ArrayAdapter;
import android.widget.ListView;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;

import com.google.android.material.appbar.MaterialToolbar;
import com.google.android.material.button.MaterialButton;
import com.techtennis.arena.services.ApiService;
import com.techtennis.arena.services.SerialService;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;

/** Controle manual de servos, laser, LED, buzzer e sessão. */
public class ControlActivity extends AppCompatActivity {

    private static final String TAG = "ControlActivity";
    private static final int COR_MOVIMENTO = 0xFF01579B; // azul escuro (botão pressionado)

    private SerialService serialService;
    private final List<String> logs = new ArrayList<>();
    private ArrayAdapter<String> logAdapter;
    private ListView listViewLogs;
    private TextView statusConexao;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private Animator pulsoEstop, piscarStatus;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_control);

        serialService = GlobalUser.getSerialService(this);
        if (!serialService.isConnected()) {
            Toast.makeText(this, "Flask não conectado!", Toast.LENGTH_SHORT).show();
            finish();
            return;
        }

        MaterialToolbar toolbar = findViewById(R.id.toolbar);
        toolbar.setNavigationOnClickListener(v -> finish());
        statusConexao = findViewById(R.id.status_conexao);

        listViewLogs = findViewById(R.id.log_list);
        logAdapter = new ArrayAdapter<>(this, android.R.layout.simple_list_item_1, logs);
        listViewLogs.setAdapter(logAdapter);

        setupBotao(R.id.btn_servo_cima, "W", "movimento");
        setupBotao(R.id.btn_servo_baixo, "S", "movimento");
        setupBotao(R.id.btn_servo_esq, "A", "movimento");
        setupBotao(R.id.btn_servo_dir, "D", "movimento");
        setupBotao(R.id.btn_laser, "L", "componente");
        setupBotao(R.id.btn_led, "E", "componente");
        setupBotao(R.id.btn_buzzer, "B", "componente");
        setupBotao(R.id.btn_reset, "R", "componente");
        setupBotao(R.id.btn_iniciar, "@", "sessao");
        setupBotao(R.id.btn_pausar, "#", "sessao");
        setupEstop();
        findViewById(R.id.btn_limpar).setOnClickListener(v -> limparLogs());

        // status pisca; E-STOP pulsa o tempo todo para ficar sempre à vista
        piscarStatus = AnimatorInflater.loadAnimator(this, R.animator.blink);
        piscarStatus.setTarget(statusConexao);
        piscarStatus.start();
        pulsoEstop = AnimatorInflater.loadAnimator(this, R.animator.pulse);
        pulsoEstop.setTarget(findViewById(R.id.btn_estop));
        pulsoEstop.start();

        adicionarLog("ControlActivity iniciada (Flask: " + GlobalUser.flaskURL + ")");
    }

    @Override
    public void finish() {
        super.finish();
        Nav.aoFechar(this);
    }

    /** Envia via Flask; se ok, roda o feedback do botão e loga a resposta do Arduino. */
    private void enviar(String comando, String descricao, Runnable aoSucesso) {
        serialService.enviarComando(comando, new SerialService.Resultado<ApiService.RespostaAPI>() {
            @Override
            public void onOk(ApiService.RespostaAPI r) {
                statusConexao.setText("● Conectado");
                adicionarLog(descricao + " → " + (r.resposta == null || r.resposta.isEmpty() ? "OK" : r.resposta));
                if (aoSucesso != null) aoSucesso.run();
            }

            @Override
            public void onErro(String mensagem) {
                statusConexao.setText("● Sem resposta");
                statusConexao.startAnimation(AnimationUtils.loadAnimation(ControlActivity.this, R.anim.shake));
                adicionarLog("❌ Falha em '" + comando + "': " + mensagem);
            }
        });
    }

    private void setupBotao(int id, String comando, String tipo) {
        MaterialButton botao = findViewById(id);
        botao.setOnClickListener(v -> enviar(comando, descricao(comando, tipo), () -> piscar(botao, tipo)));
    }

    private void setupEstop() {
        findViewById(R.id.btn_estop).setOnClickListener(v -> new AlertDialog.Builder(this)
                .setTitle("E-STOP")
                .setMessage("Confirmar PARADA DE EMERGÊNCIA?")
                .setPositiveButton("SIM", (dialog, which) -> enviar("!", "🚨 E-STOP ATIVADO!", null))
                .setNegativeButton("NÃO", null)
                .show());
    }

    private String descricao(String comando, String tipo) {
        switch (tipo) {
            case "movimento": return "➡️ " + nomeMovimento(comando) + " (" + comando + ")";
            case "sessao": return "▶️ Sessão: " + (comando.equals("@") ? "Iniciar" : "Pausar") + " (" + comando + ")";
            default: return "⚙️ " + nomeComponente(comando) + " (" + comando + ")";
        }
    }

    /** Realça o botão por um instante e restaura a cor original. Botões sem fundo (outlined) não piscam. */
    private void piscar(MaterialButton botao, String tipo) {
        ColorStateList original = botao.getBackgroundTintList();
        if (original == null) return;
        int cor = tipo.equals("movimento") ? COR_MOVIMENTO
                : tipo.equals("sessao") ? getColor(R.color.md_theme_success)
                : getColor(R.color.md_theme_secondary);
        if (botao.getTag() == null) botao.setTag(original);   // guarda só a cor ORIGINAL (toques rápidos)
        botao.setBackgroundTintList(ColorStateList.valueOf(cor));
        handler.postDelayed(() -> botao.setBackgroundTintList((ColorStateList) botao.getTag()), 300);
    }

    private void adicionarLog(String mensagem) {
        String hora = new SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(new Date());
        String entrada = "[" + hora + "] " + mensagem;
        logs.add(entrada);
        logAdapter.notifyDataSetChanged();
        listViewLogs.setSelection(logs.size() - 1);
        Log.d(TAG, entrada);
    }

    private void limparLogs() {
        logs.clear();
        logAdapter.notifyDataSetChanged();
        adicionarLog("Log limpo pelo usuário");
    }

    private String nomeMovimento(String comando) {
        switch (comando) {
            case "W": return "CIMA ▲";
            case "S": return "BAIXO ▼";
            case "A": return "ESQUERDA ◀";
            case "D": return "DIREITA ▶";
            default: return comando;
        }
    }

    private String nomeComponente(String comando) {
        switch (comando) {
            case "L": return "LASER";
            case "E": return "LED";
            case "B": return "BUZZER";
            case "R": return "RESET SERVOS";
            default: return comando;
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        handler.removeCallbacksAndMessages(null);
        if (pulsoEstop != null) pulsoEstop.cancel();
        if (piscarStatus != null) piscarStatus.cancel();
    }
}
