from __future__ import annotations

from dataclasses import dataclass

from portfolio_model.model import PortfolioDecision


@dataclass(frozen=True)
class IndustryAgentSpec:
    name: str
    display_name: str
    industry: str
    symbols: tuple[str, ...]


@dataclass(frozen=True)
class IndustryAgentResult:
    spec: IndustryAgentSpec
    decisions: list[PortfolioDecision]
    researched: int
    skipped: int
    errors: list[str]
    warnings: list[str]
