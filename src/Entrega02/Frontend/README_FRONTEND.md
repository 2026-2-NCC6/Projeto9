# Frontend

Aplicativo Android (Java) que se comunica com o backend por HTTP.

## Tecnologias

- Java
- Android SDK (mínimo 24, alvo 33)
- Gradle (wrapper incluso — não é necessário instalar Gradle separadamente)
- [Retrofit](https://square.github.io/retrofit/) + [OkHttp](https://square.github.io/okhttp/) — cliente HTTP
- [Firebase Authentication](https://firebase.google.com/docs/auth) — login por e-mail/senha
- [Cloud Firestore](https://firebase.google.com/docs/firestore) — histórico de partidas
- Material Design 3 (`com.google.android.material`)

## Pré-requisitos

- [Android Studio](https://developer.android.com/studio) (recomendado) ou o SDK/JDK equivalente
  pela linha de comando
- JDK 8+
- Um projeto Firebase próprio, com Authentication (e-mail/senha) e Firestore ativados

## Setup

1. Abra a pasta `android/` no Android Studio (`File → Open`).
2. **Firebase:** baixe o arquivo `google-services.json` do seu projeto no
   [Firebase Console](https://console.firebase.google.com/) e coloque em `android/app/google-services.json`.
   Sem esse arquivo, o app abre normalmente, mas a tela de login fica desativada.
3. Deixe o Android Studio sincronizar o Gradle (baixa as dependências automaticamente).
4. Rode o app (`Run ▶` ou `Shift+F10`) com um emulador ou aparelho físico conectado.

## Conectar ao Backend

O endereço do servidor Flask é configurado dentro do próprio app (não fica fixo no código): no
menu, abra a tela de conexão e informe o IP e a porta onde o `flask_server` está rodando (por
exemplo, `http://<ip-do-servidor>:5000`). O valor fica salvo no aparelho.

## Build pela linha de comando

```bash
cd android
./gradlew assembleDebug       # gera o APK de debug
./gradlew installDebug        # instala no dispositivo/emulador conectado
```

## Testes de integração (rodam em um dispositivo real, pela rede)

```bash
cd android
./gradlew assembleDebug assembleDebugAndroidTest
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb install -r app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb shell am instrument -w -e flaskUrl http://<ip-do-servidor>:5000 \
    com.techtennis.arena.test/androidx.test.runner.AndroidJUnitRunner
```
