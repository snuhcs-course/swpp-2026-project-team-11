package com.example.metchu.ui.result

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import java.net.URLEncoder

/**
 * Walking directions to [to], in the order tried: Naver Map, Kakao Map, then Kakao Map's
 * web page. No route API is called; the map app finds the route from where the phone is.
 * Kakao Map is given the user's position [from] when known, as it may not start without one.
 */
fun directionsLinks(name: String, to: Point, from: Point?, appName: String): List<String> {
    val label = URLEncoder.encode(name, "UTF-8").replace("+", "%20")
    val kakaoStart = from?.let { "sp=${it.lat},${it.lng}&" }.orEmpty()
    return listOf(
        "nmap://route/walk?dlat=${to.lat}&dlng=${to.lng}&dname=$label&appname=$appName",
        "kakaomap://route?${kakaoStart}ep=${to.lat},${to.lng}&by=FOOT",
        "https://map.kakao.com/link/to/$label,${to.lat},${to.lng}"
    )
}

/** Opens the first of [directionsLinks] that an installed app handles. */
fun Context.openDirections(name: String, to: Point, from: Point?) {
    for (link in directionsLinks(name, to, from, packageName)) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(link)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            return
        } catch (_: ActivityNotFoundException) {
        }
    }
}
