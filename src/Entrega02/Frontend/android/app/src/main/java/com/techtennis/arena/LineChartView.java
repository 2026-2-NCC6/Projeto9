package com.techtennis.arena;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.util.AttributeSet;
import android.view.View;

import java.util.ArrayList;
import java.util.List;

/** Gráfico de linha simples (evolução do score), sem biblioteca externa. */
public class LineChartView extends View {

    private final Paint linha = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint ponto = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint eixo = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint texto = new Paint(Paint.ANTI_ALIAS_FLAG);
    private List<Integer> valores = new ArrayList<>();

    public LineChartView(Context context, AttributeSet attrs) {
        super(context, attrs);
        float d = getResources().getDisplayMetrics().density;
        linha.setColor(getContext().getColor(R.color.md_theme_primary));
        linha.setStyle(Paint.Style.STROKE);
        linha.setStrokeWidth(3 * d);
        ponto.setColor(getContext().getColor(R.color.md_theme_secondary_dark));
        eixo.setColor(getContext().getColor(R.color.md_theme_outline_variant));
        eixo.setStrokeWidth(1 * d);
        texto.setColor(getContext().getColor(R.color.md_theme_on_surface));
        texto.setTextSize(11 * d);
    }

    /** Valores em ordem cronológica (mais antigo primeiro). */
    public void setValores(List<Integer> novos) {
        valores = new ArrayList<>(novos);
        invalidate();
    }

    @Override
    protected void onDraw(Canvas c) {
        super.onDraw(c);
        float d = getResources().getDisplayMetrics().density;
        float esq = 36 * d, dir = 8 * d, topo = 8 * d, base = 8 * d;
        float w = getWidth() - esq - dir, h = getHeight() - topo - base;

        c.drawLine(esq, topo, esq, topo + h, eixo);
        c.drawLine(esq, topo + h, esq + w, topo + h, eixo);

        if (valores.isEmpty()) {
            c.drawText("Sem dados", esq + 8 * d, topo + h / 2, texto);
            return;
        }
        int max = 1;
        for (int v : valores) max = Math.max(max, v);
        c.drawText(String.valueOf(max), 2 * d, topo + 10 * d, texto);
        c.drawText("0", 2 * d, topo + h, texto);

        Path path = new Path();
        int n = valores.size();
        for (int i = 0; i < n; i++) {
            float x = esq + (n == 1 ? w / 2 : w * i / (n - 1));
            float y = topo + h - h * valores.get(i) / max;
            if (i == 0) path.moveTo(x, y); else path.lineTo(x, y);
            c.drawCircle(x, y, 4 * d, ponto);
        }
        c.drawPath(path, linha);
    }
}
