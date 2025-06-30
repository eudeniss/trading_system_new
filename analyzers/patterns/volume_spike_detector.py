# analyzers/patterns/volume_spike_detector.py
from typing import List, Optional, Dict
from collections import deque
import numpy as np
from domain.entities.trade import Trade

class VolumeSpikeDetector:
    """Detecta picos anormais de volume."""
    
    def __init__(self, spike_multiplier: float = 3.0, history_size: int = 100):
        self.spike_multiplier = spike_multiplier
        self.volume_history = deque(maxlen=history_size)
        self.baseline_window = 50
    
    def detect(self, recent_trades: List[Trade]) -> Optional[Dict]:
        """Detecta spike de volume comparado com baseline."""
        if not recent_trades:
            return None
        
        # Calcula volume dos trades recentes (últimos segundos)
        current_volume = sum(t.volume for t in recent_trades[-10:])
        
        # Adiciona ao histórico
        self.volume_history.append(current_volume)
        
        if len(self.volume_history) < self.baseline_window:
            return None
        
        # Calcula baseline (mediana para robustez)
        baseline_volumes = list(self.volume_history)[-self.baseline_window:-10]
        if not baseline_volumes:
            return None
            
        baseline = np.median(baseline_volumes)
        
        if baseline > 0 and current_volume > baseline * self.spike_multiplier:
            # Determina direção do spike
            buy_volume = sum(t.volume for t in recent_trades[-10:] if t.side.value == "BUY")
            sell_volume = sum(t.volume for t in recent_trades[-10:] if t.side.value == "SELL")
            
            direction = "COMPRA" if buy_volume > sell_volume else "VENDA"
            
            return {
                "pattern": "VOLUME_SPIKE",
                "current_volume": current_volume,
                "baseline": baseline,
                "multiplier": current_volume / baseline,
                "direction": direction,
                "buy_volume": buy_volume,
                "sell_volume": sell_volume
            }
        
        return None