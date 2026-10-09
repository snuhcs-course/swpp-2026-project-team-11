// AI-generated: written with Claude (Anthropic) and reviewed by the team.
package com.example.metchu.data.model

import com.google.gson.annotations.SerializedName

/**
 * Mirrors `RecommendSession.public_state()` in backend/recommend/sessions.py field
 * for field. Every endpoint returns this one shape, so the screen always redraws
 * from the server's current step rather than from what the phone thinks happened.
 *
 * Gson does not enforce Kotlin nullability: a renamed field arrives as null without
 * throwing. Fields that only some step types carry are declared nullable.
 */
data class SessionState(
    @SerializedName("session_id") val sessionId: String,
    val engine: String,
    val date: String,
    val meal: String?,
    @SerializedName("candidate_count") val candidateCount: Int,
    @SerializedName("max_questions") val maxQuestions: Int?,
    @SerializedName("can_undo") val canUndo: Boolean,
    val step: Step
)

/** The question engines the server can run a session with; see [SessionState.engine]. */
object Engine {
    /** P10: picks each question from the dishes' extracted features. Answers at once. */
    const val DECISION_TREE = "decision_tree"
    /** P13/P14: Gemini writes each question from the dish names. A step can take seconds. */
    const val LLM = "llm"
}

/** One engine step. [type] decides which of the optional fields are present. */
data class Step(
    val type: String,
    @SerializedName("question_count") val questionCount: Int,
    val text: String,
    // question
    @SerializedName("question_id") val questionId: String?,
    val options: List<AnswerOption>?,
    // guess and recommendation; only the decision tree sends a group
    @SerializedName("guess_id") val guessId: String?,
    @SerializedName("target_kind") val targetKind: String?,
    val food: Food?,
    val group: FoodGroup?,
    // unavailable
    val reason: String?
) {
    companion object {
        const val QUESTION = "question"
        const val GUESS = "guess"
        const val RECOMMENDATION = "recommendation"
        const val UNAVAILABLE = "unavailable"
    }
}

data class AnswerOption(val id: String, val label: String)

data class Food(
    @SerializedName("food_id") val foodId: Int,
    val name: String,
    @SerializedName("display_name") val displayName: String,
    @SerializedName("food_group") val foodGroup: String,
    val offers: List<Offer>
)

data class Offer(val restaurant: String, val meal: String, val price: Int?)

/** Present when a guess names a whole group; [Step.food] is then one example from it. */
data class FoodGroup(
    @SerializedName("group_id") val groupId: String,
    @SerializedName("display_name") val displayName: String,
    val members: List<GroupMember>
)

data class GroupMember(
    @SerializedName("food_id") val foodId: Int,
    @SerializedName("display_name") val displayName: String
)
