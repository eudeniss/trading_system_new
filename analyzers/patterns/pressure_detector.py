# analyzers/patterns/pressure_detector.py
from typing import List, Optional, Dict
from domain.entities.trade import Trade, TradeSide

class PressureDetector:
    """Detecta pressão compradora/vendedora baseada em volume direcional."""
    
    def __init__(self, threshold: float = 0.8, min_volume: int = 100):
        self.threshold = threshold  # 80% do volume em uma direção
        self.min_volume = min_volume
    
    def detect(self, recent_trades: List[Trade]) -> Optional[Dict]:
        """Detecta pressão compradora ou vendedora."""
        if len(recent_trades) < 10:
            return None
        
        buy_volume = sum(t.volume for t in recent_trades if t.side == TradeSide.BUY)
        sell_volume = sum(t.volume for t in recent_trades if t.side == TradeSide.SELL)
        total_volume = buy_volume + sell_volume
        
        if total_volume < self.min_volume:
            return None
        
        buy_ratio = buy_volume / total_volume
        sell_ratio = sell_volume / total_volume
        
        if buy_ratio >= self.threshold:
            return {
                "pattern": "PRESSAO_COMPRA",
                "buy_volume": buy_volume,
                "sell_volume": sell_volume,
                "ratio": buy_ratio,
                "total_volume": total_volume,
                "direction": "COMPRA"
            }
        elif sell_ratio >= self.threshold:
            return {
                "pattern": "PRESSAO_VENDA",
                "buy_volume": buy_volume,
                "sell_volume": sell_volume,
                "ratio": sell_ratio,
                "total_volume": total_volume,
                "direction": "VENDA"
            }
        
        return None