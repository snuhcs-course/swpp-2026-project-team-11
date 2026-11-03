package com.example.metchu.data

import com.example.metchu.data.model.Engine
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
}
