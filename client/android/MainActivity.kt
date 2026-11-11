package com.unifierr.client

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.webkit.CookieManager
import android.webkit.WebView
import androidx.activity.enableEdgeToEdge
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat

// Copied over the generated MainActivity by CI (see client/README.md).
// The window draws edge-to-edge (Android 15+), so without this the page sits under the status bar and
// behind the back/home/recents bar. Padding the content view keeps the whole app between the system bars;
// the keyboard inset keeps the focused field visible.
class MainActivity : TauriActivity() {
  override fun onCreate(savedInstanceState: Bundle?) {
    enableEdgeToEdge()
    super.onCreate(savedInstanceState)

    val content = findViewById<View>(android.R.id.content)
    ViewCompat.setOnApplyWindowInsetsListener(content) { view, insets ->
      val bars = insets.getInsets(
        WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout()
      )
      val keyboard = insets.getInsets(WindowInsetsCompat.Type.ime())
      view.setPadding(bars.left, bars.top, bars.right, maxOf(bars.bottom, keyboard.bottom))
      WindowInsetsCompat.CONSUMED
    }
  }

  // Save the sign-in cookie to disk when the app goes to the background, so it survives the app being closed.
  override fun onPause() {
    CookieManager.getInstance().flush()
    super.onPause()
  }

  override fun onWebViewCreate(webView: WebView) {
    // Tells the Unifierr page this is the app and which version, so it can offer a small "Update app" button.
    val version = packageManager.getPackageInfo(packageName, 0).versionName ?: "0.0.0"
    webView.settings.userAgentString = webView.settings.userAgentString + " UnifierrApp/" + version
    // The page's "Update app" link points at the new APK: hand it to the phone's browser to download.
    webView.setDownloadListener { url, _, _, _, _ ->
      if (url.startsWith("https://")) startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
    }
    ViewCompat.requestApplyInsets(findViewById(android.R.id.content))
  }
}
