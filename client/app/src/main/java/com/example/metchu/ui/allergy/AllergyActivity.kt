package com.example.metchu.ui.allergy

import android.os.Bundle
import android.view.LayoutInflater
import androidx.appcompat.app.AppCompatActivity
import com.example.metchu.data.model.Allergen
import com.example.metchu.data.repository.AllergyStore
import com.example.metchu.databinding.ActivityAllergyBinding
import com.example.metchu.databinding.ItemAllergenChipBinding
import com.example.metchu.util.padForSystemBars
import com.google.android.material.chip.Chip

/**
 * Picks the allergies to avoid, one chip per [Allergen]. Save stores them on this
 * device, also when none is picked, and returns to the start screen.
 */
class AllergyActivity : AppCompatActivity() {

    private lateinit var chips: Map<Allergen, Chip>

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val binding = ActivityAllergyBinding.inflate(layoutInflater)
        setContentView(binding.root)
        binding.root.padForSystemBars()

        val store = AllergyStore(this)
        // Picks not saved yet survive a rotation.
        val checked = savedInstanceState?.getStringArrayList(CHECKED)?.toSet()
            ?: store.allergies.map { it.id }.toSet()
        val inflater = LayoutInflater.from(this)
        chips = Allergen.entries.associateWith { allergen ->
            ItemAllergenChipBinding.inflate(inflater, binding.allergyChips, true).root.apply {
                setText(allergen.label)
                isChecked = allergen.id in checked
            }
        }
        binding.btnSaveAllergies.setOnClickListener {
            store.allergies = checkedAllergens()
            finish()
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putStringArrayList(CHECKED, ArrayList(checkedAllergens().map { it.id }))
    }

    private fun checkedAllergens(): List<Allergen> = chips.filterValues { it.isChecked }.keys.toList()

    private companion object {
        const val CHECKED = "checked"
    }
}
