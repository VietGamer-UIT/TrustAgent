"""
TrustAgent.Forensics — Z3 Solver Wrapper

The TrustAgentSolver is the central component of the Symbolic Layer.
It wraps the Z3 Theorem Prover with a clean interface for verifying
business transactions against a registry of encoded rules.

Architecture Role:
    Neural Layer (Gemini) → JSON data → TrustAgentSolver → SAT/UNSAT

Key Design Decisions:
1. Each verification creates a FRESH solver (no state leakage between checks)
2. Rules are registered once and reused across verifications
3. Timing is measured for performance monitoring (target: < 5ms)
4. Results include full audit metadata for the Forensics layer
"""

from __future__ import annotations

import time
from typing import Any

from z3 import Solver, sat, unsat

from .models import (
    VerificationResult,
    VerificationStatus,
    RuleViolation,
    RuleSeverity,
)
from .rules.base_rule import BusinessRule


class TrustAgentSolver:
    """
    Main verification engine wrapping Z3 Theorem Prover.

    Usage:
        solver = TrustAgentSolver()
        solver.register_rule(VietnamCashPaymentRule())
        solver.register_rule(KoreaTaxRefundRule())

        result = solver.verify(transaction_data, rule_names=["vn_cash_payment_threshold"])
        if result.is_compliant:
            execute_transaction()
        else:
            block_and_report(result.violations)
    """

    def __init__(self, timeout_ms: int = 5000) -> None:
        """
        Initialize the TrustAgent Solver.

        Args:
            timeout_ms: Z3 solver timeout in milliseconds (default: 5000ms)
        """
        self._rules: dict[str, BusinessRule] = {}
        self._timeout_ms = timeout_ms

    def register_rule(self, rule: BusinessRule) -> None:
        """
        Register a business rule for future verification checks.

        Args:
            rule: BusinessRule instance to register

        Raises:
            ValueError: If a rule with the same name is already registered
        """
        if rule.name in self._rules:
            raise ValueError(
                f"Rule '{rule.name}' is already registered. "
                f"Use unregister_rule() first to replace it."
            )
        self._rules[rule.name] = rule

    def unregister_rule(self, rule_name: str) -> None:
        """Remove a registered rule by name."""
        self._rules.pop(rule_name, None)

    def get_registered_rules(self) -> list[str]:
        """Return names of all registered rules."""
        return list(self._rules.keys())

    def verify(
        self,
        data: dict[str, Any],
        rule_names: list[str] | None = None,
        dynamic_thresholds: dict[str, int] | None = None,
    ) -> VerificationResult:
        """
        Verify transaction data against registered business rules using Z3.

        For each rule, a fresh Z3 Solver is created to ensure isolation.
        The rule encodes its constraints (with optional dynamic thresholds from RAG),
        binds the actual data, and the solver checks for satisfiability.

        Args:
            data: Transaction data dictionary (from Pydantic model)
            rule_names: Specific rules to check. If None, checks ALL registered rules.
            dynamic_thresholds: Thresholds from Legal RAG Module.
                                If provided, rules use these instead of hardcoded defaults.
                                Format: {"VN_CASH_THRESHOLD": 20000000, ...}

        Returns:
            VerificationResult with status, violations, and timing info
        """
        start_time = time.perf_counter()

        # Determine which rules to check
        if rule_names:
            rules_to_check = {
                name: self._rules[name]
                for name in rule_names
                if name in self._rules
            }
            missing = set(rule_names) - set(rules_to_check.keys())
            if missing:
                raise ValueError(f"Unknown rules: {missing}")
        else:
            rules_to_check = self._rules

        if not rules_to_check:
            return VerificationResult(
                status=VerificationStatus.SAT,
                is_compliant=True,
                rules_checked=[],
                verification_time_ms=0.0,
                raw_input=data,
                explanation="No rules registered to check.",
            )

        # Verify each rule independently
        violations: list[RuleViolation] = []
        rules_checked: list[str] = []
        z3_model_str: str | None = None

        for rule_name, rule in rules_to_check.items():
            rules_checked.append(rule_name)

            # Create a FRESH solver for each rule (isolation)
            z3_solver = Solver()
            z3_solver.set("timeout", self._timeout_ms)

            try:
                # Let the rule encode its constraints + bind data
                # Pass dynamic_thresholds from RAG (None = use rule's own defaults)
                rule.encode(z3_solver, data, dynamic_thresholds)

                # Ask Z3: "Can all constraints be satisfied simultaneously?"
                result = z3_solver.check()

                if result == unsat:
                    # UNSAT = The data contradicts the rule → VIOLATION
                    violations.append(
                        RuleViolation(
                            rule_name=rule.name,
                            rule_description=rule.description,
                            severity=RuleSeverity(rule.severity),
                            violation_detail=rule.get_violation_detail(data),
                            legal_reference=rule.legal_reference,
                        )
                    )
                elif result == sat:
                    # SAT = Data is consistent with the rule → COMPLIANT
                    model = z3_solver.model()
                    z3_model_str = str(model)

            except Exception as e:
                # Z3 error or encoding error → treat as UNKNOWN
                violations.append(
                    RuleViolation(
                        rule_name=rule.name,
                        rule_description=rule.description,
                        severity=RuleSeverity.WARNING,
                        violation_detail=f"Verification error: {str(e)}",
                        legal_reference=rule.legal_reference,
                    )
                )

        # Calculate timing
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Determine overall status
        has_violations = len(violations) > 0
        status = VerificationStatus.UNSAT if has_violations else VerificationStatus.SAT

        # Build explanation
        if has_violations:
            violation_summaries = [v.violation_detail for v in violations]
            explanation = (
                f"❌ BLOCKED: {len(violations)} rule violation(s) detected. "
                + " | ".join(violation_summaries)
            )
        else:
            explanation = (
                f"✅ APPROVED: Transaction passes all {len(rules_checked)} rule(s). "
                f"Verification completed in {elapsed_ms:.2f}ms."
            )

        return VerificationResult(
            status=status,
            is_compliant=not has_violations,
            violations=violations,
            rules_checked=rules_checked,
            verification_time_ms=round(elapsed_ms, 3),
            raw_input=data,
            z3_model=z3_model_str,
            explanation=explanation,
        )

    def verify_transaction(self, data: dict[str, Any]) -> VerificationResult:
        """Shorthand: verify against ALL registered rules."""
        return self.verify(data)

    def __repr__(self) -> str:
        rule_names = ", ".join(self._rules.keys()) or "none"
        return f"<TrustAgentSolver rules=[{rule_names}]>"
