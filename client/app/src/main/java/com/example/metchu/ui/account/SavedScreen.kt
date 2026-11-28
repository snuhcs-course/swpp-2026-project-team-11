package com.example.metchu.ui.account

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.example.metchu.R
import com.example.metchu.data.network.Bookmark
import com.example.metchu.data.network.HistoryEntry
import com.example.metchu.ui.common.CircleIconButton
import com.example.metchu.ui.common.Icons
import com.example.metchu.ui.common.LabelCapsule
import com.example.metchu.ui.common.NavigationBarFade
import com.example.metchu.ui.common.PinnedTopRow
import com.example.metchu.ui.common.Spinner
import com.example.metchu.ui.common.TopRowHeight
import com.example.metchu.ui.theme.MetchuColors
import com.example.metchu.ui.theme.MetchuType
import com.example.metchu.ui.theme.screenBackground

/** The account's lists, opened from the settings. */
enum class SavedList { BOOKMARKS, HISTORY }

/** One line of a list: a bookmark's restaurant and address, or a dish and where and when it was. */
private data class SavedRow(val title: String, val detail: String?)

/**
 * The signed-in account's bookmarks or history, newest first. The list is null while it
 * loads; [failed] offers [onRetry] instead. Dish and restaurant names stay as the server sent them;
 * a bookmark without an address (the campus cafeterias) shows its name alone.
 */
@Composable
fun SavedScreen(
    list: SavedList,
    bookmarks: List<Bookmark>?,
    history: List<HistoryEntry>?,
    failed: Boolean,
    onRetry: () -> Unit,
    onBack: () -> Unit
) {
    val rows = when (list) {
        SavedList.BOOKMARKS -> bookmarks?.map { SavedRow(it.restaurant, it.address) }
        SavedList.HISTORY -> history?.map {
            SavedRow(it.displayName, "${it.restaurant} · ${it.date} · ${mealName(it.meal)}")
        }
    }
    val scroll = rememberScrollState()
    Box(Modifier.fillMaxSize().screenBackground()) {
        Column(Modifier.fillMaxSize().statusBarsPadding().verticalScroll(scroll)) {
            Spacer(Modifier.height(TopRowHeight))
            Text(
                stringResource(if (list == SavedList.BOOKMARKS) R.string.account_bookmarks else R.string.account_history),
                Modifier.padding(start = 20.dp, end = 20.dp, top = 8.dp, bottom = 12.dp),
                style = MetchuType.Title
            )
            Column(Modifier.padding(horizontal = 20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                when {
                    rows != null && rows.isEmpty() -> Text(
                        stringResource(if (list == SavedList.BOOKMARKS) R.string.bookmarks_empty else R.string.history_empty),
                        Modifier.testTag("savedEmpty"),
                        style = MetchuType.Caption
                    )
                    rows != null -> rows.forEach { row ->
                        Column(Modifier.fillMaxWidth().padding(vertical = 4.dp).testTag("savedRow")) {
                            Text(row.title, style = MetchuType.Item)
                            row.detail?.let { Text(it, style = MetchuType.Caption) }
                        }
                    }
                    failed -> {
                        Text(stringResource(R.string.saved_failed), style = MetchuType.Label, color = MetchuColors.Primary)
                        LabelCapsule(stringResource(R.string.retry), onRetry, filled = false, modifier = Modifier.testTag("savedRetry"))
                    }
                    else -> Box(Modifier.fillMaxWidth().padding(top = 24.dp), contentAlignment = Alignment.Center) {
                        Spinner(MetchuColors.Primary, 28.dp)
                    }
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

@Composable
private fun mealName(meal: String?): String = stringResource(
    when (meal) {
        "BR" -> R.string.meal_breakfast
        "LU" -> R.string.meal_lunch
        "DN" -> R.string.meal_dinner
        else -> R.string.meal_any
    }
)
