# analyzers/confluence/__init__.py
"""
Módulo de análise de confluência para sinais estratégicos.
Contém filtros de contexto e validadores de qualidade.
"""

from .context_filters import (
    ContextFilters,
    MarketStabilityFilter,
    RegimeCompatibilityFilter,
    ManipulationRiskFilter,
    FilterResult
)

__all__ = [
    'ContextFilters',
    'MarketStabilityFilter',
    'RegimeCompatibilityFilter',
    'ManipulationRiskFilter',
    'FilterResult'
]