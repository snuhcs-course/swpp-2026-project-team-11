package com.example.metchu.ui.main

import android.graphics.Color
import android.os.Build
import android.os.Bundle
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.appcompat.app.AppCompatActivity
import com.example.metchu.data.location.FusedLocationSource
import com.example.metchu.data.repository.AllergyStore
import com.example.metchu.data.repository.AppContainer
import com.example.metchu.data.repository.AuthRepository
import com.example.metchu.data.repository.DeviceAccountStore
import com.example.metchu.data.repository.SettingsStore
import com.example.metchu.ui.account.AccountViewModel
import com.example.metchu.ui.account.AccountViewModelFactory
import com.example.metchu.ui.theme.MetchuTheme

/**
 * The only activity. [MetchuApp] draws the start and settings screens before a
 * session, and the engine's current step during one. A session starts with where the
 * user is, when that is allowed, so the server can give each cafeteria's distance. The activity is an
 * AppCompatActivity so the language picker can switch the app's locale.
 */
class MainActivity : AppCompatActivity() {

    private val viewModel: RecommendViewModel by viewModels {
        RecommendViewModelFactory(AppContainer.repository)
    }

    private val accounts: AccountViewModel by viewModels {
        AccountViewModelFactory(AppContainer.authRepository ?: AuthRepository(DeviceAccountStore(applicationContext)))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        // A transparent navigation bar, also with the three buttons: screens keep their content
        // above it, and the ones that scroll under it draw their own fade (NavigationBarFade).
        enableEdgeToEdge(navigationBarStyle = SystemBarStyle.light(Color.TRANSPARENT, Color.TRANSPARENT))
        super.onCreate(savedInstanceState)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) window.isNavigationBarContrastEnforced = false
        val allergies = AllergyStore(this)
        val settings = SettingsStore(this)
        val location = AppContainer.locationSource ?: FusedLocationSource(applicationContext)
        setContent {
            MetchuTheme {
                MetchuApp(viewModel, accounts, AppContainer.google, allergies, settings, location)
            }
        }
    }
}
