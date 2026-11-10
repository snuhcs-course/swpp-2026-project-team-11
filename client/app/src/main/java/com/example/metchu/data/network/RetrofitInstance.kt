package com.example.metchu.data.network

import com.example.metchu.BuildConfig
import com.google.gson.Gson
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

/**
 * The server address comes from BuildConfig.BASE_URL (see app/build.gradle.kts).
 * The default is the team server; local.properties can point a developer build
 * at an emulator, a phone via adb reverse, or another development server.
 */
object RetrofitInstance {

    val gson = Gson()

    private val logging = HttpLoggingInterceptor().apply {
        level = if (BuildConfig.DEBUG) HttpLoggingInterceptor.Level.BODY
        else HttpLoggingInterceptor.Level.NONE
    }

    private val client = OkHttpClient.Builder()
        .addInterceptor(logging)
        .connectTimeout(5, TimeUnit.SECONDS)
        // An LLM engine step makes up to two Gemini calls of 10 s each before the
        // server falls back, so the reply can take just over 20 s.
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    // Sign-in requests carry passwords and tokens, so only their headers are logged, with the token hidden.
    private val authClient = OkHttpClient.Builder()
        .addInterceptor(HttpLoggingInterceptor().apply {
            level = if (BuildConfig.DEBUG) HttpLoggingInterceptor.Level.HEADERS
            else HttpLoggingInterceptor.Level.NONE
            redactHeader("Authorization")
        })
        .connectTimeout(5, TimeUnit.SECONDS)
        // Google sign-in waits while the server checks the token with Google.
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    val api: ApiService by lazy { create(BuildConfig.BASE_URL) }

    val authApi: AuthApi by lazy { createAuth(BuildConfig.BASE_URL) }

    /** [baseUrl] must end with a slash. Tests point this at a local fake server. */
    fun create(baseUrl: String): ApiService = retrofit(baseUrl, client).create(ApiService::class.java)

    fun createAuth(baseUrl: String): AuthApi = retrofit(baseUrl, authClient).create(AuthApi::class.java)

    private fun retrofit(baseUrl: String, client: OkHttpClient): Retrofit =
        Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create(gson))
            .build()
}
