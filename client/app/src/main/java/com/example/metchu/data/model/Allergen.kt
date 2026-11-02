package com.example.metchu.data.model

import androidx.annotation.StringRes
import com.example.metchu.R

/**
 * The 19 allergens Korean food labels must declare. [id] is a key of ALLERGEN_KEYS
 * in backend/menus/allergens.py, which POST /api/sessions/ accepts as "allergies";
 * the two lists must stay the same.
 */
enum class Allergen(val id: String, @StringRes val label: Int) {
    EGG("egg", R.string.allergen_egg),
    MILK("milk", R.string.allergen_milk),
    BUCKWHEAT("buckwheat", R.string.allergen_buckwheat),
    PEANUT("peanut", R.string.allergen_peanut),
    SOYBEAN("soybean", R.string.allergen_soybean),
    WHEAT("wheat", R.string.allergen_wheat),
    MACKEREL("mackerel", R.string.allergen_mackerel),
    CRAB("crab", R.string.allergen_crab),
    SHRIMP("shrimp", R.string.allergen_shrimp),
    PORK("pork", R.string.allergen_pork),
    PEACH("peach", R.string.allergen_peach),
    TOMATO("tomato", R.string.allergen_tomato),
    SULFITE("sulfite", R.string.allergen_sulfite),
    WALNUT("walnut", R.string.allergen_walnut),
    CHICKEN("chicken", R.string.allergen_chicken),
    BEEF("beef", R.string.allergen_beef),
    SQUID("squid", R.string.allergen_squid),
    SHELLFISH("shellfish", R.string.allergen_shellfish),
    PINE_NUT("pine_nut", R.string.allergen_pine_nut)
}
