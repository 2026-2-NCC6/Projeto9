package com.techtennis.arena;

import android.content.Context;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.TextView;

import androidx.annotation.NonNull;

import java.util.List;
import java.util.Map;

/** Uma linha por sessão: score + nível, e data/acertos/tempo. */
public class ResultadoAdapter extends ArrayAdapter<Map<String, Object>> {

    public ResultadoAdapter(Context context, List<Map<String, Object>> dados) {
        super(context, 0, dados);
    }

    @NonNull
    @Override
    public View getView(int position, View convertView, @NonNull ViewGroup parent) {
        View v = convertView != null ? convertView
                : LayoutInflater.from(getContext()).inflate(R.layout.item_resultado, parent, false);
        Map<String, Object> r = getItem(position);

        String nivel = texto(r, "nivel");
        ((TextView) v.findViewById(R.id.item_emoji)).setText(emojiDoNivel(nivel));
        ((TextView) v.findViewById(R.id.item_titulo)).setText(numero(r, "score") + " pts");
        ((TextView) v.findViewById(R.id.item_detalhe))
                .setText(nivel.replaceAll("[^A-Za-zÁÉÍÓÚÂÊÔÃÕÇ]", "") + " • " + numero(r, "acertos") + (numero(r, "acertos") == 1 ? " acerto • " : " acertos • ")
                        + numero(r, "tempo") + "s • " + texto(r, "dataHora"));
        return v;
    }

    private static String emojiDoNivel(String nivel) {
        if (nivel.contains("FÁCIL")) return "🟢";
        if (nivel.contains("MÉDIO")) return "🟡";
        if (nivel.contains("DIFÍCIL")) return "🔴";
        return "🎾";
    }

    private static int numero(Map<String, Object> r, String chave) {
        Object o = r.get(chave);
        return o instanceof Number ? ((Number) o).intValue() : 0;
    }

    private static String texto(Map<String, Object> r, String chave) {
        Object o = r.get(chave);
        return o != null ? o.toString() : "-";
    }
}
