import math
import unittest

from ..catalog import CandidateCatalog


def sample():
    return [{"food_id": 10, "name": "Beef noodle meal", "display_name": "Noodles", "food_group": "Noodles", "features": {"soupy": .9}, "offers": [{"restaurant": "Hall", "meal": "LU", "price": 4000}]},
            {"food_id": 20, "name": "Chicken noodle meal", "display_name": "Noodles", "food_group": "Noodles", "features": {"soupy": .6}, "offers": []}]


class CatalogTests(unittest.TestCase):
    def test_duplicate_labels_are_distinct_foods(self):
        c = CandidateCatalog(sample(), [{"key": "soupy"}])
        self.assertEqual(tuple(c.by_id), (10, 20))
        self.assertEqual(len(c.food_tree.descendants["root"]), 2)
        self.assertEqual(sum(node.kind == "family" for node in c.food_tree.nodes.values()), 1)

    def test_input_and_summary_copies_protect_features_and_offers(self):
        raw = sample()
        c = CandidateCatalog(raw, [{"key": "soupy"}])
        raw[0]["features"]["soupy"] = .1
        raw[0]["offers"][0]["price"] = 1
        summary = c.by_id[10].summary()
        summary["offers"][0]["price"] = 2
        self.assertEqual(c.by_id[10].features["soupy"], .9)
        self.assertEqual(c.by_id[10].offers[0]["price"], 4000)

    def test_prior_and_scope_change_fingerprint(self):
        a = CandidateCatalog(sample(), [{"key": "soupy"}], priors={10: 3, 20: 1}, context={"meal": "LU"})
        b = CandidateCatalog(sample(), [{"key": "soupy"}], context={"meal": "DN"})
        self.assertNotEqual(a.fingerprint, b.fingerprint)
        self.assertEqual([f["prior_probability"] for f in a.foods], [.75, .25])

    def test_invalid_ids_vectors_and_probabilities(self):
        for change in (lambda x: x[0].update(food_id=True), lambda x: x[1].update(food_id=10),
                       lambda x: x[0]["features"].update(soupy=math.nan),
                       lambda x: x[0]["features"].update(soupy=True),
                       lambda x: x[0].update(features={})):
            raw = sample()
            change(raw)
            with self.assertRaises(ValueError):
                CandidateCatalog(raw, [{"key": "soupy"}])

    def test_priors_need_positive_full_coverage(self):
        for prior in ({10: 1}, {10: 0, 20: 1}, {10: math.inf, 20: 1}):
            with self.assertRaises(ValueError):
                CandidateCatalog(sample(), [{"key": "soupy"}], priors=prior)

    def test_custom_schema_and_empty_candidate_set(self):
        c = CandidateCatalog([], [{"key": "custom", "question_en": "Do you like this?"}])
        self.assertFalse(c.candidates)
        self.assertEqual(c.questions[0]["text"], "Do you like this?")

    def test_source_schema_semantics_change_fingerprint(self):
        a = CandidateCatalog(sample(), [{"key": "soupy", "question": "Want broth?"}])
        b = CandidateCatalog(sample(), [{"key": "soupy", "question": "Want thick broth?"}])
        self.assertNotEqual(a.fingerprint, b.fingerprint)

    def test_malformed_rows_context_and_offers_are_rejected(self):
        for rows, schema, context in (([None], [{"key": "soupy"}], None),
                                      (sample(), [None], None),
                                      (sample(), [{"key": "soupy"}], [])):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                CandidateCatalog(rows, schema, context=context)
        raw = sample()
        raw[0]["offers"][0]["restaurant"] = " "
        with self.assertRaises(ValueError):
            CandidateCatalog(raw, [{"key": "soupy"}])
