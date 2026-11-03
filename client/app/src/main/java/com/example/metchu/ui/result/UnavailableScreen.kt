package com.example.metchu.ui.result

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.example.metchu.R
import com.example.metchu.data.model.SessionState
import com.example.metchu.ui.common.CircleIconButton
import com.example.metchu.ui.common.Icons
import com.example.metchu.ui.common.TopRow
import com.example.metchu.ui.start.Meal
import com.example.metchu.ui.theme.MetchuType
import com.example.metchu.ui.theme.screenBackground

/** Why nothing can be recommended, in the question screen's large type, and the way back. */
@Composable
fun UnavailableScreen(session: SessionState, hasAllergies: Boolean, onHome: () -> Unit) {
    val meal = Meal.of(session.meal)?.let { stringResource(it.label) } ?: stringResource(R.string.meal_any)
    val message = when {
        session.step.reason != "empty_candidates" -> stringResource(R.string.unavailable_exhausted)
        hasAllergies -> stringResource(R.string.unavailable_no_safe_menu, meal)
        else -> stringResource(R.string.unavailable_no_menu, meal)
    }
    Box(Modifier.fillMaxSize().screenBackground()) {
        // Home sits in the top-right corner, where the question and result screens have it.
        TopRow(Modifier.statusBarsPadding(), Arrangement.End) {
            CircleIconButton(Icons.Home, stringResource(R.string.result_home), onHome, Modifier.testTag("home"))
        }
        Text(
            message,
            Modifier.statusBarsPadding().padding(start = 20.dp, end = 20.dp, top = 84.dp).testTag("unavailable"),
            style = MetchuType.Title
        )
    }
}
