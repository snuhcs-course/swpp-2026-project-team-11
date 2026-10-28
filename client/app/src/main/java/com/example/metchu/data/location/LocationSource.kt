package com.example.metchu.data.location

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import com.example.metchu.data.network.UserLocation
import com.google.android.gms.location.LocationServices
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

val LOCATION_PERMISSIONS = arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION)

fun Context.hasLocationPermission(): Boolean = LOCATION_PERMISSIONS.any {
    ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
}

/** Where the user is when a session starts, or null when that is not known or not allowed. */
fun interface LocationSource {
    suspend fun current(): UserLocation?
}

/** The last location Google Play services has; null without permission or a recent fix. */
class FusedLocationSource(private val context: Context) : LocationSource {
    @SuppressLint("MissingPermission") // checked by hasLocationPermission()
    override suspend fun current(): UserLocation? {
        if (!context.hasLocationPermission()) return null
        return suspendCancellableCoroutine { continuation ->
            LocationServices.getFusedLocationProviderClient(context).lastLocation
                .addOnSuccessListener { location ->
                    continuation.resume(location?.let { UserLocation(it.latitude, it.longitude) })
                }
                .addOnFailureListener { continuation.resume(null) }
        }
    }
}
