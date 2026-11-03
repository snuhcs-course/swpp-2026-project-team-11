package com.example.metchu.ui.common

import androidx.appcompat.app.AppCompatDelegate
import androidx.core.os.LocaleListCompat
import com.example.metchu.R

/** The app's languages: locale tags with their names written in themselves. */
val Languages = listOf("ko" to R.string.language_ko, "en" to R.string.language_en)

/** Switches the app to [tag]. The activity handles the change itself, so Compose redraws in place. */
fun setLanguage(tag: String) = AppCompatDelegate.setApplicationLocales(LocaleListCompat.forLanguageTags(tag))
