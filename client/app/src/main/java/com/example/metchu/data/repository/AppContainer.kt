package com.example.metchu.data.repository

import com.example.metchu.data.auth.CredentialManagerGoogle
import com.example.metchu.data.auth.GoogleTokenSource
import com.example.metchu.data.location.LocationSource

/** Where the app gets its repository. UI tests replace it with one backed by a fake server. */
object AppContainer {
    var repository: RecommendRepository = RecommendRepository()

    var rooms: RoomRepository = RoomRepository()

    /** Null: the device's own location. UI tests set a fixed one. */
    var locationSource: LocationSource? = null

    /** Null: the account kept on the device, with the team server. UI tests set one backed by a fake. */
    var authRepository: AuthRepository? = null

    var google: GoogleTokenSource = CredentialManagerGoogle()
}
