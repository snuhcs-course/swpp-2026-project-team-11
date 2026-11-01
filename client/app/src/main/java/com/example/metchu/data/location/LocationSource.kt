package com.example.metchu.data.location

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import com.example.metchu.data.network.UserLocation
import com.google.android.gms.location.CurrentLocationRequest
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.tasks.Task
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

/**
 * A current fix from Google Play services, or its last known location when none comes
 * within [FIX_TIMEOUT_MS]; null without permission or either. A last known location
 * alone is often missing right after the permission is granted.
 */
class FusedLocationSource(private val context: Context) : LocationSource {
    @SuppressLint("MissingPermission") // checked by hasLocationPermission()
    override suspend fun current(): UserLocation? {
        if (!context.hasLocationPermission()) return null
        val client = LocationServices.getFusedLocationProviderClient(context)
        val request = CurrentLocationRequest.Builder()
            .setPriority(Priority.PRIORITY_BALANCED_POWER_ACCURACY)
            .setDurationMillis(FIX_TIMEOUT_MS)
            .build()
        val location = client.getCurrentLocation(request, null).awaitOrNull() ?: client.lastLocation.awaitOrNull()
        return location?.let { UserLocation(it.latitude, it.longitude) }
    }
}

/** Long enough for a network fix, short enough that Start does not feel stuck. */
private const val FIX_TIMEOUT_MS = 3_000L

private suspend fun <T> Task<T>.awaitOrNull(): T? = suspendCancellableCoroutine { continuation ->
    addOnSuccessListener { continuation.resume(it) }
    addOnFailureListener { continuation.resume(null) }
}
