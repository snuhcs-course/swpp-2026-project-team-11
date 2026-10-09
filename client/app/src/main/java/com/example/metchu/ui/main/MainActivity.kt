// AI-generated: written with Claude (Anthropic) and reviewed by the team.
package com.example.metchu.ui.main

import android.os.Bundle
import android.view.HapticFeedbackConstants
import android.view.LayoutInflater
import android.view.View
import androidx.activity.viewModels
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.isVisible
import com.example.metchu.R
import com.example.metchu.data.model.Engine
import com.example.metchu.data.model.Food
import com.example.metchu.data.model.SessionState
import com.example.metchu.data.model.Step
import com.example.metchu.data.repository.AppContainer
import com.example.metchu.databinding.ActivityMainBinding
import com.example.metchu.databinding.ItemAnswerBinding
import com.example.metchu.util.padForSystemBars
import java.text.NumberFormat
import java.util.Locale

/**
 * One screen that redraws from the engine's current step:
 *
 *   no session -> start        question -> answer buttons
 *   guess      -> yes / no     recommendation, unavailable -> start over
 *
 * Question text, answer labels and guess text come from the server as they are.
 * The start screen picks which question engine runs the session, so the two can be
 * compared; the screens are the same for both.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding

    /** The button whose request is running, if any. */
    private var tapped: View? = null

    private val viewModel: RecommendViewModel by viewModels {
        RecommendViewModelFactory(AppContainer.repository)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        binding.root.padForSystemBars()

        binding.btnStart.onTap { viewModel.start(selectedMeal(), selectedEngine()) }
        binding.btnAccept.onTap { viewModel.feedback(accepted = true) }
        binding.btnReject.onTap { viewModel.feedback(accepted = false) }
        binding.btnUndo.onTap { viewModel.undo() }
        binding.btnRecommendNow.onTap { viewModel.recommendNow() }
        binding.btnStartOver.onTap { viewModel.startOver() }
        binding.btnQuit.onTap { viewModel.startOver() }
        binding.btnRetry.onTap { viewModel.retry() }
        binding.engineToggle.addOnButtonCheckedListener { _, checkedId, isChecked ->
            if (isChecked) binding.tvEngineHint.setText(
                if (checkedId == R.id.btnEngineLlm) R.string.engine_llm_hint
                else R.string.engine_decision_tree_hint
            )
        }

        viewModel.session.observe(this) { render(it) }

        viewModel.loading.observe(this) { loading ->
            binding.progressLoading.visibility = if (loading) View.VISIBLE else View.INVISIBLE
            // The tapped button stays highlighted and pressed in for as long as its
            // request runs; everything else is disabled and fades.
            tapped?.isSelected = loading
            if (!loading) tapped = null
            setEnabledRecursively(binding.content, !loading)
            setEnabledRecursively(binding.bottomBar, !loading)
            if (!loading) viewModel.session.value?.let { binding.btnUndo.isEnabled = it.canUndo }
        }

        // An error stays on screen until the next request; a Toast would vanish
        // before anyone has read why the server could not be reached.
        viewModel.error.observe(this) { error ->
            binding.errorBanner.isVisible = error != null
            if (error != null) {
                binding.tvError.setText(error.message)
                binding.btnRetry.isVisible = error.canRetry
            }
        }
    }

    /** A click that also gives a light haptic tick and remembers which button it was. */
    private fun View.onTap(action: () -> Unit) = setOnClickListener { view ->
        tapped = view
        view.performHapticFeedback(HapticFeedbackConstants.CONTEXT_CLICK)
        action()
    }

    private fun selectedMeal(): String? = when (binding.mealToggle.checkedButtonId) {
        R.id.btnMealBreakfast -> "BR"
        R.id.btnMealLunch -> "LU"
        R.id.btnMealDinner -> "DN"
        else -> null
    }

    private fun selectedEngine(): String =
        if (binding.engineToggle.checkedButtonId == R.id.btnEngineLlm) Engine.LLM
        else Engine.DECISION_TREE

    private fun render(session: SessionState?) {
        val type = session?.step?.type
        binding.panelStart.isVisible = session == null
        binding.panelQuestion.isVisible = type == Step.QUESTION
        binding.panelGuess.isVisible = type == Step.GUESS
        binding.panelResult.isVisible = type == Step.RECOMMENDATION
        binding.panelUnavailable.isVisible = type == Step.UNAVAILABLE
        binding.bottomBar.isVisible = type == Step.QUESTION || type == Step.GUESS
        binding.btnQuit.isVisible = session != null
        binding.btnStartOver.isVisible = type == Step.RECOMMENDATION || type == Step.UNAVAILABLE
        binding.tvContext.isVisible = session != null
        if (session == null) return

        binding.tvContext.text = getString(
            R.string.session_context, session.date, mealLabel(session.meal),
            resources.getQuantityString(R.plurals.dishes, session.candidateCount, session.candidateCount),
            // The server says which engine it ran, which is not always the one asked for.
            getString(if (session.engine == Engine.LLM) R.string.engine_llm else R.string.engine_decision_tree)
        )
        binding.btnUndo.isEnabled = session.canUndo
        // A guess is already a proposal, so "recommend now" has nothing to add there.
        binding.btnRecommendNow.isVisible = type == Step.QUESTION
        binding.scroll.scrollTo(0, 0)

        val step = session.step
        when (type) {
            Step.QUESTION -> renderQuestion(session, step)
            Step.GUESS -> renderGuess(step)
            Step.RECOMMENDATION -> renderResult(step)
            Step.UNAVAILABLE -> binding.tvUnavailable.text =
                if (step.reason == "empty_candidates") {
                    getString(R.string.unavailable_no_menu, session.date, mealLabel(session.meal))
                } else {
                    getString(R.string.unavailable_exhausted)
                }
        }
    }

    private fun renderQuestion(session: SessionState, step: Step) {
        val number = step.questionCount + 1
        val max = session.maxQuestions
        binding.tvProgress.text =
            if (max != null) getString(R.string.question_progress_capped, number, max)
            else getString(R.string.question_progress, number)
        binding.progressQuestions.isVisible = max != null
        if (max != null) {
            binding.progressQuestions.max = max
            binding.progressQuestions.setProgressCompat(step.questionCount, true)
        }
        binding.tvQuestion.text = step.text

        // The server decides which answers exist; draw exactly those.
        binding.answers.removeAllViews()
        val inflater = LayoutInflater.from(this)
        step.options.orEmpty().forEach { option ->
            val button = ItemAnswerBinding.inflate(inflater, binding.answers, true).root
            button.text = option.label
            button.onTap { viewModel.answer(option.id) }
        }
    }

    private fun renderGuess(step: Step) {
        val food = step.food ?: return
        val group = step.group
        binding.tvGuessPrompt.text = step.text
        binding.tvGuessKind.setText(
            if (group != null) R.string.guess_kind_group else R.string.guess_kind_food
        )
        binding.tvGuessName.text = group?.displayName ?: food.displayName

        // A group guess names the category; the food is one real dish from it.
        binding.tvGuessExampleLabel.isVisible = group != null
        binding.tvGuessExample.isVisible = group != null
        binding.tvGuessExample.text = food.displayName
        binding.tvGuessOffers.text = offersText(food)

        val others = group?.members.orEmpty().filter { it.foodId != food.foodId }
        binding.tvGuessMembers.isVisible = others.isNotEmpty()
        if (others.isNotEmpty()) {
            val shown = others.take(MEMBER_PREVIEW).joinToString(", ") { it.displayName }
            val rest = others.size - MEMBER_PREVIEW
            binding.tvGuessMembers.text =
                if (rest > 0) getString(R.string.guess_members_more, shown, rest)
                else getString(R.string.guess_members, shown)
        }
        binding.btnAccept.setText(
            if (group != null) R.string.accept_group else R.string.accept_food
        )
    }

    private fun renderResult(step: Step) {
        val food = step.food ?: return
        binding.tvResultPrompt.text = step.text
        binding.tvResultName.text = food.displayName
        // `name` is the full menu line (for example with side dishes); show it when it adds detail.
        binding.tvResultFullName.isVisible = food.name != food.displayName
        binding.tvResultFullName.text = food.name
        binding.tvResultOffers.text = offersText(food)
    }

    private fun offersText(food: Food): String =
        if (food.offers.isEmpty()) getString(R.string.offer_none)
        else food.offers.joinToString("\n") { offer ->
            val price = offer.price?.let {
                getString(R.string.price_won, NumberFormat.getIntegerInstance(Locale.US).format(it))
            } ?: getString(R.string.price_unknown)
            getString(R.string.offer_line, offer.restaurant, mealLabel(offer.meal), price)
        }

    private fun mealLabel(meal: String?): String = getString(
        when (meal) {
            "BR" -> R.string.meal_breakfast
            "LU" -> R.string.meal_lunch
            "DN" -> R.string.meal_dinner
            else -> R.string.meal_any
        }
    )

    private fun setEnabledRecursively(view: View, enabled: Boolean) {
        view.isEnabled = enabled
        if (view is android.view.ViewGroup) {
            for (i in 0 until view.childCount) setEnabledRecursively(view.getChildAt(i), enabled)
        }
    }

    private companion object {
        const val MEMBER_PREVIEW = 5
    }
}
