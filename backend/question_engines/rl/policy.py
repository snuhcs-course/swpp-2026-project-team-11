"""Frozen v20 inference over any v2 candidate set. Only numeric features reach the policy."""
import hashlib
import json
import threading
import weakref
from numbers import Real
from operator import itemgetter
from pathlib import Path

import numpy as np


_export = json.loads(Path(__file__).with_name("weights.json").read_text())
MODEL_VERSION = _export["version"]
CHECKPOINT_SHA256 = _export["source_sha256"]
FEATURE_KEYS = tuple(_export["keys"])
_keys = frozenset(FEATURE_KEYS)
_ordered_values = itemgetter(*FEATURE_KEYS)
_parameters = {key: np.array(value, dtype=np.float32) for key, value in _export["parameters"].items()}
_catalogs = weakref.WeakValueDictionary()
_lock = threading.Lock()


def _weighted_sum(weights, matrix):
    # Small reductions on a web request do not need a multithreaded BLAS pool.
    return np.einsum("i,ij->j", weights, matrix)


def _feature_row(mapping, default):
    if not isinstance(mapping, dict) or mapping.keys() - _keys:
        raise ValueError("Expected keyed v2 feature values")
    types = set(map(type, mapping.values()))
    if not types <= {float, int, type(None)} and any(
        v is not None and (isinstance(v, bool) or not isinstance(v, Real)) for v in mapping.values()
    ):
        raise ValueError("Feature values must be numeric")
    if len(mapping) == len(FEATURE_KEYS) and type(None) not in types:
        return _ordered_values(mapping), None
    values = tuple(mapping.get(key) for key in FEATURE_KEYS)
    return tuple(default if v is None else v for v in values), tuple(v is not None for v in values)


def _matrix(rows, maximum, label):
    # Validate in double precision before converting to the checkpoint dtype.
    values = np.asarray(rows, dtype=np.float64)
    if not np.isfinite(values).all() or values.min() < 0 or values.max() > maximum:
        raise ValueError(f"Invalid {label}; expected finite values in [0, {maximum}]")
    return values.astype(np.float32)


def prepare(rows):
    """Share prepared numeric data across concurrent sessions, regardless of display metadata."""
    if not rows:
        raise ValueError("An empty catalog has no policy action")
    shape = (len(rows), len(FEATURE_KEYS))
    mean_rows, std_rows = [], []
    default_std = (.14,) * len(FEATURE_KEYS)
    known = np.zeros(shape, dtype=bool)
    for i, row in enumerate(rows):
        values, mask = _feature_row(row.get("features"), .5)
        mean_rows.append(values)
        if mask is not None:
            known[i] = mask
        else:
            known[i] = True
        std = row.get("feature_std")
        if std is None:
            std_rows.append(default_std)
        else:
            std_rows.append(_feature_row(std, .14)[0])
    means = _matrix(mean_rows, 1, "mean")
    deviations = _matrix(std_rows, .5, "deviation")
    digest = hashlib.sha256()
    for array in (means, deviations, known):
        digest.update(memoryview(array).cast("B"))
    key = digest.digest()
    with _lock:
        catalog = _catalogs.get(key)
        if catalog is None:
            catalog = PreparedCatalog(means, deviations, known)
            catalog.numeric_fingerprint = key.hex()
            _catalogs[key] = catalog
        return catalog


def _channel(values):
    a, b, c, d, e, f = (_parameters["channel.common"] + _parameters["channel.adjust"]).T
    mild = np.logaddexp(0, b) + .15
    strong = mild + np.logaddexp(0, a)
    z = 2 * values - 1
    logits = np.stack((c + strong*z, d + mild*z, e - mild*z, f - strong*z), axis=-1)
    direction = np.exp(logits - logits.max(axis=-1, keepdims=True))
    direction /= direction.sum(axis=-1, keepdims=True)
    neutral = _parameters["channel.neutral"]
    direction *= 1 - neutral.sum(axis=-1, keepdims=True)
    response = np.empty((*values.shape, 6), dtype=np.float32)
    response[..., [0, 1, 3, 4]] = direction
    response[..., [2, 5]] = neutral
    return response


class PreparedCatalog:
    """Linear catalogue storage. Session-specific answer and refusal state lives in the caller."""
    def __init__(self, means, deviations, known):
        size, features = means.shape
        average = _parameters["average"]
        strength = known * np.maximum(1 - 4 * deviations**2, 0)
        filled = np.where(known, means, average)
        observed = strength * (filled - average)
        self.prior = np.clip(np.einsum("ij,j->i", observed, _parameters["prior_coef"]), -1.2, 1.2)
        self.signature = observed / np.maximum(np.linalg.norm(observed, axis=1, keepdims=True), 1e-12)
        self.prob = np.empty((size, features, 6), dtype=np.float32)
        self.logratio = np.empty((features, 6, size), dtype=np.float32)
        self.entropy = np.empty((size, features), dtype=np.float32)
        sums = np.zeros((features, 6), dtype=np.float64)
        # Limit scratch space when binding a large, previously unseen menu.
        for i in range(0, size, 256):
            block = slice(i, i+256)
            raw = _channel(filled[block])
            self.prob[block] = raw
            sums += (raw * known[block, :, None]).sum(axis=0, dtype=np.float64)
        counts = known.sum(axis=0)[:, None]
        marginal = np.where(counts > 0, sums / np.maximum(counts, 1), _channel(average)).astype(np.float32)
        for i in range(0, size, 256):
            block = slice(i, i+256)
            prob = self.prob[block]
            prob[:] = np.maximum(marginal + strength[block, :, None] * (prob - marginal), 1e-7)
            prob /= prob.sum(axis=2, keepdims=True)
            self.logratio[:, :, block] = np.clip(np.log(prob / np.maximum(marginal, 1e-7)), -4, 4).transpose(1, 2, 0)
            self.entropy[block] = -(prob * np.log(prob)).sum(axis=2)
        self.logratio[:, [2, 5], :] = 0
        self.squares = np.square(self.prob).reshape(size, -1)
        self.prob = self.prob.reshape(size, -1)
        for array in vars(self).values():
            array.flags.writeable = False

    def refusal_row(self, index):
        """The exact v20 cosine-to-the-fourth contribution for one refused item."""
        similarity = np.einsum("ij,j->i", self.signature, self.signature[index])
        np.clip(similarity, 0, 1, out=similarity)
        np.square(similarity, out=similarity)
        return np.square(similarity, out=similarity)

    def decide(self, answers, rejected, *, available=None, refusal_sum=None):
        """Return (question index or -1, food index, normalized model scores)."""
        answers = np.asarray(answers)
        rejected = np.asarray(rejected, dtype=bool)
        if rejected.all():
            raise ValueError("All candidates have been rejected")
        temp, focus, log_cost, power, refusal = _parameters["actor"]
        logits = self.prior.copy()
        evidence = np.zeros_like(logits)
        for q in np.flatnonzero((answers >= 0) & (answers != 2) & (answers != 5)):
            evidence += self.logratio[q, answers[q]]
        logits += temp * evidence
        if rejected.any():
            if refusal_sum is None:
                refusal_sum = np.zeros_like(logits)
                for m in np.flatnonzero(rejected):
                    refusal_sum += self.refusal_row(m)
            logits -= refusal * np.minimum(refusal_sum, 3)
        logits[rejected] = -np.inf
        weights = np.exp(logits - logits.max())
        weights /= weights.sum()
        menu = int(weights.argmax())
        best = weights[menu]
        resp = _weighted_sum(weights, self.prob).reshape(-1, 6)
        information = np.maximum(-(resp * np.log(resp)).sum(axis=1) - _weighted_sum(weights, self.entropy), 0)
        squared = np.square(weights)
        concentration = (_weighted_sum(squared, self.squares).reshape(-1, 6) / np.maximum(resp, 1e-9)).sum(axis=1)
        gain = information + focus * (np.log(np.maximum(concentration / squared.sum(), 1)) - information)
        gain[answers >= 0] = -np.inf
        if available is not None:
            gain[~np.asarray(available, dtype=bool)] = -np.inf
        question = int(gain.argmax())
        threshold = np.exp(log_cost) * (best / max(1 - best, 1e-7))**power
        return (question if gain[question] > threshold else -1), menu, weights
