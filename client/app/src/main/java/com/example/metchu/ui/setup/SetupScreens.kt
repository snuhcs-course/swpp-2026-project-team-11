package com.example.metchu.ui.setup

import androidx.compose.foundation.Image
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.example.metchu.R
import com.example.metchu.data.model.Allergen
import com.example.metchu.ui.common.ActionCapsule
import com.example.metchu.ui.common.CircleIconButton
import com.example.metchu.ui.common.Icons
import com.example.metchu.ui.common.Languages
import com.example.metchu.ui.common.PinnedTopRow
import com.example.metchu.ui.common.TopRowHeight
import com.example.metchu.ui.settings.AllergenChips
import com.example.metchu.ui.theme.MetchuColors
import com.example.metchu.ui.theme.MetchuType
import com.example.metchu.ui.theme.screenBackground

/** The first launch's first step, asked in both languages. A tap picks one and goes on. */
@Composable
fun LanguageSetupScreen(onPick: (String) -> Unit) {
    val current = LocalConfiguration.current.locales[0].language
    Box(Modifier.fillMaxSize().screenBackground()) {
        Column(Modifier.statusBarsPadding().padding(start = 20.dp, end = 20.dp, top = 72.dp)) {
            Text(stringResource(R.string.setup_language_title), Modifier.padding(bottom = 24.dp), style = MetchuType.Title)
            Languages.forEach { (tag, name) ->
                Row(
                    Modifier
                        .fillMaxWidth()
                        .heightIn(min = 60.dp)
                        .clickable(role = Role.Button) { onPick(tag) }
                        .padding(vertical = 8.dp)
                        .testTag("language_$tag"),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(stringResource(name), Modifier.weight(1f), style = MetchuType.Item, color = if (tag == current) MetchuColors.Grey900 else MetchuColors.Grey600)
                    if (tag == current) Image(Icons.Check, null, Modifier.size(24.dp), colorFilter = ColorFilter.tint(MetchuColors.Grey900))
                }
            }
        }
    }
}

/** The second step: the settings' allergy chips, kept at once, and Next. Back returns to the language. */
@Composable
fun AllergySetupScreen(allergies: List<Allergen>, onAllergies: (List<Allergen>) -> Unit, onBack: () -> Unit, onNext: () -> Unit) {
    val scroll = rememberScrollState()
    Box(Modifier.fillMaxSize().screenBackground()) {
        Column(Modifier.fillMaxSize().statusBarsPadding().verticalScroll(scroll)) {
            Spacer(Modifier.height(TopRowHeight))
            Column(Modifier.padding(start = 20.dp, end = 20.dp, top = 8.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Text(stringResource(R.string.setup_allergies_title), style = MetchuType.Title)
                Text(stringResource(R.string.allergies_body), style = MetchuType.Lead)
                AllergenChips(allergies, onAllergies)
                Text(stringResource(R.string.allergies_disclaimer), style = MetchuType.Caption.copy(lineHeight = MetchuType.Caption.fontSize * 1.55f))
            }
            Box(Modifier.navigationBarsPadding().height(120.dp))
        }
        PinnedTopRow(scroll) {
            CircleIconButton(Icons.Back, stringResource(R.string.back), onBack, Modifier.testTag("back"))
        }
        ActionCapsule(
            stringResource(R.string.setup_next), Icons.Forward, onNext, filled = true,
            modifier = Modifier.align(Alignment.BottomEnd).navigationBarsPadding().padding(end = 20.dp, bottom = 16.dp).testTag("setupNext")
        )
    }
}
