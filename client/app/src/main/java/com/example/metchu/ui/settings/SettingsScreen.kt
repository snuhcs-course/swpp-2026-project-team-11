package com.example.metchu.ui.settings

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateDpAsState
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
import androidx.compose.foundation.layout.Spacer
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
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.annotation.StringRes
import com.example.metchu.R
import com.example.metchu.data.model.Allergen
import com.example.metchu.data.model.Engine
import com.example.metchu.data.repository.Account
import com.example.metchu.ui.common.CircleIconButton
import com.example.metchu.ui.common.Icons
import com.example.metchu.ui.common.LabelCapsule
import com.example.metchu.ui.common.NavigationBarFade
import com.example.metchu.ui.common.PinnedTopRow
import com.example.metchu.ui.common.TopRowHeight
import com.example.metchu.ui.common.chipShadow
import com.example.metchu.ui.theme.MetchuColors
import com.example.metchu.ui.theme.MetchuType
import com.example.metchu.ui.theme.screenBackground

/**
 * The account, allergies to avoid and, for development, which engine asks the questions.
 * Every change is kept at once, so there is no save button. A guest opens the account
 * screen with [onAccount]; [onLinkGoogle] is null when this build has no Google client ID.
 */
@Composable
fun SettingsScreen(
    account: Account?,
    accountBusy: Boolean,
    @StringRes accountError: Int?,
    allergies: List<Allergen>,
    engine: String,
    onAccount: () -> Unit,
    onLinkGoogle: (() -> Unit)?,
    onLogOut: () -> Unit,
    onAllergies: (List<Allergen>) -> Unit,
    onEngine: (String) -> Unit,
    onBack: () -> Unit
) {
    val scroll = rememberScrollState()
    Box(Modifier.fillMaxSize().screenBackground()) {
        Column(Modifier.fillMaxSize().statusBarsPadding().verticalScroll(scroll)) {
            Spacer(Modifier.height(TopRowHeight))
            Text(stringResource(R.string.settings), Modifier.padding(start = 20.dp, end = 20.dp, top = 8.dp), style = MetchuType.Title)

            Section(stringResource(R.string.settings_account)) {
                AccountSection(account, accountBusy, accountError, onAccount, onLinkGoogle, onLogOut)
            }

            Section(stringResource(R.string.settings_allergies)) {
                Text(stringResource(R.string.allergies_body), style = MetchuType.Item)
                AllergenChips(allergies, onAllergies)
                Text(stringResource(R.string.allergies_disclaimer), style = MetchuType.Caption.copy(lineHeight = MetchuType.Caption.fontSize * 1.55f))
            }

            Section(stringResource(R.string.settings_engine)) {
                Column {
                    EngineRow(Engine.DECISION_TREE, R.string.engine_decision_tree, R.string.engine_decision_tree_hint, engine, onEngine)
                    EngineRow(Engine.RL, R.string.engine_rl, R.string.engine_rl_hint, engine, onEngine)
                    EngineRow(Engine.LLM, R.string.engine_llm, R.string.engine_llm_hint, engine, onEngine, unavailable = R.string.engine_unavailable)
                }
            }
            Box(Modifier.navigationBarsPadding().height(96.dp))
        }
        NavigationBarFade(Modifier.align(Alignment.BottomCenter))
        PinnedTopRow(scroll) {
            CircleIconButton(Icons.Back, stringResource(R.string.back), onBack, Modifier.testTag("back"))
        }
    }
}

/** A guest sees how to sign in; a signed-in user, the account, its Google link and signing out. */
@Composable
private fun AccountSection(
    account: Account?,
    busy: Boolean,
    @StringRes error: Int?,
    onAccount: () -> Unit,
    onLinkGoogle: (() -> Unit)?,
    onLogOut: () -> Unit
) {
    if (account == null) {
        Text(stringResource(R.string.account_guest), style = MetchuType.Item)
        Text(stringResource(R.string.account_guest_hint), style = MetchuType.Caption)
        LabelCapsule(stringResource(R.string.account_open), onAccount, filled = true, modifier = Modifier.testTag("accountOpen"))
    } else {
        val email = account.user.googleEmail
        Text(account.user.username, Modifier.testTag("accountName"), style = MetchuType.Item)
        Text(
            when {
                email == null -> stringResource(R.string.account_google_none)
                email.isEmpty() -> stringResource(R.string.account_google_linked)
                else -> stringResource(R.string.account_google_linked_as, email)
            },
            style = MetchuType.Caption
        )
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            if (email == null && onLinkGoogle != null) {
                LabelCapsule(stringResource(R.string.account_link_google), onLinkGoogle, filled = false, enabled = !busy,
                             modifier = Modifier.testTag("accountLinkGoogle"))
            }
            LabelCapsule(stringResource(R.string.account_log_out), onLogOut, filled = false, enabled = !busy,
                         modifier = Modifier.testTag("accountLogOut"))
        }
    }
    if (error != null) {
        Text(stringResource(error), Modifier.testTag("accountError"), style = MetchuType.Label, color = MetchuColors.Primary)
    }
}

@Composable
private fun Section(caption: String, content: @Composable () -> Unit) {
    Column(Modifier.padding(start = 20.dp, end = 20.dp, top = 28.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text(caption, style = MetchuType.Caption)
        content()
    }
}

/** One chip per allergen, here and on the first launch. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun AllergenChips(picked: List<Allergen>, onChange: (List<Allergen>) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Allergen.entries.forEach { allergen ->
            val on = allergen in picked
            val background by animateColorAsState(if (on) MetchuColors.Primary else Color.White, label = "chip")
            // Only the fill changes, so a tap never widens the chip and moves the ones after it.
            Box(
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
                contentAlignment = Alignment.Center
            ) {
                Text(
                    stringResource(allergen.label),
                    style = MetchuType.Label.copy(fontWeight = MetchuType.Caption.fontWeight),
                    color = if (on) Color.White else MetchuColors.Grey900
                )
            }
        }
    }
}

@Composable
private fun EngineRow(id: String, label: Int, hint: Int, selected: String, onPick: (String) -> Unit, unavailable: Int? = null) {
    val enabled = unavailable == null
    val on = enabled && id == selected
    val ink by animateColorAsState(if (on) MetchuColors.Grey900 else MetchuColors.Grey600, label = "engine")
    val ring by animateDpAsState(if (on) 7.dp else 2.5.dp, label = "ring")
    // Only the control fades; the note saying why it is off keeps its readable color.
    val dim = Modifier.alpha(if (enabled) 1f else 0.45f)
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 64.dp)
            .selectable(on, enabled = enabled, role = Role.RadioButton) { onPick(id) }
            .padding(vertical = 10.dp)
            .testTag("engine_$id"),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(label), dim, style = MetchuType.Item, color = ink)
                if (unavailable != null) Text(stringResource(unavailable), Modifier.padding(start = 8.dp), style = MetchuType.Caption)
            }
            Text(stringResource(hint), dim, style = MetchuType.Caption)
        }
        Box(
            dim.size(24.dp).drawBehind {
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
