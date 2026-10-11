package com.touchhelm.app

import android.annotation.SuppressLint
import android.content.Context
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.view.WindowManager
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress

class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private var multicastLock: WifiManager.MulticastLock? = null
    private var isDiscovering = true

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Keep screen awake for presentations
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        // Enable Immersive Fullscreen Mode
        hideSystemBars()

        webView = WebView(this)
        setContentView(webView)

        configureWebView()

        // Acquire Wi-Fi Multicast Lock for UDP Auto-Discovery
        acquireMulticastLock()

        // Start local network auto-discovery in background
        startAutoDiscovery()
    }

    private fun configureWebView() {
        val settings = webView.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.databaseEnabled = true
        settings.allowFileAccess = true
        settings.loadWithOverviewMode = true
        settings.useWideViewPort = true
        settings.cacheMode = WebSettings.LOAD_DEFAULT

        webView.setLayerType(View.LAYER_TYPE_HARDWARE, null)
        webView.webViewClient = object : WebViewClient() {
            override fun onReceivedError(
                view: WebView?,
                errorCode: Int,
                description: String?,
                failingUrl: String?
            ) {
                // If failed, load fallback pairing UI
                showFallbackHtml()
            }
        }

        // Check shared preferences for last known server
        val prefs = getSharedPreferences("touchhelm_prefs", Context.MODE_PRIVATE)
        val lastHost = prefs.getString("last_host", null)
        if (!lastHost.isNullOrEmpty()) {
            webView.loadUrl("http://$lastHost")
        } else {
            showFallbackHtml()
        }
    }

    private fun showFallbackHtml() {
        val fallbackHtml = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    body { background: #070a0e; color: #fff; font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; text-align: center; }
                    h2 { margin-bottom: 8px; color: #00f5ff; }
                    p { color: #94a3b8; font-size: 14px; margin-bottom: 24px; }
                    input { background: #0e141c; border: 1px solid rgba(0,245,255,0.2); border-radius: 10px; color: #fff; font-size: 16px; padding: 12px 16px; width: 100%; max-width: 320px; box-sizing: border-box; outline: none; margin-bottom: 12px; }
                    button { background: #00f5ff; border: none; border-radius: 10px; color: #000; font-weight: bold; font-size: 16px; padding: 12px 24px; width: 100%; max-width: 320px; cursor: pointer; }
                    .radar { width: 48px; height: 48px; border-radius: 50%; border: 3px solid #00f5ff; border-top-color: transparent; animation: spin 1s linear infinite; margin-bottom: 20px; }
                    @keyframes spin { 100% { transform: rotate(360deg); } }
                </style>
            </head>
            <body>
                <div class="radar"></div>
                <h2>Searching for TouchHelm PC...</h2>
                <p>Ensure your PC is running TouchHelm and connected to the same Wi-Fi.</p>
                <input type="text" id="manualIp" placeholder="Or enter PC IP (e.g. 192.168.1.10:8765)">
                <button onclick="connectManual()">Connect Directly</button>
                <script>
                    function connectManual() {
                        var ip = document.getElementById('manualIp').value.trim();
                        if (ip) {
                            if (!ip.startsWith('http')) ip = 'http://' + ip;
                            window.location.href = ip;
                        }
                    }
                </script>
            </body>
            </html>
        """.trimIndent()
        webView.loadDataWithBaseURL(null, fallbackHtml, "text/html", "utf-8", null)
    }

    private fun startAutoDiscovery() {
        Thread {
            try {
                val socket = DatagramSocket(53317)
                socket.broadcast = true
                val buffer = ByteArray(2048)
                val packet = DatagramPacket(buffer, buffer.size)

                while (isDiscovering) {
                    socket.receive(packet)
                    val jsonStr = String(packet.data, 0, packet.length)
                    try {
                        val obj = JSONObject(jsonStr)
                        if (obj.optString("service") == "touchhelm") {
                            val primaryIp = obj.optString("primary_ip", packet.address.hostAddress)
                            val port = obj.optInt("port", 8765)
                            val targetUrl = "http://$primaryIp:$port"

                            // Save preference
                            val prefs = getSharedPreferences("touchhelm_prefs", Context.MODE_PRIVATE)
                            prefs.edit().putString("last_host", "$primaryIp:$port").apply()

                            Handler(Looper.getMainLooper()).post {
                                if (webView.url == null || webView.url?.contains("data:") == true) {
                                    webView.loadUrl(targetUrl)
                                }
                            }
                            break
                        }
                    } catch (e: Exception) {}
                }
                socket.close()
            } catch (e: Exception) {}
        }.start()
    }

    private fun acquireMulticastLock() {
        try {
            val wifi = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
            multicastLock = wifi.createMulticastLock("touchhelm_multicast_lock")
            multicastLock?.setReferenceCounted(true)
            multicastLock?.acquire()
        } catch (e: Exception) {}
    }

    private fun hideSystemBars() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.insetsController?.let {
                it.hide(WindowInsets.Type.statusBars() or WindowInsets.Type.navigationBars())
                it.systemBarsBehavior = WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            }
        } else {
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility = (
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                or View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_FULLSCREEN
            )
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        isDiscovering = false
        try {
            multicastLock?.release()
        } catch (e: Exception) {}
    }

    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }
}
