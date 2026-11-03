package com.example.metchu.ui.settings

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.example.metchu.R
import com.example.metchu.data.model.Allergen
import com.example.metchu.data.model.Engine
import com.example.metchu.ui.common.CircleIconButton
import com.example.metchu.ui.common.Icons
import com.example.metchu.ui.common.chipShadow
import com.example.metchu.ui.theme.MetchuColors
import com.example.metchu.ui.theme.MetchuType
import com.example.metchu.ui.theme.screenBackground

/**
 * Allergies to avoid and, for development, which engine asks the questions. Every
 * change is kept at once, so there is no save button.
 */
@Composable
fun SettingsScreen(
    allergies: List<Allergen>,
    engine: String,
    onAllergies: (List<Allergen>) -> Unit,
    onEngine: (String) -> Unit,
    onBack: () -> Unit
) {
    Box(Modifier.fillMaxSize().screenBackground()) {
        Column(Modifier.fillMaxSize().statusBarsPadding().verticalScroll(rememberScrollState())) {
            Row(Modifier.height(56.dp).padding(start = 20.dp, top = 6.dp)) {
                CircleIconButton(Icons.Back, stringResource(R.string.back), onBack, Modifier.testTag("back"))
            }
            Text(stringResource(R.string.settings), Modifier.padding(start = 20.dp, end = 20.dp, top = 8.dp), style = MetchuType.Title)

            Section(stringResource(R.string.settings_allergies)) {
                Text(stringResource(R.string.allergies_body), style = MetchuType.Item)
                AllergenChips(allergies, onAllergies)
                Text(stringResource(R.string.allergies_disclaimer), style = MetchuType.Caption.copy(lineHeight = MetchuType.Caption.fontSize * 1.55f))
            }

            Section(stringResource(R.string.settings_engine)) {
                Column {
                    EngineRow(Engine.DECISION_TREE, R.string.engine_decision_tree, R.string.engine_decision_tree_hint, engine, onEngine)
                    EngineRow(Engine.RL, R.string.engine_rl, R.string.engine_rl_hint, engine, onEngine)
                    EngineRow(Engine.LLM, R.string.engine_llm, R.string.engine_llm_hint, engine, onEngine)
                }
            }
            Box(Modifier.navigationBarsPadding().height(96.dp))
        }
    }
}

@Composable
private fun Section(caption: String, content: @Composable () -> Unit) {
    Column(Modifier.padding(start = 20.dp, end = 20.dp, top = 28.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text(caption, style = MetchuType.Caption)
        content()
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun AllergenChips(picked: List<Allergen>, onChange: (List<Allergen>) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Allergen.entries.forEach { allergen ->
            val on = allergen in picked
            val background by animateColorAsState(if (on) MetchuColors.Primary else Color.White, label = "chip")
            Row(
                Modifier
                    .height(40.dp)
                    .chipShadow()
                    .clip(CircleShape)
                    .background(background)
                    .toggleable(on, role = Role.Checkbox) { checked ->
                        onChange(Allergen.entries.filter { if (it == allergen) checked else it in picked })
                    }
                    .padding(horizontal = 14.dp)
                    .testTag("allergen_${allergen.id}"),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                if (on) Image(Icons.Check, null, Modifier.size(16.dp), colorFilter = ColorFilter.tint(Color.White))
                Text(
                    stringResource(allergen.label),
                    style = MetchuType.Label.copy(fontWeight = if (on) MetchuType.Label.fontWeight else MetchuType.Caption.fontWeight),
                    color = if (on) Color.White else MetchuColors.Grey900
                )
            }
        }
    }
}

@Composable
private fun EngineRow(id: String, label: Int, hint: Int, selected: String, onPick: (String) -> Unit) {
    val on = id == selected
    val ink by animateColorAsState(if (on) MetchuColors.Grey900 else MetchuColors.Grey400, label = "engine")
    val ring by animateDpAsState(if (on) 7.dp else 2.5.dp, label = "ring")
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 64.dp)
            .selectable(on, role = Role.RadioButton) { onPick(id) }
            .padding(vertical = 10.dp)
            .testTag("engine_$id"),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(Modifier.weight(1f)) {
            Text(stringResource(label), style = MetchuType.Item, color = ink)
            Text(stringResource(hint), style = MetchuType.Caption)
        }
        Box(
            Modifier.size(24.dp).drawBehind {
                val width = ring.toPx()
                drawCircle(
                    if (on) MetchuColors.Primary else MetchuColors.Grey300,
                    radius = (size.minDimension - width) / 2,
                    style = Stroke(width)
                )
            }
        )
    }
}
