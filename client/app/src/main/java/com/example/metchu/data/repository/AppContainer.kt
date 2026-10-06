package com.example.metchu.data.repository

/** Where the app gets its repository. UI tests replace it with one backed by a fake server. */
object AppContainer {
    var repository: RecommendRepository = RecommendRepository()
}
