# analyzers/patterns/iceberg_detector.py
from typing import List, Optional, Dict
from domain.entities.trade import Trade

class IcebergDetector:
    """Detecta ordens do tipo Iceberg (travamento de preço)."""

    def __init__(self, repetitions=3, min_volume=50):
        self.repetitions = repetitions
        self.min_volume = min_volume

    def detect(self, trade: Trade, recent_trades: List[Trade]) -> Optional[Dict]:
        """Detecta um iceberg (travamento) baseado no trade atual e no histórico recente."""
        if trade.volume < self.min_volume or len(recent_trades) < self.repetitions:
            return None

        similar_trades_count = 0
        total_volume_at_price = 0
        
        # Iceberg = múltiplas ordens do mesmo tamanho no mesmo preço
        # Indica ordem grande fracionada travando o preço
        for t in reversed(recent_trades):
            if abs(t.price - trade.price) < 0.5: # Tolerância de 1 tick
                total_volume_at_price += t.volume
                if t.volume == trade.volume:  # Mesmo tamanho = fracionamento
                    similar_trades_count += 1
        
        if similar_trades_count >= self.repetitions:
            # Detecta se é mais provável ser suporte ou resistência
            # baseado na posição do preço em relação aos trades anteriores
            avg_price_before = sum(t.price for t in recent_trades[-20:-10]) / 10 if len(recent_trades) >= 20 else trade.price
            
            position = "RESISTÊNCIA" if trade.price > avg_price_before else "SUPORTE"
            
            return {
                "pattern": "ICEBERG",
                "price": trade.price,
                "unit_volume": trade.volume,
                "repetitions": similar_trades_count,
                "total_volume": total_volume_at_price,
                "position": position  # Não é side, é posição (suporte/resistência)
            }
            
        return None