package com.techtennis.arena;

import android.app.Activity;
import android.content.Intent;
import android.os.Build;
import android.os.VibrationEffect;
import android.os.Vibrator;

/** Navegação com as transições do design (deslizar, subir, escalar, fade) e vibração. */
final class Nav {

    private Nav() { }

    /** Login -> Menu, Conexão -> Controle: desliza da direita. */
    static void avancar(Activity a, Intent i) {
        a.startActivity(i);
        a.overridePendingTransition(R.anim.slide_in_right, R.anim.slide_out_left);
    }

    /** Menu -> Histórico / Conexão: sobe de baixo. */
    static void subir(Activity a, Intent i) {
        a.startActivity(i);
        a.overridePendingTransition(R.anim.slide_in_up, R.anim.hold);
    }

    /** Menu -> Jogo: escala + fade. */
    static void escalar(Activity a, Intent i) {
        a.startActivity(i);
        a.overridePendingTransition(R.anim.scale_in, R.anim.fade_out);
    }

    /** Jogo -> Resultado, Logout: fade. */
    static void fade(Activity a, Intent i) {
        a.startActivity(i);
        a.overridePendingTransition(R.anim.fade_in, R.anim.fade_out);
    }

    /** Resultado -> Menu: desliza da esquerda. */
    static void voltar(Activity a, Intent i) {
        a.startActivity(i);
        a.overridePendingTransition(R.anim.slide_in_left, R.anim.slide_out_right);
    }

    /** Saída de telas secundárias (Histórico, Conexão, Controle). */
    static void aoFechar(Activity a) {
        a.overridePendingTransition(R.anim.slide_in_left, R.anim.slide_out_right);
    }

    /** Vibração curta (feedback de acerto); ignora aparelhos sem vibrador. */
    static void vibrar(Activity a, long ms) {
        Vibrator v = (Vibrator) a.getSystemService(Activity.VIBRATOR_SERVICE);
        if (v == null || !v.hasVibrator()) return;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            v.vibrate(VibrationEffect.createOneShot(ms, VibrationEffect.DEFAULT_AMPLITUDE));
        } else {
            v.vibrate(ms);
        }
    }
}
