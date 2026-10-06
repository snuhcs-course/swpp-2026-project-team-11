"""Validated adapter for menus.services output, independent of Django/ORM.

Food IDs are the identity boundary. Repeated display names may have different
features and offers; they are not silently merged. Family nodes are internal.
"""
from collections import defaultdict
import copy
from dataclasses import dataclass
import hashlib
import json
import math
from numbers import Real
from types import MappingProxyType

from .contracts import FEATURE_PRESENTATION


@dataclass(frozen=True)
class Candidate:
    food_id: int
    name: str
    display_name: str
    food_group: str
    features: object
    offers: tuple

    def summary(self):
        return {"food_id": self.food_id, "name": self.name,
                "display_name": self.display_name, "food_group": self.food_group,
                "offers": copy.deepcopy(list(self.offers))}


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    kind: str
    parent_id: str | None


class MenuTree:
    ROOT_ID = "root"

    def __init__(self, candidates):
        self.food_ids = tuple(f"food:{c.food_id}" for c in candidates)
        self.food_index = {food_id: i for i, food_id in enumerate(self.food_ids)}
        self.nodes = {"root": Node("root", "All available meals", "root", None)}
        self.descendants = {"root": tuple(range(len(candidates)))}
        grouped = defaultdict(list)
        for i, c in enumerate(candidates):
            if c.food_group:
                grouped[c.food_group].append(i)
        parents = {}
        for label, members in sorted(grouped.items()):
            if len(members) < 2:
                continue
            group_id = "group:" + hashlib.sha256(label.encode()).hexdigest()[:16]
            self.nodes[group_id] = Node(group_id, label, "family", "root")
            self.descendants[group_id] = tuple(members)
            for i in members:
                parents[i] = group_id
        for i, c in enumerate(candidates):
            food_id = self.food_ids[i]
            self.nodes[food_id] = Node(food_id, c.display_name, "food", parents.get(i, "root"))
            self.descendants[food_id] = (i,)
        self.proposal_ids = tuple(key for key in self.nodes if key != "root")

    def descendant_food_ids(self, node_id):
        return tuple(self.food_ids[i] for i in self.descendants[node_id])


class CandidateCatalog:
    def __init__(self, candidates, feature_schema, *, priors=None, context=None):
        schema = list(feature_schema)
        keys = [row.get("key") for row in schema]
        if not keys or any(not isinstance(key, str) or not key.strip() for key in keys) or len(set(keys)) != len(keys):
            raise ValueError("Feature schema requires distinct nonempty keys")
        self.feature_keys = tuple(keys)
        self.questions = []
        for row in schema:
            key = row["key"]
            default = FEATURE_PRESENTATION.get(key, (f"Do you feel like {key.replace('_', ' ')}?", key))
            text = row.get("question_en", default[0])
            family = row.get("family", default[1])
            if not isinstance(text, str) or not text.strip() or not isinstance(family, str) or not family.strip():
                raise ValueError("Question text and family must be nonempty strings")
            self.questions.append({"id": f"q:{key}", "attribute": key, "text": text, "family": family, "kind": "attribute"})
        rows = []
        for raw in candidates:
            food_id = raw.get("food_id")
            if type(food_id) is not int or food_id <= 0:
                raise ValueError("Each candidate needs a positive integer food_id")
            name = raw.get("name")
            label = raw.get("display_name") or name
            group = raw.get("food_group", "")
            if not isinstance(name, str) or not name.strip() or not isinstance(label, str) or not label.strip() or not isinstance(group, str):
                raise ValueError("Invalid candidate name or food_group")
            features = raw.get("features")
            if not isinstance(features, dict) or set(features) != set(keys):
                raise ValueError(f"Food {food_id} must have exactly the declared feature keys")
            values = {}
            for key, value in features.items():
                if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError(f"Food {food_id}: {key} must be a probability in [0,1]")
                values[key] = float(value)
            offers = raw.get("offers", [])
            if not isinstance(offers, list):
                raise ValueError("Candidate offers must be a list")
            for offer in offers:
                if not isinstance(offer, dict) or not isinstance(offer.get("restaurant"), str) or offer.get("meal") not in {"BR", "LU", "DN"}:
                    raise ValueError("Invalid cafeteria offer")
                price = offer.get("price")
                if price is not None and (type(price) is not int or price < 0):
                    raise ValueError("Offer price must be a nonnegative integer or null")
            rows.append(Candidate(food_id, name.strip(), label.strip(), group.strip(), MappingProxyType(values), tuple(copy.deepcopy(offers))))
        if len({c.food_id for c in rows}) != len(rows):
            raise ValueError("Duplicate food_id")
        self.candidates = tuple(sorted(rows, key=lambda c: c.food_id))
        self.by_id = {c.food_id: c for c in self.candidates}
        ids = set(self.by_id)
        if priors is not None:
            if not isinstance(priors, dict) or set(priors) != ids or any(type(key) is not int for key in priors):
                raise ValueError("Priors must cover exactly the integer candidate IDs")
            if any(isinstance(v, bool) or not isinstance(v, Real) or not math.isfinite(v) or v <= 0 for v in priors.values()):
                raise ValueError("Priors must be finite and positive")
            total = math.fsum(priors.values())
            if not math.isfinite(total):
                raise ValueError("Prior sum must be finite")
            probabilities = {key: float(value / total) for key, value in priors.items()}
        else:
            probabilities = {key: 1 / len(ids) for key in ids} if ids else {}
        self.context = copy.deepcopy(context or {})
        self.food_tree = MenuTree(self.candidates)
        self.foods = [{"id": f"food:{c.food_id}", "display_name": c.display_name,
                       "attributes": dict(c.features), "prior_probability": probabilities[c.food_id]}
                      for c in self.candidates]
        canonical = {"candidates": [c.summary() | {"features": dict(c.features), "prior": probabilities[c.food_id]} for c in self.candidates],
                     "questions": self.questions, "context": self.context}
        self.fingerprint = hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()

    def candidate_for_node(self, node_id):
        if not node_id.startswith("food:"):
            raise ValueError("Expected a concrete food node")
        return self.by_id[int(node_id.split(":", 1)[1])]
