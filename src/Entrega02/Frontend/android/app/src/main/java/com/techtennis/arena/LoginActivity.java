package com.techtennis.arena;

import android.content.Intent;
import android.os.Bundle;
import android.util.Log;
import android.view.View;
import android.view.animation.AnimationUtils;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ProgressBar;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

import com.google.android.gms.tasks.Task;
import com.google.firebase.auth.AuthResult;
import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.FirebaseAuthInvalidCredentialsException;
import com.google.firebase.auth.FirebaseAuthInvalidUserException;
import com.google.firebase.auth.FirebaseAuthUserCollisionException;
import com.google.firebase.auth.FirebaseAuthWeakPasswordException;
import com.google.firebase.auth.FirebaseUser;
import com.google.firebase.FirebaseNetworkException;
import com.google.firebase.firestore.FirebaseFirestore;

import java.util.Date;
import java.util.HashMap;
import java.util.Map;

/** Login e cadastro com Firebase Authentication (email/senha). */
public class LoginActivity extends AppCompatActivity {

    private static final String TAG = "LoginActivity";

    private FirebaseAuth mAuth;
    private EditText emailInput, senhaInput;
    private Button btnLogin, btnRegistro;
    private ProgressBar loading;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_login);

        emailInput = findViewById(R.id.email_input);
        senhaInput = findViewById(R.id.senha_input);
        btnLogin = findViewById(R.id.btn_login);
        btnRegistro = findViewById(R.id.btn_registro);
        loading = findViewById(R.id.loading);

        // entrada suave (fade 300ms)
        View raiz = findViewById(R.id.login_root);
        raiz.setAlpha(0f);
        raiz.animate().alpha(1f).setDuration(300).start();

        if (!GlobalUser.firebaseConfigurado(this)) {
            Toast.makeText(this, "Firebase não configurado: falta app/google-services.json",
                    Toast.LENGTH_LONG).show();
            btnLogin.setEnabled(false);
            btnRegistro.setEnabled(false);
            return;
        }

        mAuth = FirebaseAuth.getInstance();
        if (mAuth.getCurrentUser() != null) {
            irParaMenu();
            return;
        }

        btnLogin.setOnClickListener(v -> fazerLogin());
        btnRegistro.setOnClickListener(v -> fazerRegistro());
    }

    private void fazerLogin() {
        String email = emailInput.getText().toString().trim();
        String senha = senhaInput.getText().toString();

        if (email.isEmpty() || senha.isEmpty()) {
            Toast.makeText(this, "Preencha todos os campos", Toast.LENGTH_SHORT).show();
            return;
        }
        setCarregando(true);
        try {
            mAuth.signInWithEmailAndPassword(email, senha)
                    .addOnCompleteListener(this, task -> aoConcluir(task, "Login realizado!", false));
        } catch (Exception e) {
            Log.e(TAG, "Erro no login", e);
            setCarregando(false);
            Toast.makeText(this, "Erro de conexão", Toast.LENGTH_SHORT).show();
        }
    }

    private void fazerRegistro() {
        String email = emailInput.getText().toString().trim();
        String senha = senhaInput.getText().toString();

        if (email.isEmpty()) {
            Toast.makeText(this, "Informe o email", Toast.LENGTH_SHORT).show();
            return;
        }
        if (senha.length() < 6) {
            Toast.makeText(this, "Senha deve ter mínimo 6 caracteres", Toast.LENGTH_SHORT).show();
            return;
        }
        setCarregando(true);
        try {
            mAuth.createUserWithEmailAndPassword(email, senha)
                    .addOnCompleteListener(this, task -> aoConcluir(task, "Conta criada com sucesso!", true));
        } catch (Exception e) {
            Log.e(TAG, "Erro no registro", e);
            setCarregando(false);
            Toast.makeText(this, "Erro de conexão", Toast.LENGTH_SHORT).show();
        }
    }

    private void aoConcluir(Task<AuthResult> task, String msgSucesso, boolean novaConta) {
        if (task.isSuccessful()) {
            if (novaConta) criarDocumentoUsuario(mAuth.getCurrentUser());
            Toast.makeText(this, msgSucesso, Toast.LENGTH_SHORT).show();
            irParaMenu();
        } else {
            setCarregando(false);
            Exception e = task.getException();
            Log.e(TAG, "Falha de autenticação", e);
            Toast.makeText(this, traduzirErro(e), Toast.LENGTH_LONG).show();
            findViewById(R.id.login_root).startAnimation(AnimationUtils.loadAnimation(this, R.anim.shake));
        }
    }

    private String traduzirErro(Exception e) {
        if (e instanceof FirebaseAuthUserCollisionException) return "Email já em uso";
        if (e instanceof FirebaseAuthWeakPasswordException) return "Senha muito fraca";
        if (e instanceof FirebaseAuthInvalidUserException) return "Usuário não encontrado";
        if (e instanceof FirebaseAuthInvalidCredentialsException) return "Email ou senha inválidos";
        if (e instanceof FirebaseNetworkException) return "Sem conexão com a internet";
        return "Erro: " + (e != null ? e.getMessage() : "desconhecido");
    }

    private void setCarregando(boolean ativo) {
        loading.setVisibility(ativo ? View.VISIBLE : View.GONE);
        btnLogin.setEnabled(!ativo);
        btnRegistro.setEnabled(!ativo);
    }

    /** Documento usuarios/{uid} com as estatísticas iniciais. */
    private void criarDocumentoUsuario(FirebaseUser user) {
        Map<String, Object> usuario = new HashMap<>();
        usuario.put("email", user.getEmail());
        usuario.put("criadoEm", new Date());
        usuario.put("ultimoAcesso", new Date());
        usuario.put("totalSessoes", 0);
        usuario.put("melhorScore", 0);
        usuario.put("mediaScore", 0.0);
        FirebaseFirestore.getInstance().collection("usuarios").document(user.getUid()).set(usuario)
                .addOnFailureListener(e -> Log.e(TAG, "Erro ao criar documento do usuário", e));
    }

    private void irParaMenu() {
        FirebaseUser user = mAuth.getCurrentUser();
        GlobalUser.iniciarSessao(user.getEmail(), user.getUid());
        Nav.avancar(this, new Intent(this, MenuActivity.class));
        finish();
    }
}
