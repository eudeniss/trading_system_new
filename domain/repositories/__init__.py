# domain/repositories/__init__.py
"""
Interfaces de repositórios seguindo Clean Architecture.
Define contratos que devem ser implementados pela camada de infraestrutura.
"""

from .trade_cache import ITradeCache

__all__ = ['ITradeCache']