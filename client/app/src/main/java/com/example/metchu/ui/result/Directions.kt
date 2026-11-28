package com.example.metchu.ui.result

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import java.net.URLEncoder

/**
 * Walking directions to [to], in the order tried: Naver Map, Kakao Map, then Kakao Map's
 * web page. No route API is called and only the destination is sent: the map app picks
 * the start itself, from where the phone is if the user lets it.
 */
fun directionsLinks(name: String, to: Point, appName: String): List<String> {
    val label = encode(name)
    return listOf(
        "nmap://route/walk?dlat=${to.lat}&dlng=${to.lng}&dname=$label&appname=$appName",
        "kakaomap://route?ep=${to.lat},${to.lng}&by=FOOT",
        "https://map.kakao.com/link/to/$label,${to.lat},${to.lng}"
    )
}

private fun encode(text: String) = URLEncoder.encode(text, "UTF-8").replace("+", "%20")

/** Opens the first of [directionsLinks] that an installed app handles. */
fun Context.openDirections(name: String, to: Point) {
    for (link in directionsLinks(name, to, packageName)) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(link)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            return
        } catch (_: ActivityNotFoundException) {
        }
    }
}
