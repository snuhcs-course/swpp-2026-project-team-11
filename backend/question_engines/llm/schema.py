# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Structured output of one LLM turn: ask one more question, or propose a food.

The LLM sees only food names, never the extracted features. Its `food` field is an
enum of exactly the names still available, so structured output keeps every
proposal inside the candidate list.
"""
from typing import Literal

from pydantic import BaseModel, Field, create_model


class EngineTurn(BaseModel):
    """The LLM's answer for one turn. `food` is narrowed to the available names per call."""

    action: Literal["ask", "recommend"] = Field(
        description="ask: ask one more question. recommend: propose `food` now.")
    question: str = Field(
        description="When action=ask, one short yes/no question for the user. Otherwise empty.")
    food: str = Field(
        description="The most likely menu given the answers so far; the proposal when action=recommend.")


def build_turn_model(food_names):
    """EngineTurn whose `food` must be one of `food_names` (sent to Gemini as an enum)."""
    return create_model(
        "EngineTurn",
        __base__=EngineTurn,
        food=(Literal[tuple(food_names)], EngineTurn.model_fields["food"]),
    )
