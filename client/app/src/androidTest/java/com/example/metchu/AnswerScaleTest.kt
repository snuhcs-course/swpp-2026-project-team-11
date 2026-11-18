package com.example.metchu

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performTouchInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.example.metchu.data.model.AnswerId
import com.example.metchu.ui.question.AnswerScale
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** A group round can end while a finger is on the scale; letting go then must not answer the next question. */
@RunWith(AndroidJUnit4::class)
class AnswerScaleTest {
    @get:Rule
    val compose = createComposeRule()

    private var question by mutableStateOf("q:spicy")
    private val picks = mutableListOf<String>()

    private fun show() = compose.setContent {
        AnswerScale(question, OFFERED, loading = false, onPick = { picks += it }, onPress = {})
    }

    @Test
    fun aSliderHeldIntoTheNextQuestionAnswersNothing() {
        show()
        compose.onNodeWithTag("answer_${AnswerId.YES}").performTouchInput { down(center) }
        compose.runOnIdle { question = "q:soupy" }
        compose.onNodeWithTag("answer_${AnswerId.YES}").performTouchInput { up() }
        compose.waitForIdle()
        assertEquals(emptyList<String>(), picks)

        // The next press answers as usual.
        compose.onNodeWithTag("answer_${AnswerId.NO}").performTouchInput { down(center); up() }
        compose.runOnIdle { assertEquals(listOf(AnswerId.NO), picks) }
    }

    @Test
    fun notSureHeldIntoTheNextQuestionAnswersNothing() {
        show()
        compose.onNodeWithTag("answer_${AnswerId.UNKNOWN}").performTouchInput { down(center) }
        compose.runOnIdle { question = "q:soupy" }
        compose.onNodeWithTag("answer_${AnswerId.UNKNOWN}").performTouchInput { up() }
        compose.runOnIdle { assertEquals(emptyList<String>(), picks) }
    }

    private companion object {
        val OFFERED = setOf(AnswerId.YES, AnswerId.PROBABLY_YES, AnswerId.ANY, AnswerId.PROBABLY_NO, AnswerId.NO, AnswerId.UNKNOWN)
    }
}
