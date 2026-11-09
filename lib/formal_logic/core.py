"""Generic temporal and deontic logic primitives.

This module provides reusable logic building blocks for complaint and evidence
reasoning without embedding HACC- or Title-18-specific facts, parties, or
obligations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, Optional, Set, Tuple


class DeonticModality(Enum):
    """Deontic modalities for obligations, permissions, and prohibitions."""

    OBLIGATORY = "O"
    PERMITTED = "P"
    PROHIBITED = "F"
    OPTIONAL = "OPT"


class TemporalOperator(Enum):
    """Basic temporal relations for ordering events."""

    BEFORE = "before"
    AFTER = "after"
    COINCIDENT = "coincident"
    DURING = "during"
    OVERLAPS = "overlaps"
    STARTS = "starts"
    FINISHES = "finishes"
    EQUALS = "equals"


class LogicalOperator(Enum):
    """Basic logical connectives."""

    AND = "and"
    OR = "or"
    NOT = "not"
    IMPLIES = "implies"
    IFF = "iff"
    FORALL = "forall"
    EXISTS = "exists"


@dataclass(frozen=True)
class TimeInterval:
    """Represents a time interval with optional end or duration."""

    start: Optional[datetime] = None
    end: Optional[datetime] = None
    duration_days: Optional[int] = None

    def resolved_end(self) -> Optional[datetime]:
        if self.end is not None:
            return self.end
        if self.start is not None and self.duration_days is not None:
            return self.start + timedelta(days=self.duration_days)
        return None

    def contains(self, at_time: datetime) -> bool:
        resolved_end = self.resolved_end()
        if self.start is not None and at_time < self.start:
            return False
        if resolved_end is not None and at_time > resolved_end:
            return False
        return True

    def __str__(self) -> str:
        resolved_end = self.resolved_end()
        if self.start and resolved_end:
            return f"[{self.start.date()} to {resolved_end.date()}]"
        if self.duration_days is not None:
            return f"{self.duration_days} days from start"
        return "unbounded"


@dataclass(frozen=True)
class Party:
    """Represents a legal or factual actor."""

    name: str
    role: str
    entity_id: str

    def __str__(self) -> str:
        return f"{self.name} ({self.role})"


@dataclass(frozen=True)
class Action:
    """Represents an action that may be required, permitted, or forbidden."""

    verb: str
    object_noun: str
    action_id: str

    def __str__(self) -> str:
        return f"{self.verb} {self.object_noun}"


class Proposition(ABC):
    """Base class for evaluable logical propositions."""

    @abstractmethod
    def __str__(self) -> str:
        """Return the canonical text used to identify this proposition in a model."""

    @abstractmethod
    def evaluate(self, model: Dict[str, Any]) -> bool:
        """Evaluate this proposition against the truth assignments in ``model``."""


@dataclass(frozen=True)
class Predicate(Proposition):
    """Simple predicate over positional arguments."""

    name: str
    args: Tuple[Any, ...] = field(default_factory=tuple)

    def __str__(self) -> str:
        args_str = ", ".join(str(arg) for arg in self.args)
        return f"{self.name}({args_str})"

    def evaluate(self, model: Dict[str, Any]) -> bool:
        return bool(model.get(str(self), False))


@dataclass(frozen=True)
class Conjunction(Proposition):
    left: Proposition
    right: Proposition

    def __str__(self) -> str:
        return f"({self.left} and {self.right})"

    def evaluate(self, model: Dict[str, Any]) -> bool:
        return self.left.evaluate(model) and self.right.evaluate(model)


@dataclass(frozen=True)
class Disjunction(Proposition):
    left: Proposition
    right: Proposition

    def __str__(self) -> str:
        return f"({self.left} or {self.right})"

    def evaluate(self, model: Dict[str, Any]) -> bool:
        return self.left.evaluate(model) or self.right.evaluate(model)


@dataclass(frozen=True)
class Negation(Proposition):
    prop: Proposition

    def __str__(self) -> str:
        return f"not ({self.prop})"

    def evaluate(self, model: Dict[str, Any]) -> bool:
        return not self.prop.evaluate(model)


@dataclass(frozen=True)
class Implication(Proposition):
    antecedent: Proposition
    consequent: Proposition

    def __str__(self) -> str:
        return f"({self.antecedent} -> {self.consequent})"

    def evaluate(self, model: Dict[str, Any]) -> bool:
        return (not self.antecedent.evaluate(model)) or self.consequent.evaluate(model)


@dataclass(frozen=True)
class DeonticStatement:
    """A deontic statement about what an actor must, may, or must not do."""

    modality: DeonticModality
    actor: Party
    action: Action
    recipient: Optional[Party] = None
    time_interval: Optional[TimeInterval] = None
    condition: Optional[Proposition] = None

    def __str__(self) -> str:
        recipient_str = f" to {self.recipient}" if self.recipient else ""
        time_str = f" {self.time_interval}" if self.time_interval else ""
        condition_str = f" when {self.condition}" if self.condition else ""
        return f"{self.modality.value}({self.actor}, {self.action}{recipient_str}{time_str}{condition_str})"


class DeonticKnowledgeBase:
    """Stores deontic statements, rules, and ground facts."""

    def __init__(self) -> None:
        self.statements: Set[DeonticStatement] = set()
        self.rules: list[tuple[Proposition, DeonticStatement]] = []
        self.facts: Dict[str, bool] = {}
        self.derived_statements: Set[DeonticStatement] = set()

    def add_statement(self, statement: DeonticStatement) -> None:
        self.statements.add(statement)

    def add_rule(self, condition: Proposition, statement: DeonticStatement) -> None:
        self.rules.append((condition, statement))

    def add_fact(self, fact_name: str, value: bool = True) -> None:
        self.facts[fact_name] = value

    def infer_statements(self) -> Set[DeonticStatement]:
        derived = set(self.statements)
        changed = True
        while changed:
            changed = False
            for condition, statement in self.rules:
                if condition.evaluate(self.facts) and statement not in derived:
                    derived.add(statement)
                    changed = True
        self.derived_statements = derived
        return derived

    def get_statements(
        self,
        *,
        modality: Optional[DeonticModality] = None,
        actor: Optional[Party] = None,
        recipient: Optional[Party] = None,
    ) -> Set[DeonticStatement]:
        statements = self.derived_statements or self.statements
        return {
            statement
            for statement in statements
            if (modality is None or statement.modality == modality)
            and (actor is None or statement.actor == actor)
            and (recipient is None or statement.recipient == recipient)
        }

    def check_compliance(self, party: Party, action: Action, at_time: datetime) -> tuple[bool, str]:
        statements = self.derived_statements or self.statements
        for statement in statements:
            if statement.actor != party or statement.action != action:
                continue
            if statement.modality == DeonticModality.PROHIBITED:
                return False, f"violates prohibition: {statement}"
            if statement.modality == DeonticModality.OBLIGATORY:
                if statement.time_interval is None or statement.time_interval.contains(at_time):
                    return True, f"complies with obligation: {statement}"
        return True, "action is not prohibited"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "facts": dict(sorted(self.facts.items())),
            "statements": [str(statement) for statement in sorted(self.statements, key=str)],
            "derived_statements": [
                str(statement) for statement in sorted(self.derived_statements, key=str)
            ],
        }


__all__ = [
    "Action",
    "Conjunction",
    "DeonticKnowledgeBase",
    "DeonticModality",
    "DeonticStatement",
    "Disjunction",
    "Implication",
    "LogicalOperator",
    "Negation",
    "Party",
    "Predicate",
    "Proposition",
    "TemporalOperator",
    "TimeInterval",
]
