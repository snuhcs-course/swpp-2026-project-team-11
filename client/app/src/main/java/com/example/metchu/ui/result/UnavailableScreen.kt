package com.example.metchu.ui.result

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.example.metchu.R
import com.example.metchu.data.model.SessionState
import com.example.metchu.ui.common.Pill
import com.example.metchu.ui.common.PillSegment
import com.example.metchu.ui.start.Meal
import com.example.metchu.ui.theme.MetchuType
import com.example.metchu.ui.theme.screenBackground

/** Why nothing can be recommended, in the question screen's large type, and the way back. */
@Composable
fun UnavailableScreen(session: SessionState, hasAllergies: Boolean, onHome: () -> Unit) {
    val meal = Meal.of(session.meal)?.let { stringResource(it.label) } ?: stringResource(R.string.meal_any)
    val message = when {
        session.step.reason != "empty_candidates" -> stringResource(R.string.unavailable_exhausted)
        hasAllergies -> stringResource(R.string.unavailable_no_safe_menu, meal, session.date)
        else -> stringResource(R.string.unavailable_no_menu, meal, session.date)
    }
    Box(Modifier.fillMaxSize().screenBackground()) {
        // "Start over" sits in the top-right corner, where the result screen has it.
        Row(
            Modifier.statusBarsPadding().fillMaxWidth().height(56.dp).padding(start = 20.dp, end = 20.dp, top = 6.dp),
            horizontalArrangement = Arrangement.End
        ) {
            Pill { PillSegment(stringResource(R.string.result_home), onHome, modifier = Modifier.testTag("home")) }
        }
        Text(
            message,
            Modifier.statusBarsPadding().padding(start = 20.dp, end = 20.dp, top = 76.dp).testTag("unavailable"),
            style = MetchuType.Title
        )
    }
}
