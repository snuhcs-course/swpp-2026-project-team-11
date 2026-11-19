package com.example.metchu.ui.result

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import com.example.metchu.R
import java.net.URLEncoder

/**
 * Walking directions to [to], in the order tried: Naver Map, Kakao Map, then Kakao Map's
 * web page. No route API is called; the map app finds the route from where the phone is.
 * Kakao Map and its web page are given the user's position [from], labelled [fromName],
 * when known: the app may not start without one, and the web page leaves the start empty.
 */
fun directionsLinks(name: String, to: Point, from: Point?, fromName: String, appName: String): List<String> {
    val label = encode(name)
    val web = if (from == null) "to/$label,${to.lat},${to.lng}"
    else "by/walk/${encode(fromName)},${from.lat},${from.lng}/$label,${to.lat},${to.lng}"
    val kakaoStart = from?.let { "sp=${it.lat},${it.lng}&" }.orEmpty()
    return listOf(
        "nmap://route/walk?dlat=${to.lat}&dlng=${to.lng}&dname=$label&appname=$appName",
        "kakaomap://route?${kakaoStart}ep=${to.lat},${to.lng}&by=FOOT",
        "https://map.kakao.com/link/$web"
    )
}

private fun encode(text: String) = URLEncoder.encode(text, "UTF-8").replace("+", "%20")

/** Opens the first of [directionsLinks] that an installed app handles. */
fun Context.openDirections(name: String, to: Point, from: Point?) {
    for (link in directionsLinks(name, to, from, getString(R.string.directions_from), packageName)) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(link)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            return
        } catch (_: ActivityNotFoundException) {
        }
    }
}
