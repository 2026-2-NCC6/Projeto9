package com.techtennis.arena;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.util.AttributeSet;
import android.view.View;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/** Chuva de confete (comemoração no resultado). Não intercepta toques. */
public class ConfettiView extends View {

    private static final int[] CORES = {
            Color.parseColor("#FFD600"), Color.parseColor("#2E7D32"),
            Color.parseColor("#0288D1"), Color.parseColor("#F57C00"), Color.parseColor("#B3261E")
    };

    private static class Particula {
        float x, y, vx, vy, rot, vrot, tam;
        int cor;
    }

    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final List<Particula> particulas = new ArrayList<>();
    private final Random random = new Random();
    private long ultimoQuadro;

    public ConfettiView(Context context, AttributeSet attrs) {
        super(context, attrs);
        setClickable(false);
        setFocusable(false);
    }

    /** Dispara o confete (precisa do tamanho da tela já medido). */
    public void iniciar() {
        if (getWidth() == 0) {
            post(this::iniciar);
            return;
        }
        float d = getResources().getDisplayMetrics().density;
        particulas.clear();
        for (int i = 0; i < 110; i++) {
            Particula p = new Particula();
            p.x = random.nextFloat() * getWidth();
            p.y = -random.nextFloat() * getHeight() * 0.6f;   // espalha a chegada no tempo
            p.vx = (random.nextFloat() - 0.5f) * 120 * d;
            p.vy = (180 + random.nextFloat() * 260) * d;
            p.rot = random.nextFloat() * 360;
            p.vrot = (random.nextFloat() - 0.5f) * 540;
            p.tam = (5 + random.nextFloat() * 6) * d;
            p.cor = CORES[random.nextInt(CORES.length)];
            particulas.add(p);
        }
        ultimoQuadro = System.nanoTime();
        invalidate();
    }

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        if (particulas.isEmpty()) return;

        long agora = System.nanoTime();
        float dt = Math.min((agora - ultimoQuadro) / 1e9f, 0.05f);
        ultimoQuadro = agora;

        boolean algumVisivel = false;
        for (Particula p : particulas) {
            p.x += p.vx * dt;
            p.y += p.vy * dt;
            p.rot += p.vrot * dt;
            if (p.y < getHeight() + p.tam) algumVisivel = true;
            if (p.y < -p.tam) continue;

            paint.setColor(p.cor);
            canvas.save();
            canvas.rotate(p.rot, p.x, p.y);
            canvas.drawRect(p.x - p.tam / 2, p.y - p.tam, p.x + p.tam / 2, p.y + p.tam, paint);
            canvas.restore();
        }
        if (algumVisivel) {
            postInvalidateOnAnimation();
        } else {
            particulas.clear();
        }
    }
}
