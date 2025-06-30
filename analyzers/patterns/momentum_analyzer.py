# analyzers/patterns/momentum_analyzer.py
from typing import List, Optional, Dict
from domain.entities.trade import Trade

class MomentumAnalyzer:
    """Detecta divergências e momentum extremo."""

    def __init__(self, divergence_roc_threshold=50, extreme_roc_threshold=100):
        self.divergence_roc_threshold = divergence_roc_threshold
        self.extreme_roc_threshold = extreme_roc_threshold

    def detect_divergence(self, recent_trades: List[Trade], cvd_roc: float) -> Optional[Dict]:
        """Detecta divergências entre preço e fluxo (CVD ROC)."""
        if not recent_trades or abs(cvd_roc) < self.divergence_roc_threshold:
            return None

        prices = [t.price for t in recent_trades]
        price_trend = prices[-1] - prices[0]
        current_price = prices[-1]

        # Divergência de baixa: preço sobe, fluxo cai
        if price_trend > 1.0 and cvd_roc < -self.divergence_roc_threshold:
            return {
                "pattern": "DIVERGENCIA_BAIXA",
                "price": current_price,
                "cvd_roc": cvd_roc
            }
        
        # Divergência de alta: preço cai, fluxo sobe
        if price_trend < -1.0 and cvd_roc > self.divergence_roc_threshold:
            return {
                "pattern": "DIVERGENCIA_ALTA",
                "price": current_price,
                "cvd_roc": cvd_roc
            }

        # Momentum Extremo
        if abs(cvd_roc) > self.extreme_roc_threshold:
            return {
                "pattern": "MOMENTUM_EXTREMO",
                "price": current_price,
                "cvd_roc": cvd_roc,
                "direction": "COMPRA" if cvd_roc > 0 else "VENDA"
            }
            
        return None