package com.example.metchu.ui.common

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Looper
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import androidx.core.app.ActivityCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import com.example.metchu.data.location.LOCATION_PERMISSIONS
import com.example.metchu.data.location.hasLocationPermission
import com.example.metchu.data.repository.SettingsStore
import com.example.metchu.ui.result.Point
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import kotlin.math.abs

/** How a request for location ended: [BLOCKED] when Android will not show its dialog again, so only the app's settings page can allow it. */
enum class LocationAnswer { GRANTED, DENIED, BLOCKED }

/**
 * After the system's answer: Android shows its dialog again only while it would show a rationale
 * ([rationaleAfter]). Without one, the dialog was either closed unanswered (Back or a tap outside a
 * first dialog leaves no trace) or never shown because the user blocked it. The app cannot tell these
 * apart (it is paused and gets the same result either way), so no rationale counts as blocked only
 * after an earlier refusal: a rationale before this request, or the last request [refusedBefore].
 */
fun locationAnswer(granted: Boolean, rationaleBefore: Boolean, rationaleAfter: Boolean, refusedBefore: Boolean): LocationAnswer = when {
    granted -> LocationAnswer.GRANTED
    rationaleAfter || !(rationaleBefore || refusedBefore) -> LocationAnswer.DENIED
    else -> LocationAnswer.BLOCKED
}

/** Whether the user allows location, and how to ask. Declining keeps the app working without distances. */
class LocationPermission(val granted: Boolean, val request: () -> Unit)

/**
 * Checked again whenever the app comes back, for location allowed on the app's settings page meanwhile.
 * Every answer goes to [onAnswer], the one of the latest composition, so a screen recreated while
 * Android's dialog is open still gets it.
 */
@Composable
fun rememberLocationPermission(onAnswer: (LocationAnswer) -> Unit = {}): LocationPermission {
    val context = LocalContext.current
    val settings = remember { SettingsStore(context) }
    var granted by remember { mutableStateOf(context.hasLocationPermission()) }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { granted = context.hasLocationPermission() }
    val answer by rememberUpdatedState(onAnswer)
    var rationaleBefore by rememberSaveable { mutableStateOf(false) }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        granted = context.hasLocationPermission()
        val result = locationAnswer(granted, rationaleBefore, context.canAskForLocation(), settings.locationRefused)
        settings.locationRefused = !granted
        answer(result)
    }
    return LocationPermission(granted) {
        rationaleBefore = context.canAskForLocation()
        launcher.launch(LOCATION_PERMISSIONS)
    }
}

private fun Context.canAskForLocation(): Boolean {
    var context = this
    while (context !is Activity && context is ContextWrapper) context = context.baseContext
    val activity = context as? Activity ?: return false
    return LOCATION_PERMISSIONS.any { ActivityCompat.shouldShowRequestPermissionRationale(activity, it) }
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
        if (!granted || !context.hasLocationPermission()) return@DisposableEffect onDispose {}
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

/**
 * Which way the phone points, in degrees clockwise from north, while [enabled]; null when it
 * is off or the phone has no rotation sensor. Small wobbles under 2 degrees are ignored.
 */
@Composable
fun rememberHeading(enabled: Boolean): Float? {
    val context = LocalContext.current
    var heading by remember { mutableStateOf<Float?>(null) }
    DisposableEffect(enabled) {
        val sensors = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        val sensor = sensors.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)
        if (!enabled || sensor == null) {
            heading = null
            return@DisposableEffect onDispose {}
        }
        val matrix = FloatArray(9)
        val angles = FloatArray(3)
        val listener = object : SensorEventListener {
            override fun onSensorChanged(event: SensorEvent) {
                SensorManager.getRotationMatrixFromVector(matrix, event.values)
                SensorManager.getOrientation(matrix, angles)
                val degrees = (Math.toDegrees(angles[0].toDouble()).toFloat() + 360f) % 360f
                val last = heading
                if (last == null || abs(((degrees - last + 540f) % 360f) - 180f) > 2f) heading = degrees
            }
            override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit
        }
        sensors.registerListener(listener, sensor, SensorManager.SENSOR_DELAY_UI)
        onDispose { sensors.unregisterListener(listener) }
    }
    return heading
}
