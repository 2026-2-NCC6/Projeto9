package com.techtennis.arena;

import android.content.Context;
import android.content.SharedPreferences;

import com.google.firebase.FirebaseApp;
import com.techtennis.arena.services.SerialService;

/** Dados compartilhados entre as Activities. */
public class GlobalUser {
    public static String email = null;
    public static String userID = null;      // uid do Firebase
    public static String nomeUsuario = "";   // parte do email antes do @
    public static int nivelSelecionado = 0;

    /** IP do notebook onde roda flask_server/api.py (editável na tela de conexão). */
    public static String flaskURL = "http://192.168.1.100:5000";
    /** Último /status: a visão computacional está enviando acertos? */
    public static boolean visaoAtiva = false;
    public static SerialService serialService;

    private static final String PREFS = "config";

    /** Cliente HTTP compartilhado; criado na primeira chamada com a URL salva. */
    public static synchronized SerialService getSerialService(Context context) {
        if (serialService == null) {
            SharedPreferences p = context.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            flaskURL = p.getString("flaskURL", flaskURL);
            serialService = new SerialService(flaskURL);
        }
        return serialService;
    }

    public static void salvarFlaskURL(Context context, String url) {
        flaskURL = url;
        context.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .edit().putString("flaskURL", url).apply();
        getSerialService(context).configurar(url);
    }

    public static void iniciarSessao(String email, String uid) {
        GlobalUser.email = email;
        GlobalUser.userID = uid;
        GlobalUser.nomeUsuario = email != null ? email.split("@")[0] : "";
    }

    public static void resetarPartida() {
        nivelSelecionado = 0;
    }

    /** Logout completo. */
    public static void limpar() {
        email = null;
        userID = null;
        nomeUsuario = "";
        nivelSelecionado = 0;
        visaoAtiva = false;
    }

    /** false se o app foi compilado sem app/google-services.json. */
    public static boolean firebaseConfigurado(Context context) {
        return !FirebaseApp.getApps(context).isEmpty();
    }
}
