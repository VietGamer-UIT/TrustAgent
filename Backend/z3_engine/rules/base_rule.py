"""
TrustAgent.Forensics — Abstract Business Rule Base Class

All business rules must inherit from BusinessRule and implement:
- encode(): Add Z3 constraints to the solver
- describe(): Return a human-readable description
- get_legal_reference(): Return the legal basis for this rule

This abstraction allows the system to dynamically load and apply
different rulesets for different jurisdictions (Vietnam, Korea, etc.)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from z3 import Solver


class BusinessRule(ABC):
    """
    Abstract base class for business rules encoded as Z3 constraints.

    Each rule represents a specific legal regulation or company policy
    that must be mathematically verified before an AI Agent action
    can be executed.

    The rule follows the Policy Encoding pattern:
    1. Declare Z3 symbolic variables
    2. Add constraint(s) representing the legal rule
    3. Bind actual transaction data
    4. Let the solver determine SAT/UNSAT
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Technical identifier for this rule (e.g., 'vn_cash_payment_threshold')."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of the rule."""
        ...

    @property
    @abstractmethod
    def legal_reference(self) -> str:
        """Legal basis or regulation reference (e.g., 'Circular 96/2015/TT-BTC')."""
        ...

    @property
    def severity(self) -> str:
        """Default severity level for violations of this rule."""
        return "critical"

    @abstractmethod
    def encode(self, solver: Solver, data: dict[str, Any], dynamic_thresholds: dict[str, int] | None = None) -> None:
        """
        Encode this business rule as Z3 constraints and add them to the solver.

        This method must:
        1. Declare Z3 variables (Int, Bool, Real, etc.)
        2. Add the legal/policy constraint using solver.add()
        3. Bind the actual data values from the transaction

        Args:
            solver: Z3 Solver instance to add constraints to
            data: Dictionary of transaction data (from Pydantic model)
            dynamic_thresholds: Thresholds extracted from RAG (Legal RAG Module).
                                If None, use hardcoded class-level defaults.
                                Format: {"VN_CASH_THRESHOLD": 20000000}

        Example:
            z3_amount = Int('amount')
            z3_is_cash = Bool('is_cash')
            threshold = (dynamic_thresholds or {}).get('VN_CASH_THRESHOLD', 20_000_000)
            solver.add(Implies(z3_amount >= threshold, Not(z3_is_cash)))
            solver.add(z3_amount == data['amount'])
            solver.add(z3_is_cash == data['is_cash_payment'])
        """
        ...

    @abstractmethod
    def get_violation_detail(self, data: dict[str, Any]) -> str:
        """
        Generate a human-readable explanation of why the data violates this rule.

        Called only when Z3 returns UNSAT for this rule's constraints.

        Args:
            data: The transaction data that caused the violation

        Returns:
            Detailed violation explanation string
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self.name}>"
