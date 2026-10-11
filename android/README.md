# TouchHelm Android wrapper

The supported phone experience is the browser remote served by the Windows host. Start `run.bat`, connect the phone to the same reachable network, and open the desktop QR link. Home-screen installation depends on browser/secure-context support.

This folder contains an **experimental Android WebView wrapper**, with package/application ID `com.touchhelm.app`. It discovers TouchHelm hosts using UDP port 53317 and supports a manually entered PC address. The source uses Android SDK 34, Java 17, Kotlin 1.9.22, and Android Gradle Plugin 8.2.2.

No APK build or Android device test is claimed. The scaffold has no committed Gradle wrapper or generated launcher-icon resources; complete the Android Studio setup before building an APK. The browser remote does not require this project.

See the [main README](../README.md) for Windows setup, controls, pairing, and tests.
