"""Tax modules — KR NTS 양도세·세제 한도·손실 인식 (Phase 3 PREREG-0008)."""

from sentinelq.tax.capital_gains import (
    DEFAULT_RULES,
    TAX_YEAR_RULES_2026,
    MarketBreakdown,
    TaxYearRules,
    TaxYearSummary,
    UnknownTaxYearError,
    calculate_all,
    calculate_year,
)

__all__ = [
    "DEFAULT_RULES",
    "TAX_YEAR_RULES_2026",
    "MarketBreakdown",
    "TaxYearRules",
    "TaxYearSummary",
    "UnknownTaxYearError",
    "calculate_all",
    "calculate_year",
]
