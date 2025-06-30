# infrastructure/cache/__init__.py
"""
Módulo de cache para o sistema de trading.
Fornece implementações de cache em memória para dados de mercado.
"""

from .trade_memory_cache import TradeMemoryCache

__all__ = ['TradeMemoryCache']