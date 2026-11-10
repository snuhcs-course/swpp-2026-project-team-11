package com.example.metchu.ui

import androidx.arch.core.executor.testing.InstantTaskExecutorRule
import com.example.metchu.FakeAuthApi
import com.example.metchu.Fixtures
import com.example.metchu.MemoryAccountStore
import com.example.metchu.R
import com.example.metchu.data.network.AccountReply
import com.example.metchu.data.network.AccountUser
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
        store.account = signedIn
        viewModel = AccountViewModel(AuthRepository(store, api))
        api.reply(AccountReply(AccountUser("metchu_user", "minji@example.com", hasPassword = true)))
        viewModel.linkGoogle { "google-id-token" }
        assertEquals(listOf("link Token device-token google-id-token"), api.calls)
        assertEquals("minji@example.com", viewModel.account.value!!.user.googleEmail)
    }

    @Test
    fun aTokenTheServerNoLongerTakesSignsOut() {
        store.account = signedIn
        viewModel = AccountViewModel(AuthRepository(store, api))
        api.fail(httpError(401, "error_not_authenticated"))
        viewModel.linkGoogle { "google-id-token" }
        assertEquals(R.string.account_error_signed_out, viewModel.error.value)
        assertNull(viewModel.account.value)
        assertNull(store.account)
    }

    @Test
    fun loggingOutForgetsTheAccountEvenOffline() {
        store.account = signedIn
        viewModel = AccountViewModel(AuthRepository(store, api))
        api.fail(IOException("unreachable"))
        viewModel.logOut()
        assertEquals(listOf("logout Token device-token"), api.calls)
        assertNull(viewModel.account.value)
        assertNull(store.account)
        assertNull(viewModel.error.value)

        store.account = signedIn
        viewModel = AccountViewModel(AuthRepository(store, api))
        api.reply(Response.success(Unit))
        viewModel.logOut()
        assertNull(viewModel.account.value)
    }
}
