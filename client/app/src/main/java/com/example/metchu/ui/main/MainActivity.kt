package com.example.metchu.ui.main

import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.appcompat.app.AppCompatActivity
import com.example.metchu.data.location.FusedLocationSource
import com.example.metchu.data.repository.AllergyStore
import com.example.metchu.data.repository.AppContainer
import com.example.metchu.data.repository.SettingsStore
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

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        val allergies = AllergyStore(this)
        val settings = SettingsStore(this)
        val location = AppContainer.locationSource ?: FusedLocationSource(applicationContext)
        setContent {
            MetchuTheme {
                MetchuApp(viewModel, allergies, settings, location)
            }
        }
    }
}
