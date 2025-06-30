# analyzers/patterns/base_pattern_detector.py
from typing import List, Optional, Dict
from domain.entities.trade import Trade
from abc import ABC, abstractmethod

class BasePatternDetector(ABC):
    """Classe base para todos os detectores de padrões."""
    
    def __init__(self, **config):
        self.config = config
    
    @abstractmethod
    def detect(self, trades: List[Trade]) -> Optional[Dict]:
        """Detecta o padrão específico."""
    
    def calculate_volume_stats(self, trades: List[Trade]) -> Dict[str, float]:
        """Calcula estatísticas de volume comuns."""
        if not trades:
            return {'total': 0, 'buy': 0, 'sell': 0}
        
        buy_volume = sum(t.volume for t in trades if t.side.name == "BUY")
        sell_volume = sum(t.volume for t in trades if t.side.name == "SELL")
        
        return {
            'total': buy_volume + sell_volume,
            'buy': buy_volume,
            'sell': sell_volume,
            'buy_ratio': buy_volume / (buy_volume + sell_volume) if (buy_volume + sell_volume) > 0 else 0
        }