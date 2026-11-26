"""Forward-chaining rule engine for sky reasoning.

Facts are triples ``(predicate, subject, object)``, for example
``("velocity", "track:7", 3.2)`` or ``("matches_pattern", "cluster:0", "Orion")``.

Rules are Horn clauses: a conjunction of premise patterns implies one
conclusion pattern. Pattern terms that are strings starting with ``?`` are
variables. Premises may also use the built-in comparison predicates
``gt, ge, lt, le, eq, ne`` (e.g. ``("gt", "?v", 1.0)``), which test bound
values instead of matching facts.

:func:`reason` applies all rules repeatedly until no new fact is derived (the
least fixpoint). Termination is guaranteed: rules must be *range-restricted*
(every conclusion variable occurs in a fact premise), so conclusions only
combine constants that already appear in the facts, and there are finitely
many such triples. Running :func:`reason` again on its own output derives
nothing new (idempotence).
"""

from __future__ import annotations

import operator
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

Fact = tuple[str, Any, Any]
Pattern = tuple[Any, Any, Any]
Bindings = Mapping[str, Any]

BUILTINS: dict[str, Callable[[Any, Any], bool]] = {
    "gt": operator.gt,
    "ge": operator.ge,
    "lt": operator.lt,
    "le": operator.le,
    "eq": operator.eq,
    "ne": operator.ne,
}


def is_variable(term: Any) -> bool:
    return isinstance(term, str) and term.startswith("?")


def _variables(pattern: Pattern) -> set[str]:
    return {t for t in pattern if is_variable(t)}


@dataclass(frozen=True)
class Rule:
    """``IF premise_1 AND ... AND premise_n THEN conclusion``."""

    name: str
    premises: tuple[Pattern, ...]
    conclusion: Pattern

    def __post_init__(self) -> None:
        if not self.premises:
            raise ValueError(f"Rule {self.name!r} needs at least one premise")
        fact_vars: set[str] = set()
        for premise in self.premises:
            if len(premise) != 3:
                raise ValueError(f"Rule {self.name!r}: premises must be triples")
            if premise[0] not in BUILTINS:
                fact_vars |= _variables(premise)
        for premise in self.premises:
            if premise[0] in BUILTINS and not _variables(premise) <= fact_vars:
                raise ValueError(
                    f"Rule {self.name!r}: comparison {premise} uses unbound variables"
                )
        if self.conclusion[0] in BUILTINS or is_variable(self.conclusion[0]):
            raise ValueError(f"Rule {self.name!r}: conclusion needs a fixed predicate")
        if not _variables(self.conclusion) <= fact_vars:
            raise ValueError(
                f"Rule {self.name!r} is not range-restricted: conclusion variables "
                f"{sorted(_variables(self.conclusion) - fact_vars)} never bound"
            )


@dataclass(frozen=True)
class Conclusion:
    """A derived fact with its justification (for explanations in the UI)."""

    fact: Fact
    rule: str
    support: tuple[Fact, ...]
    iteration: int


def substitute(term: Any, bindings: Bindings) -> Any:
    return bindings.get(term, term) if is_variable(term) else term


def unify(pattern: Pattern, fact: Fact, bindings: Bindings) -> dict[str, Any] | None:
    """Extend ``bindings`` so ``pattern`` equals ``fact``, or return ``None``."""
    result = dict(bindings)
    for p, f in zip(pattern, fact):
        if is_variable(p):
            if p in result:
                if result[p] != f:
                    return None
            else:
                result[p] = f
        elif p != f:
            return None
    return result


def _match_premises(
    premises: Sequence[Pattern],
    index: Mapping[str, Sequence[Fact]],
    bindings: Bindings,
    support: tuple[Fact, ...],
) -> Iterable[tuple[dict[str, Any], tuple[Fact, ...]]]:
    """All bindings satisfying the premises (fact patterns first, then tests)."""
    if not premises:
        yield dict(bindings), support
        return
    first, rest = premises[0], premises[1:]
    if first[0] in BUILTINS:
        left, right = substitute(first[1], bindings), substitute(first[2], bindings)
        try:
            ok = BUILTINS[first[0]](left, right)
        except TypeError:
            ok = False
        if ok:
            yield from _match_premises(rest, index, bindings, support)
        return
    for fact in index.get(first[0], ()):
        extended = unify(first, fact, bindings)
        if extended is not None:
            yield from _match_premises(rest, index, extended, support + (fact,))


def _ordered(premises: Sequence[Pattern]) -> tuple[Pattern, ...]:
    """Evaluate comparisons after the fact patterns that bind their variables."""
    facts = [p for p in premises if p[0] not in BUILTINS]
    tests = [p for p in premises if p[0] in BUILTINS]
    return tuple(facts + tests)


def reason(
    facts: Iterable[Fact],
    rules: Sequence[Rule],
    *,
    max_iterations: int = 1000,
) -> list[Conclusion]:
    """Forward-chain ``rules`` over ``facts`` to the least fixpoint.

    Pure: inputs are not modified. Returns the newly derived facts (not the
    input facts) in derivation order, each with the rule and supporting facts
    that produced it.

    Raises:
        RuntimeError: If the fixpoint is not reached within ``max_iterations``
            (impossible for range-restricted rules over finite facts; a guard).
    """
    known: set[Fact] = set()
    index: dict[str, list[Fact]] = {}
    for fact in facts:
        fact = tuple(fact)  # type: ignore[assignment]
        if len(fact) != 3:
            raise ValueError(f"Facts must be (predicate, subject, object): {fact!r}")
        if fact not in known:
            known.add(fact)
            index.setdefault(fact[0], []).append(fact)

    ordered = [(rule, _ordered(rule.premises)) for rule in rules]
    derived: list[Conclusion] = []
    for iteration in range(1, max_iterations + 1):
        new: list[Conclusion] = []
        for rule, premises in ordered:
            for bindings, support in _match_premises(premises, index, {}, ()):
                fact = tuple(substitute(t, bindings) for t in rule.conclusion)
                if fact not in known and all(c.fact != fact for c in new):
                    new.append(Conclusion(fact, rule.name, support, iteration))  # type: ignore[arg-type]
        if not new:
            return derived
        for conclusion in new:
            known.add(conclusion.fact)
            index.setdefault(conclusion.fact[0], []).append(conclusion.fact)
        derived.extend(new)
    raise RuntimeError(f"No fixpoint after {max_iterations} iterations")


@dataclass(frozen=True)
class ReasonerConfig:
    """Thresholds used by the default rules (``reasoning`` in config.yaml)."""

    satellite_velocity_threshold: float = 1.0
    min_cluster_size: int = 4
    match_confidence_threshold: float = 0.6
    anomaly_brightness_threshold: float = 230.0

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | None) -> "ReasonerConfig":
        values = values or {}
        known = {f: values[f] for f in cls.__dataclass_fields__ if f in values}
        return cls(**known)


def default_rules(config: ReasonerConfig | None = None) -> list[Rule]:
    """AstraGraph's sky rules.

    * ``identify_constellation`` – cluster_size >= min AND matches_known_pattern.
    * ``full_view`` / ``partial_view`` – split identifications by match
      confidence; partial views get their hidden stars rendered as ghosts.
    * ``render_ghost`` – a hidden template star of a partial view.
    * ``star_in_constellation`` – chain cluster membership to the identity.
    * ``is_satellite`` – linear trajectory AND speed > threshold.
    * ``is_anomaly`` – brightness > threshold AND not in the catalog.
    """
    cfg = config or ReasonerConfig()
    return [
        Rule(
            "identify_constellation",
            (
                ("cluster_size", "?c", "?n"),
                ("ge", "?n", cfg.min_cluster_size),
                ("matches_pattern", "?c", "?k"),
            ),
            ("identified_as", "?c", "?k"),
        ),
        Rule(
            "full_view",
            (
                ("identified_as", "?c", "?k"),
                ("match_confidence", "?c", "?x"),
                ("ge", "?x", cfg.match_confidence_threshold),
            ),
            ("full_view", "?c", "?k"),
        ),
        Rule(
            "partial_view",
            (
                ("identified_as", "?c", "?k"),
                ("match_confidence", "?c", "?x"),
                ("lt", "?x", cfg.match_confidence_threshold),
            ),
            ("partial_view", "?c", "?k"),
        ),
        Rule(
            "render_ghost",
            (("partial_view", "?c", "?k"), ("hidden_star", "?c", "?h")),
            ("render_ghost", "?h", "?k"),
        ),
        Rule(
            "star_in_constellation",
            (("member_of", "?s", "?c"), ("identified_as", "?c", "?k")),
            ("in_constellation", "?s", "?k"),
        ),
        Rule(
            "is_satellite",
            (
                ("trajectory_linear", "?t", True),
                ("velocity", "?t", "?v"),
                ("gt", "?v", cfg.satellite_velocity_threshold),
            ),
            ("is_satellite", "?t", True),
        ),
        Rule(
            "is_anomaly",
            (
                ("brightness", "?s", "?b"),
                ("gt", "?b", cfg.anomaly_brightness_threshold),
                ("not_in_catalog", "?s", True),
            ),
            ("is_anomaly", "?s", True),
        ),
    ]


class SkyReasoner:
    """Apply AstraGraph's rules to scene facts."""

    def __init__(self, config: ReasonerConfig | None = None) -> None:
        self.config = config or ReasonerConfig()
        self.rules = default_rules(self.config)

    def reason(
        self, facts: Iterable[Fact], rules: Sequence[Rule] | None = None
    ) -> list[Conclusion]:
        """Derive conclusions from ``facts`` (default rules if none given)."""
        return reason(facts, self.rules if rules is None else rules)

    @staticmethod
    def query(conclusions: Iterable[Conclusion], predicate: str) -> list[Fact]:
        """Derived facts with the given predicate, in derivation order."""
        return [c.fact for c in conclusions if c.fact[0] == predicate]
