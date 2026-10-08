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
 * The default, http://10.0.2.2:8000/, is how the emulator reaches the host machine;
 * "127.0.0.1" would be the emulator itself.
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

    val api: ApiService by lazy { create(BuildConfig.BASE_URL) }

    /** [baseUrl] must end with a slash. Tests point this at a local fake server. */
    fun create(baseUrl: String): ApiService =
        Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create(gson))
            .build()
            .create(ApiService::class.java)
}
