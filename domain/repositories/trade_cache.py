# domain/repositories/trade_cache.py
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from domain.entities.trade import Trade

class ITradeCache(ABC):
    """Interface para cache de trades seguindo Clean Architecture."""
    
    @abstractmethod
    def add_trade(self, symbol: str, trade: Trade) -> None:
        """Adiciona um trade ao cache."""
    
    @abstractmethod
    def add_trades(self, symbol: str, trades: List[Trade]) -> None:
        """Adiciona múltiplos trades ao cache."""
    
    @abstractmethod
    def get_recent_trades(self, symbol: str, count: int) -> List[Trade]:
        """Retorna os N trades mais recentes."""
    
    @abstractmethod
    def get_all_trades(self, symbol: str) -> List[Trade]:
        """Retorna todos os trades em cache para um símbolo."""
    
    @abstractmethod
    def get_trades_by_time_window(self, symbol: str, seconds: int) -> List[Trade]:
        """Retorna trades dos últimos N segundos."""
    
    @abstractmethod
    def clear(self, symbol: Optional[str] = None) -> None:
        """Limpa o cache (todos os símbolos ou apenas um)."""
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas de uso do cache."""
    
    @abstractmethod
    def get_size(self, symbol: str) -> int:
        """Retorna quantidade de trades em cache para um símbolo."""
