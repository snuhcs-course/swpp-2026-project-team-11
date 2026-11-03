package com.example.metchu.ui.common

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.selection.selectable
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.example.metchu.ui.theme.MetchuColors
import com.example.metchu.ui.theme.MetchuType
import com.example.metchu.ui.theme.ScreenGradient

/** One choice in a [BottomSheetPicker]. */
class PickerOption(val label: String, val note: String?, val selected: Boolean, val onPick: () -> Unit)

/** The sheet's entrance curve, shared with the result sheet. */
val SheetEasing = CubicBezierEasing(0.2f, 0.8f, 0.2f, 1f)

/**
 * A modal list that rises from the bottom over a dimmed screen. The picked option is
 * dark with a check; the others are grey, like past questions.
 */
@Composable
fun BottomSheetPicker(visible: Boolean, title: String, options: List<PickerOption>, onDismiss: () -> Unit) {
    BottomSheet(visible, title, onDismiss) {
        options.forEach { option ->
            Row(
                Modifier
                    .fillMaxWidth()
                    .heightIn(min = 60.dp)
                    .selectable(option.selected, role = Role.RadioButton, onClick = option.onPick)
                    .padding(vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(Modifier.weight(1f)) {
                    Text(option.label, style = MetchuType.Item, color = if (option.selected) MetchuColors.Grey900 else MetchuColors.Grey600)
                    if (option.note != null) Text(option.note, style = MetchuType.Caption)
                }
                if (option.selected) {
                    Image(Icons.Check, null, Modifier.size(24.dp), colorFilter = ColorFilter.tint(MetchuColors.Grey900))
                }
            }
        }
    }
}

/** A panel that rises from the bottom over a dimmed screen, with [title] above [content]. A tap outside it calls [onDismiss]. */
@Composable
fun BottomSheet(visible: Boolean, title: String, onDismiss: () -> Unit, content: @Composable ColumnScope.() -> Unit) {
    Box(Modifier.fillMaxSize()) {
        AnimatedVisibility(visible, enter = fadeIn(tween(200)), exit = fadeOut(tween(200))) {
            Box(
                Modifier.fillMaxSize().background(MetchuColors.Grey900.copy(alpha = 0.48f))
                    .clickable(remember { MutableInteractionSource() }, indication = null, onClick = onDismiss)
            )
        }
        AnimatedVisibility(
            visible,
            modifier = Modifier.align(Alignment.BottomCenter),
            enter = slideInVertically(tween(320, easing = SheetEasing)) { it },
            exit = slideOutVertically(tween(240)) { it }
        ) {
            Column(
                Modifier
                    .fillMaxWidth()
                    .cssShadow(RectangleShape, (-6).dp, 20.dp, 0.12f)
                    .background(ScreenGradient)
                    .navigationBarsPadding()
                    .padding(start = 20.dp, end = 20.dp, top = 28.dp, bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Text(title, Modifier.padding(bottom = 4.dp), style = MetchuType.Caption)
                content()
            }
        }
    }
}
