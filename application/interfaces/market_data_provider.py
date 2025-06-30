# application/interfaces/market_data_provider.py
from abc import ABC, abstractmethod
from typing import Optional
from domain.entities.market_data import MarketData

class IMarketDataProvider(ABC):
    """Interface para provedores de dados de mercado."""

    @abstractmethod
    def connect(self) -> bool:
        """Conecta à fonte de dados."""

    @abstractmethod
    def get_market_data(self) -> Optional[MarketData]:
        """Retorna um snapshot completo dos dados de mercado."""

    @abstractmethod
    def close(self) -> None:
        """Fecha a conexão com a fonte de dados."""
