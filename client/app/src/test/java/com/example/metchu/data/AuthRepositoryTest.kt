package com.example.metchu.data

import com.example.metchu.Fixtures
import com.example.metchu.MemoryAccountStore
import com.example.metchu.data.network.AccountUser
import com.example.metchu.data.network.RetrofitInstance
import com.example.metchu.data.repository.Account
import com.example.metchu.data.repository.AuthRepository
import com.google.gson.JsonParser
import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import retrofit2.HttpException
import java.io.IOException

/** Real Retrofit and Gson against a local fake server: what the account calls send and keep. */
class AuthRepositoryTest {

    private val server = MockWebServer()
    private val store = MemoryAccountStore()
    private lateinit var repository: AuthRepository
    private val signedIn = Account("device-token", AccountUser("metchu_user", null, hasPassword = true))

    @Before
    fun setUp() {
        server.start()
        repository = AuthRepository(store, RetrofitInstance.createAuth(server.url("/").toString()))
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    private fun reply(fixture: String, code: Int = 200) {
        server.enqueue(MockResponse().setResponseCode(code).setBody(Fixtures.json(fixture)))
    }

    private fun sentJson() = server.takeRequest().let { it.path to JsonParser().parse(it.body.readUtf8()).asJsonObject.toString() }

    @Test
    fun signUpSendsTheCredentialsAndKeepsTheAccount() = runTest {
        reply("auth_signed_in", 201)
        val account = repository.signUp("metchu_user", "bap-meokja-2026")

        assertEquals("/api/auth/signup/" to """{"username":"metchu_user","password":"bap-meokja-2026"}""", sentJson())
        assertEquals(Fixtures.signedIn().token, account.token)
        assertEquals(AccountUser("metchu_user", null, hasPassword = true), account.user)
        assertEquals(account, store.account)
    }

    @Test
    fun aWrongPasswordKeepsNothingAndNamesTheError() = runTest {
        reply("error_invalid_credentials", 401)
        try {
            repository.logIn("metchu_user", "wrong-pass-2026")
            fail("expected HttpException")
        } catch (e: HttpException) {
            assertEquals("invalid_credentials", repository.errorCode(e))
        }
        assertNull(store.account)
    }

    @Test
    fun googleSendsTheIdToken() = runTest {
        server.enqueue(MockResponse().setResponseCode(201).setBody(
            """{"token": "g-device", "user": {"username": "minji", "google_email": "minji@example.com", "has_password": false}, "created": true}"""
        ))
        val account = repository.google("google-id-token")

        assertEquals("/api/auth/google/" to """{"id_token":"google-id-token"}""", sentJson())
        assertEquals(Account("g-device", AccountUser("minji", "minji@example.com", hasPassword = false)), store.account)
        assertEquals(store.account, account)
    }

    @Test
    fun linkingSendsTheDeviceTokenAndKeepsTheLinkedUser() = runTest {
        store.account = signedIn
        server.enqueue(MockResponse().setBody(
            """{"user": {"username": "metchu_user", "google_email": "minji@example.com", "has_password": true}}"""
        ))
        repository.linkGoogle("google-id-token")

        val request = server.takeRequest()
        assertEquals("/api/auth/google/link/", request.path)
        assertEquals("Token device-token", request.getHeader("Authorization"))
        assertEquals(signedIn.copy(user = signedIn.user.copy(googleEmail = "minji@example.com")), store.account)
    }

    @Test
    fun logOutSendsTheTokenAndForgetsTheAccount() = runTest {
        store.account = signedIn
        server.enqueue(MockResponse().setResponseCode(204))
        repository.logOut()

        val request = server.takeRequest()
        assertEquals("POST" to "/api/auth/logout/", request.method to request.path)
        assertEquals("Token device-token", request.getHeader("Authorization"))
        assertNull(store.account)
    }

    @Test
    fun logOutForgetsTheAccountEvenWithoutTheServer() = runTest {
        store.account = signedIn
        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AT_START))
        try {
            repository.logOut()
            fail("expected IOException")
        } catch (e: IOException) {
            assertNull(store.account)
        }
    }

    @Test
    fun refreshSendsTheTokenAndKeepsTheServersAccount() = runTest {
        store.account = signedIn
        reply("auth_account")
        assertEquals(signedIn, repository.refresh())

        val request = server.takeRequest()
        assertEquals("GET" to "/api/auth/me/", request.method to request.path)
        assertEquals("Token device-token", request.getHeader("Authorization"))

        // Google was linked on another device in the meantime.
        server.enqueue(MockResponse().setBody(
            """{"user": {"username": "metchu_user", "google_email": "minji@example.com", "has_password": true}}"""
        ))
        val linked = signedIn.copy(user = signedIn.user.copy(googleEmail = "minji@example.com"))
        assertEquals(linked, repository.refresh())
        assertEquals(linked, store.account)
    }

    @Test
    fun refreshForgetsATokenTheServerRejects() = runTest {
        store.account = signedIn
        reply("error_not_authenticated", 401)
        assertNull(repository.refresh())
        assertNull(store.account)
    }

    @Test
    fun refreshKeepsTheAccountUnlessTheServerRejectsIt() = runTest {
        store.account = signedIn
        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AT_START))
        server.enqueue(MockResponse().setResponseCode(401).setBody("<html>Unauthorized</html>"))
        server.enqueue(MockResponse().setResponseCode(500))
        for (failure in listOf(IOException::class.java, HttpException::class.java, HttpException::class.java)) {
            try {
                repository.refresh()
                fail("expected ${failure.simpleName}")
            } catch (e: Exception) {
                assertTrue(failure.isInstance(e))
            }
            assertEquals(signedIn, store.account)
        }
    }

    @Test
    fun refreshAsksNothingForAGuest() = runTest {
        assertNull(repository.refresh())
        assertEquals(0, server.requestCount)
    }

    @Test
    fun anIncompleteReplyIsRejected() = runTest {
        server.enqueue(MockResponse().setResponseCode(201).setBody("""{"token": "t"}"""))
        try {
            repository.signUp("metchu_user", "bap-meokja-2026")
            fail("expected IllegalStateException")
        } catch (e: IllegalStateException) {
            assertTrue(e.message!!.contains("incomplete"))
        }
        assertNull(store.account)
    }

    @Test
    fun theCapturedRepliesDecode() {
        assertEquals(AccountUser("metchu_user", null, hasPassword = true), Fixtures.signedIn().user)
        assertTrue(Fixtures.signedIn().token.isNotEmpty())
        for ((name, code) in listOf(
            "error_username_taken" to "username_taken",
            "error_invalid_credentials" to "invalid_credentials",
            "error_google_unavailable" to "google_unavailable",
            "error_not_authenticated" to "not_authenticated"
        )) {
            assertEquals(code, Fixtures.error(name).error!!.code)
        }
    }
}
