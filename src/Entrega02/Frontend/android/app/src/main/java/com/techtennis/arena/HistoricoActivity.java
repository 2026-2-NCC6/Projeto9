package com.techtennis.arena;

import android.os.Bundle;
import android.util.Log;
import android.widget.ListView;
import android.widget.TextView;

import androidx.appcompat.app.AppCompatActivity;

import com.google.android.material.appbar.MaterialToolbar;
import com.google.firebase.firestore.DocumentSnapshot;
import com.google.firebase.firestore.FirebaseFirestore;
import com.google.firebase.firestore.Query;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/** Lista de sessões, estatísticas e gráfico de evolução do usuário logado. */
public class HistoricoActivity extends AppCompatActivity {

    private static final String TAG = "HistoricoActivity";
    private static final int MAX_PONTOS_GRAFICO = 20;

    private ListView lista;
    private TextView estatisticasText;
    private LineChartView grafico;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_historico);

        MaterialToolbar toolbar = findViewById(R.id.toolbar);
        toolbar.setNavigationOnClickListener(v -> finish());

        lista = findViewById(R.id.resultados_list);
        estatisticasText = findViewById(R.id.estatisticas_text);
        grafico = findViewById(R.id.grafico);

        carregarHistorico();
    }

    @Override
    public void finish() {
        super.finish();
        Nav.aoFechar(this);
    }

    private void carregarHistorico() {
        if (GlobalUser.userID == null || !GlobalUser.firebaseConfigurado(this)) {
            estatisticasText.setText("Faça login para ver o histórico.");
            return;
        }
        FirebaseFirestore.getInstance()
                .collection("usuarios").document(GlobalUser.userID).collection("resultados")
                .orderBy("timestamp", Query.Direction.DESCENDING)
                .get()
                .addOnSuccessListener(snapshot -> {
                    List<Map<String, Object>> resultados = new ArrayList<>();
                    for (DocumentSnapshot doc : snapshot) resultados.add(doc.getData());
                    lista.setAdapter(new ResultadoAdapter(this, resultados));
                    calcularEstatisticas(resultados);
                    desenharGrafico(resultados);
                })
                .addOnFailureListener(e -> {
                    Log.e(TAG, "Erro ao carregar histórico", e);
                    estatisticasText.setText("Erro ao carregar histórico: " + e.getMessage());
                });
    }

    private static int score(Map<String, Object> r) {
        return ((Number) r.get("score")).intValue();
    }

    private void calcularEstatisticas(List<Map<String, Object>> resultados) {
        if (resultados.isEmpty()) {
            estatisticasText.setText("Nenhuma sessão ainda. Comece a jogar!");
            return;
        }
        int melhor = 0;
        String nivelMelhor = "";
        double soma = 0;
        for (Map<String, Object> r : resultados) {
            int s = score(r);
            if (s >= melhor) {
                melhor = s;
                nivelMelhor = String.valueOf(r.get("nivel")).replaceAll("[^A-Za-zÁÉÍÓÚÂÊÔÃÕÇ]", "");
            }
            soma += s;
        }
        estatisticasText.setText("📊 ESTATÍSTICAS GERAIS\n\n"
                + "Total: " + resultados.size() + " sessões\n"
                + "Melhor: " + melhor + " pts (" + nivelMelhor + ")\n"
                + "Média: " + String.format(Locale.getDefault(), "%.1f", soma / resultados.size()) + " pts\n"
                + "Evolução: " + evolucao(resultados));
    }

    /** Média das sessões mais recentes contra as anteriores (a lista vem do mais novo ao mais antigo). */
    private String evolucao(List<Map<String, Object>> resultados) {
        int k = Math.min(3, resultados.size() / 2);
        if (k == 0) return "— (jogue mais uma sessão)";
        double recente = 0, anterior = 0;
        for (int i = 0; i < k; i++) {
            recente += score(resultados.get(i));
            anterior += score(resultados.get(k + i));
        }
        recente /= k;
        anterior /= k;
        if (anterior == 0) return recente > 0 ? "↗ subindo" : "→ estável";
        double pct = (recente - anterior) / anterior * 100;
        String seta = pct > 1 ? "↗" : pct < -1 ? "↘" : "→";
        return seta + " " + String.format(Locale.getDefault(), "%+.0f%%", pct);
    }

    /** A lista vem do mais novo para o mais antigo; o gráfico usa ordem cronológica. */
    private void desenharGrafico(List<Map<String, Object>> resultados) {
        List<Integer> pontos = new ArrayList<>();
        int inicio = Math.min(resultados.size(), MAX_PONTOS_GRAFICO);
        for (int i = inicio - 1; i >= 0; i--) pontos.add(score(resultados.get(i)));
        grafico.setValores(pontos);
    }
}
