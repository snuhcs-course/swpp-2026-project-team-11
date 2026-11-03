package com.example.metchu.ui.result

import androidx.compose.foundation.layout.Column
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

/** Why nothing can be recommended in the question screen's large type, what to do in a caption, and the way back. */
@Composable
fun UnavailableScreen(session: SessionState, hasAllergies: Boolean, onBack: () -> Unit) {
    val meal = Meal.of(session.meal)?.let { stringResource(it.label) } ?: stringResource(R.string.meal_any)
    val (message, hint) = when {
        session.step.reason != "empty_candidates" ->
            stringResource(R.string.unavailable_exhausted) to stringResource(R.string.unavailable_exhausted_hint)
        hasAllergies ->
            stringResource(R.string.unavailable_no_safe_menu, meal) to stringResource(R.string.unavailable_no_safe_menu_hint)
        else -> stringResource(R.string.unavailable_no_menu, meal) to stringResource(R.string.unavailable_no_menu_hint)
    }
    Column(Modifier.fillMaxSize().screenBackground().statusBarsPadding()) {
        TopRow {
            CircleIconButton(Icons.Back, stringResource(R.string.back), onBack, Modifier.testTag("back"))
        }
        Text(message, Modifier.padding(start = 20.dp, end = 20.dp, top = 20.dp).testTag("unavailable"), style = MetchuType.Title)
        Text(hint, Modifier.padding(start = 20.dp, end = 20.dp, top = 12.dp), style = MetchuType.Caption)
    }
}
