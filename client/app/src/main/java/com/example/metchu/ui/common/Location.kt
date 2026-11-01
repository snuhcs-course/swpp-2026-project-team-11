package com.example.metchu.ui.common

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.os.Looper
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import com.example.metchu.ui.result.Point
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority

private val LOCATION_PERMISSIONS = arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION)

/** Whether the user allows location, and how to ask. Declining keeps the app working without distances. */
class LocationPermission(val granted: Boolean, val request: () -> Unit)

@Composable
fun rememberLocationPermission(): LocationPermission {
    val context = LocalContext.current
    var granted by remember { mutableStateOf(hasLocationPermission(context)) }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        granted = hasLocationPermission(context)
    }
    return LocationPermission(granted) { launcher.launch(LOCATION_PERMISSIONS) }
}

/**
 * The user's position from Google's fused location provider, kept up to date while the
 * screen is shown: the last known fix at once, then every new one. A phone (or an
 * emulator) often has no last fix until some app listens, so a single read is not enough.
 * Null without permission or before the first fix.
 */
@SuppressLint("MissingPermission") // checked by hasLocationPermission()
@Composable
fun rememberUserPoint(granted: Boolean): Point? {
    val context = LocalContext.current
    var point by remember { mutableStateOf<Point?>(null) }
    DisposableEffect(granted) {
        if (!granted || !hasLocationPermission(context)) return@DisposableEffect onDispose {}
        val client = LocationServices.getFusedLocationProviderClient(context)
        client.lastLocation.addOnSuccessListener { fix -> if (fix != null && point == null) point = Point(fix.latitude, fix.longitude) }
        val callback = object : LocationCallback() {
            override fun onLocationResult(result: LocationResult) {
                result.lastLocation?.let { point = Point(it.latitude, it.longitude) }
            }
        }
        val request = LocationRequest.Builder(Priority.PRIORITY_BALANCED_POWER_ACCURACY, UPDATE_MILLIS).build()
        client.requestLocationUpdates(request, callback, Looper.getMainLooper())
        onDispose { client.removeLocationUpdates(callback) }
    }
    return point
}

private const val UPDATE_MILLIS = 10_000L

fun hasLocationPermission(context: Context): Boolean = LOCATION_PERMISSIONS.any {
    ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED
}
