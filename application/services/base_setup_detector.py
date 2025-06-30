# application/services/base_setup_detector.py
"""
Classe base para detectores de setup.
Movida para evitar imports circulares.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from domain.entities.trade import Trade
from domain.entities.book import OrderBook
from domain.entities.strategic_signal import StrategicSignal, SetupType


class SetupDetector(ABC):
    """Classe base abstrata para todos os detectores de setup."""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
    
    @abstractmethod
    def get_supported_types(self) -> List[SetupType]:
        """Retorna lista de tipos de setup suportados."""
    
    @abstractmethod
    def detect(self,
               symbol: str,
               trades: List[Trade],
               book: Optional[OrderBook],
               market_context: Dict) -> List[StrategicSignal]:
        """Detecta setups nos dados fornecidos."""
