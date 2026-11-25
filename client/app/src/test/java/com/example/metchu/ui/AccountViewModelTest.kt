package com.example.metchu.ui

import androidx.arch.core.executor.testing.InstantTaskExecutorRule
import com.example.metchu.FakeAuthApi
import com.example.metchu.Fixtures
import com.example.metchu.MemoryAccountStore
import com.example.metchu.R
import com.example.metchu.data.network.AccountReply
import com.example.metchu.data.network.AccountUser
import com.example.metchu.data.network.Bookmark
import com.example.metchu.data.network.BookmarkReply
import com.example.metchu.data.network.BookmarksReply
import com.example.metchu.data.network.HistoryEntry
import com.example.metchu.data.network.HistoryReply
import com.example.metchu.data.repository.Account
import com.example.metchu.data.repository.AuthRepository
import com.example.metchu.ui.account.AccountViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import retrofit2.Response
import java.io.IOException

@OptIn(ExperimentalCoroutinesApi::class)
class AccountViewModelTest {

    @get:Rule
    val instantTasks = InstantTaskExecutorRule()

    private val api = FakeAuthApi()
    private val store = MemoryAccountStore()
    private lateinit var viewModel: AccountViewModel
    private val signedIn = Account("device-token", AccountUser("metchu_user", null, hasPassword = true))

    @Before
    fun setUp() {
        Dispatchers.setMain(UnconfinedTestDispatcher())
        viewModel = AccountViewModel(AuthRepository(store, api))
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun httpError(code: Int, fixture: String) = Fixtures.httpError(code, Fixtures.json(fixture))

    /** Starts the app with [signedIn] saved, after the server has confirmed it. */
    private fun launchSignedIn() {
        api.calls.clear()
        store.account = signedIn
        api.reply(AccountReply(signedIn.user))
        viewModel = AccountViewModel(AuthRepository(store, api))
        assertEquals(listOf("me Token device-token"), api.calls)
        api.calls.clear()
    }

    @Test
    fun aGuestLaunchAsksNothing() {
        assertEquals(emptyList<String>(), api.calls)
        assertNull(viewModel.account.value)
    }

    @Test
    fun aSavedAccountTheServerRejectsIsSignedOutOnLaunch() {
        store.account = signedIn
        api.fail(httpError(401, "error_not_authenticated"))
        viewModel = AccountViewModel(AuthRepository(store, api))
        assertEquals(listOf("me Token device-token"), api.calls)
        assertNull(viewModel.account.value)
        assertNull(store.account)
        assertNull(viewModel.error.value)
    }

    @Test
    fun aSavedAccountStaysSignedInWhenTheServerCannotSay() {
        store.account = signedIn
        api.fail(IOException("unreachable"))
        viewModel = AccountViewModel(AuthRepository(store, api))
        assertEquals(signedIn, viewModel.account.value)

        api.fail(httpError(503, "error_google_unavailable"))
        viewModel = AccountViewModel(AuthRepository(store, api))
        assertEquals(signedIn, viewModel.account.value)
        assertEquals(signedIn, store.account)
        assertNull(viewModel.error.value)
    }

    @Test
    fun theLaunchCheckShowsTheServersAccount() {
        val linked = AccountUser("metchu_user", "minji@example.com", hasPassword = true)
        store.account = signedIn
        api.reply(AccountReply(linked))
        viewModel = AccountViewModel(AuthRepository(store, api))
        assertEquals(signedIn.copy(user = linked), viewModel.account.value)
        assertEquals(signedIn.copy(user = linked), store.account)
    }

    @Test
    fun loggingOutWhileTheLaunchCheckRunsStaysLoggedOut() {
        store.account = signedIn
        api.answer {
            store.account = null
            AccountReply(signedIn.user)
        }
        viewModel = AccountViewModel(AuthRepository(store, api))
        assertNull(viewModel.account.value)
        assertNull(store.account)
    }

    @Test
    fun loggingInShowsTheAccount() {
        api.reply(Fixtures.signedIn())
        viewModel.logIn(" metchu_user ", "bap-meokja-2026")
        assertEquals(listOf("login metchu_user"), api.calls)
        assertEquals("metchu_user", viewModel.account.value!!.user.username)
        assertEquals(viewModel.account.value, store.account)
        assertNull(viewModel.error.value)
        assertEquals(false, viewModel.busy.value)
    }

    @Test
    fun aWrongPasswordSaysSo() {
        api.fail(httpError(401, "error_invalid_credentials"))
        viewModel.logIn("metchu_user", "wrong-pass-2026")
        assertEquals(R.string.account_error_credentials, viewModel.error.value)
        assertNull(viewModel.account.value)
    }

    @Test
    fun aTakenUsernameSaysSo() {
        api.fail(httpError(409, "error_username_taken"))
        viewModel.signUp("metchu_user", "bap-meokja-2026", "bap-meokja-2026")
        assertEquals(R.string.account_error_taken, viewModel.error.value)
    }

    @Test
    fun theFormIsCheckedBeforeAsking() {
        viewModel.signUp("metchu_user", "bap-meokja-2026", "bap-meokja-2025")
        assertEquals(R.string.account_error_mismatch, viewModel.error.value)
        viewModel.logIn("  ", "bap-meokja-2026")
        assertEquals(R.string.account_error_empty, viewModel.error.value)
        viewModel.signUp("metchu_user", "", "")
        assertEquals(R.string.account_error_empty, viewModel.error.value)
        assertEquals(emptyList<String>(), api.calls)
    }

    @Test
    fun withoutTheServerItSaysSo() {
        api.fail(IOException("unreachable"))
        viewModel.logIn("metchu_user", "bap-meokja-2026")
        assertEquals(R.string.error_no_server, viewModel.error.value)
    }

    @Test
    fun googleSignsInWithThePickersToken() {
        api.reply(Fixtures.signedIn())
        viewModel.google { "google-id-token" }
        assertEquals(listOf("google google-id-token"), api.calls)
        assertEquals("metchu_user", viewModel.account.value!!.user.username)
    }

    @Test
    fun closingGooglesPickerChangesNothing() {
        viewModel.google { null }
        assertEquals(emptyList<String>(), api.calls)
        assertNull(viewModel.account.value)
        assertNull(viewModel.error.value)
    }

    @Test
    fun aFailingPickerSaysGoogleSignInFailed() {
        viewModel.google { throw IllegalStateException("no Google account on the device") }
        assertEquals(R.string.account_error_google, viewModel.error.value)
        api.fail(httpError(503, "error_google_unavailable"))
        viewModel.google { "google-id-token" }
        assertEquals(R.string.account_error_google_unavailable, viewModel.error.value)
    }

    @Test
    fun linkingGoogleShowsTheLinkedAddress() {
        launchSignedIn()
        api.reply(AccountReply(AccountUser("metchu_user", "minji@example.com", hasPassword = true)))
        viewModel.linkGoogle { "google-id-token" }
        assertEquals(listOf("link Token device-token google-id-token"), api.calls)
        assertEquals("minji@example.com", viewModel.account.value!!.user.googleEmail)
    }

    @Test
    fun aTokenTheServerNoLongerTakesSignsOut() {
        launchSignedIn()
        api.fail(httpError(401, "error_not_authenticated"))
        viewModel.linkGoogle { "google-id-token" }
        assertEquals(R.string.account_error_signed_out, viewModel.error.value)
        assertNull(viewModel.account.value)
        assertNull(store.account)
    }

    @Test
    fun loggingOutForgetsTheAccountEvenOffline() {
        launchSignedIn()
        api.fail(IOException("unreachable"))
        viewModel.logOut()
        assertEquals(listOf("logout Token device-token"), api.calls)
        assertNull(viewModel.account.value)
        assertNull(store.account)
        assertNull(viewModel.error.value)

        launchSignedIn()
        api.reply(Response.success(Unit))
        viewModel.logOut()
        assertNull(viewModel.account.value)
    }

    // --- bookmarks and history ---

    private val saved = Bookmark(5, "짜장면", "홍콩반점 낙성대점", "2026-11-25T03:24:00.398Z", id = 1)

    private fun launchWithBookmarks(vararg bookmarks: Bookmark) {
        launchSignedIn()
        api.reply(BookmarksReply(bookmarks.toList()))
        viewModel.loadBookmarks()
        api.calls.clear()
    }

    @Test
    fun aGuestLoadsNothingAndCannotBookmark() {
        viewModel.loadBookmarks()
        viewModel.loadHistory()
        viewModel.toggleBookmark(5, "짜장면", "홍콩반점 낙성대점")
        assertEquals(emptyList<String>(), api.calls)
        assertNull(viewModel.bookmarks.value)
        assertNull(viewModel.history.value)
    }

    @Test
    fun theListsLoadForTheSignedInAccount() {
        launchSignedIn()
        val entry = HistoryEntry("2026-11-02", "LU", 5, "짜장면", "홍콩반점 낙성대점", "2026-11-25T03:24:00.391Z")
        api.reply(BookmarksReply(listOf(saved)))
        api.reply(HistoryReply(listOf(entry)))
        viewModel.loadBookmarks()
        viewModel.loadHistory()
        assertEquals(listOf("bookmarks Token device-token", "history Token device-token"), api.calls)
        assertEquals(listOf(saved), viewModel.bookmarks.value)
        assertEquals(listOf(entry), viewModel.history.value)
        assertEquals(false, viewModel.savedFailed.value)
    }

    @Test
    fun aFailedLoadCanBeRetried() {
        launchSignedIn()
        api.fail(IOException("offline"))
        viewModel.loadHistory()
        assertEquals(true, viewModel.savedFailed.value)
        assertNull(viewModel.history.value)
        api.reply(HistoryReply(emptyList()))
        viewModel.loadHistory()
        assertEquals(false, viewModel.savedFailed.value)
        assertEquals(emptyList<HistoryEntry>(), viewModel.history.value)
    }

    @Test
    fun aToggleSavesAndThenRemovesTheDish() {
        launchWithBookmarks()
        api.reply(BookmarkReply(saved))
        viewModel.toggleBookmark(5, "짜장면", "홍콩반점 낙성대점")
        assertEquals(listOf(saved), viewModel.bookmarks.value)

        api.reply(Response.success(Unit))
        viewModel.toggleBookmark(5, "짜장면", "홍콩반점 낙성대점")
        assertEquals(listOf("bookmark Token device-token 5", "unbookmark Token device-token 1"), api.calls)
        assertEquals(emptyList<Bookmark>(), viewModel.bookmarks.value)
    }

    @Test
    fun theSameDishUnderAnotherFoodIdIsTheSavedOne() {
        launchWithBookmarks(saved)
        api.reply(Response.success(Unit))
        viewModel.toggleBookmark(9, "짜장면", "홍콩반점 낙성대점")
        assertEquals(listOf("unbookmark Token device-token 1"), api.calls)
        assertEquals(emptyList<Bookmark>(), viewModel.bookmarks.value)
    }

    @Test
    fun theSameNameAtAnotherRestaurantIsAnotherBookmark() {
        launchWithBookmarks(saved)
        val elsewhere = Bookmark(5, "짜장면", "다른 곳", "2026-11-25T03:25:00.000Z", id = 2)
        api.reply(BookmarkReply(elsewhere))
        viewModel.toggleBookmark(5, "짜장면", "다른 곳")
        assertEquals(listOf("bookmark Token device-token 5"), api.calls)
        assertEquals(listOf(elsewhere, saved), viewModel.bookmarks.value)
    }

    @Test
    fun theListChangesAtOnceAndTapsWaitForTheServer() {
        launchWithBookmarks()
        var shownMeanwhile: List<Bookmark>? = null
        api.answer {
            shownMeanwhile = viewModel.bookmarks.value
            viewModel.toggleBookmark(5, "짜장면", "홍콩반점 낙성대점")
            BookmarkReply(saved)
        }
        viewModel.toggleBookmark(5, "짜장면", "홍콩반점 낙성대점")
        assertEquals(listOf(Bookmark(5, "짜장면", "홍콩반점 낙성대점")), shownMeanwhile)
        assertEquals(listOf("bookmark Token device-token 5"), api.calls)
        assertEquals(listOf(saved), viewModel.bookmarks.value)
    }

    @Test
    fun aListLoadedWhileASaveIsOnItsWayKeepsTheSave() {
        launchWithBookmarks()
        api.answer {
            api.reply(BookmarksReply(emptyList()))
            viewModel.loadBookmarks()
            BookmarkReply(saved)
        }
        viewModel.toggleBookmark(5, "짜장면", "홍콩반점 낙성대점")
        assertEquals(listOf(saved), viewModel.bookmarks.value)
    }

    @Test
    fun aListLoadedWhileARemovalIsOnItsWayKeepsTheRemoval() {
        launchWithBookmarks(saved)
        api.answer {
            api.reply(BookmarksReply(listOf(saved)))
            viewModel.loadBookmarks()
            Response.success(Unit)
        }
        viewModel.toggleBookmark(5, "짜장면", "홍콩반점 낙성대점")
        assertEquals(emptyList<Bookmark>(), viewModel.bookmarks.value)
    }

    @Test
    fun aListSentBeforeAChangeAndAnsweredAfterItKeepsTheChange() {
        launchWithBookmarks()
        api.answer {
            api.reply(BookmarkReply(saved))
            viewModel.toggleBookmark(5, "짜장면", "홍콩반점 낙성대점")
            BookmarksReply(emptyList())
        }
        viewModel.loadBookmarks()
        assertEquals(listOf(saved), viewModel.bookmarks.value)
    }

    @Test
    fun aRefusedToggleIsPutBack() {
        launchWithBookmarks(saved)
        api.fail(IOException("offline"))
        viewModel.toggleBookmark(5, "짜장면", "홍콩반점 낙성대점")
        assertEquals(listOf(saved), viewModel.bookmarks.value)
        api.fail(IOException("offline"))
        viewModel.toggleBookmark(6, "짬뽕", "홍콩반점 낙성대점")
        assertEquals(listOf(saved), viewModel.bookmarks.value)
    }

    @Test
    fun aRejectedTokenSignsOutAndForgetsTheLists() {
        launchWithBookmarks(saved)
        api.fail(httpError(401, "error_not_authenticated"))
        viewModel.toggleBookmark(5, "짜장면", "홍콩반점 낙성대점")
        assertNull(viewModel.account.value)
        assertNull(store.account)
        assertNull(viewModel.bookmarks.value)
        assertEquals(R.string.account_error_signed_out, viewModel.error.value)
    }

    @Test
    fun loggingOutForgetsTheLists() {
        launchWithBookmarks(saved)
        api.reply(Response.success(Unit))
        viewModel.logOut()
        assertNull(viewModel.bookmarks.value)
    }
}
