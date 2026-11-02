package com.example.metchu.ui.start

import androidx.annotation.StringRes
import com.example.metchu.R

/** The meals the start screen offers, with the server's meal codes. */
enum class Meal(val code: String, @StringRes val label: Int) {
    BREAKFAST("BR", R.string.meal_breakfast),
    LUNCH("LU", R.string.meal_lunch),
    DINNER("DN", R.string.meal_dinner);

    companion object {
        /** The meal the cafeterias serve next at [hour] (0–23): breakfast until 10, lunch until 15. */
        fun at(hour: Int): Meal = when {
            hour < 10 -> BREAKFAST
            hour < 15 -> LUNCH
            else -> DINNER
        }

        fun of(code: String?): Meal? = entries.firstOrNull { it.code == code }
    }
}
