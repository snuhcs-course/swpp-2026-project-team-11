package com.example.metchu.data.repository

import androidx.activity.result.ActivityResultRegistry
import com.example.metchu.data.location.LocationSource

/** Where the app gets its repository. UI tests replace it with one backed by a fake server. */
object AppContainer {
    var repository: RecommendRepository = RecommendRepository()

    /** Null: the device's own location. UI tests set a fixed one. */
    var locationSource: LocationSource? = null

    /** Null: the activity's own, which shows the permission dialog. UI tests answer it themselves. */
    var resultRegistry: ActivityResultRegistry? = null
}
