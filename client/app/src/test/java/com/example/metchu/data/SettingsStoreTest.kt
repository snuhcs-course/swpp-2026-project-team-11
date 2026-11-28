package com.example.metchu.data

import com.example.metchu.data.model.Engine
import com.example.metchu.data.repository.Area
import com.example.metchu.data.repository.Price
import com.example.metchu.data.repository.ids
import com.example.metchu.data.repository.levels
import com.example.metchu.data.repository.storedAreas
import com.example.metchu.data.repository.storedPrices
import com.example.metchu.data.repository.usableEngine
import org.junit.Assert.assertEquals
import org.junit.Test

class SettingsStoreTest {
    @Test
    fun rlIsTheDefaultAndReplacesAStoredLlmChoice() {
        assertEquals(Engine.RL, usableEngine(null))
        assertEquals(Engine.RL, usableEngine(Engine.LLM))
        assertEquals(Engine.RL, usableEngine(Engine.RL))
        assertEquals(Engine.DECISION_TREE, usableEngine(Engine.DECISION_TREE))
    }

    @Test
    fun theFirstLaunchPicksEveryAreaAndEveryPrice() {
        assertEquals(Area.entries.toSet(), storedAreas(null, null))
        assertEquals(Price.entries.toSet(), storedPrices(null, null))
    }

    @Test
    fun anOlderSingleChoiceBecomesItsSet() {
        assertEquals(setOf(Area.SNU_STATION), storedAreas(null, "SNU_STATION"))
        assertEquals(Area.entries.toSet(), storedAreas(null, "ALL"))
        assertEquals(setOf(Price.MID), storedPrices(null, "MID"))
        assertEquals(Price.entries.toSet(), storedPrices(null, "ANY"))
    }

    @Test
    fun storedSetsWinOverTheOlderChoiceAndMayBeEmpty() {
        assertEquals(setOf(Area.CAMPUS, Area.NAKSEONGDAE), storedAreas("CAMPUS,NAKSEONGDAE", "SNU_STATION"))
        assertEquals(setOf(Price.LOW, Price.HIGH), storedPrices("LOW,HIGH,GONE", "MID"))
        assertEquals(emptySet<Area>(), storedAreas("", "ALL"))
        assertEquals(emptySet<Price>(), storedPrices("", null))
    }

    @Test
    fun picksGoToTheServerInItsOrder() {
        assertEquals(listOf("campus", "nakseongdae"), setOf(Area.NAKSEONGDAE, Area.CAMPUS).ids())
        assertEquals(listOf(1, 3), setOf(Price.HIGH, Price.LOW).levels())
    }
}
