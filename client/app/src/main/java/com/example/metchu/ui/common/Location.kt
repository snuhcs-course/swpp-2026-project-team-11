package com.example.metchu.ui.common

import android.Manifest
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import androidx.core.location.LocationManagerCompat
import androidx.core.os.CancellationSignal
import com.example.metchu.ui.result.Point

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

/** The last known position at once, then a fresh fix when the system has one. Null without permission. */
@SuppressLint("MissingPermission") // checked by hasLocationPermission()
@Composable
fun rememberUserPoint(granted: Boolean): Point? {
    val context = LocalContext.current
    return produceState<Point?>(null, granted) {
        if (!granted || !hasLocationPermission(context)) return@produceState
        val manager = context.getSystemService(LocationManager::class.java) ?: return@produceState
        val providers = manager.getProviders(true)
        value = providers.mapNotNull { manager.getLastKnownLocation(it) }.maxByOrNull { it.time }
            ?.let { Point(it.latitude, it.longitude) }
        val provider = providers.firstOrNull { it == LocationManager.FUSED_PROVIDER }
            ?: providers.firstOrNull { it == LocationManager.NETWORK_PROVIDER }
            ?: providers.firstOrNull() ?: return@produceState
        val signal: CancellationSignal? = null
        LocationManagerCompat.getCurrentLocation(manager, provider, signal, ContextCompat.getMainExecutor(context)) { fix: Location? ->
            if (fix != null) value = Point(fix.latitude, fix.longitude)
        }
    }.value
}

fun hasLocationPermission(context: Context): Boolean = LOCATION_PERMISSIONS.any {
    ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED
}
