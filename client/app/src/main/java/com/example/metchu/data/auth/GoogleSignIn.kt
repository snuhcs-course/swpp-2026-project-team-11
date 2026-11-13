package com.example.metchu.data.auth

import android.content.Context
import android.util.Log
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialCancellationException
import com.example.metchu.BuildConfig
import com.google.android.libraries.identity.googleid.GetSignInWithGoogleOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential

/** Asks Google for an ID token the server can check, or null if the user backed out. */
fun interface GoogleTokenSource {
    /** [context] must be an Activity's: Google shows its account picker over it. */
    suspend fun idToken(context: Context): String?
}

/**
 * "Sign in with Google" through Android's Credential Manager. The token is addressed to the
 * team's web OAuth client ([serverClientId]), which is what the server checks it against;
 * Google accepts the request only from an app whose package and signing certificate are
 * registered as an Android client in the same Google Cloud project (client/README.md).
 */
class CredentialManagerGoogle(private val serverClientId: String = BuildConfig.GOOGLE_WEB_CLIENT_ID) : GoogleTokenSource {
    override suspend fun idToken(context: Context): String? {
        val request = GetCredentialRequest.Builder()
            .addCredentialOption(GetSignInWithGoogleOption.Builder(serverClientId).build())
            .build()
        val credential = try {
            CredentialManager.create(context).getCredential(context, request).credential
        } catch (e: GetCredentialCancellationException) {
            // Also how Google reports an app it does not know (an unregistered SHA-1), so say so in the log.
            Log.i(TAG, "Google sign-in closed without a token: ${e.message}")
            return null
        }
        check(credential is CustomCredential && credential.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL) {
            "Unexpected credential type: ${credential.type}"
        }
        return GoogleIdTokenCredential.createFrom(credential.data).idToken
    }

    private companion object {
        const val TAG = "GoogleSignIn"
    }
}
