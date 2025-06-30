# analyzers/patterns/absorption_detector.py
from collections import defaultdict
from typing import List, Optional, Dict
from domain.entities.trade import Trade

class AbsorptionDetector:
    """Detecta padrões de absorção e escoras de volume."""

    def __init__(self, concentration_threshold=0.4, min_volume_threshold=200):
        self.concentration_threshold = concentration_threshold
        self.min_volume_threshold = min_volume_threshold

    def detect(self, recent_trades: List[Trade]) -> Optional[Dict]:
        """Analisa os últimos trades para detectar uma escora."""
        if len(recent_trades) < 50:
            return None

        level_analysis = defaultdict(lambda: {'volume': 0, 'buy_vol': 0, 'sell_vol': 0})
        total_volume = 0

        for trade in recent_trades:
            level = round(trade.price / 0.5) * 0.5
            analysis = level_analysis[level]
            analysis['volume'] += trade.volume
            
            if trade.side.name == 'BUY':
                analysis['buy_vol'] += trade.volume
            else:
                analysis['sell_vol'] += trade.volume
            
            total_volume += trade.volume

        if total_volume == 0:
            return None

        for level, analysis in level_analysis.items():
            concentration = analysis['volume'] / total_volume
            if concentration > self.concentration_threshold and analysis['volume'] > self.min_volume_threshold:
                # Análise da absorção - sempre tem direção!
                buy_ratio = analysis['buy_vol'] / analysis['volume']
                sell_ratio = analysis['sell_vol'] / analysis['volume']
                
                # Absorção na COMPRA: vendedores estão sendo absorvidos (suporte)
                if sell_ratio > 0.6:  # Maioria vendendo mas preço segura
                    escora_type = "ABSORÇÃO"
                    direction = "COMPRA"
                # Absorção na VENDA: compradores estão sendo absorvidos (resistência)
                elif buy_ratio > 0.6:  # Maioria comprando mas preço não sobe
                    escora_type = "ABSORÇÃO"
                    direction = "VENDA"
                # Outros casos são suporte/resistência normais
                elif analysis['buy_vol'] > analysis['sell_vol']:
                    escora_type = "SUPORTE"
                    direction = "COMPRA"
                else:
                    escora_type = "RESISTÊNCIA"
                    direction = "VENDA"
                
                return {
                    "pattern": "ESCORA_DETECTADA",
                    "level": level,
                    "volume": analysis['volume'],
                    "concentration": concentration,
                    "type": escora_type,
                    "direction": direction,
                }
        
        return None