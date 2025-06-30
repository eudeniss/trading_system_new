# analyzers/statistics/cvd_calculator.py (SEM STATE MANAGER)
from typing import Any, Dict, List
import numpy as np
from collections import deque
from domain.entities.trade import Trade, TradeSide
import logging

logger = logging.getLogger(__name__)

class CvdCalculator:
    """Calcula o Cumulative Volume Delta (CVD) - SEM PERSISTÊNCIA."""
    
    def __init__(self, history_size=1000, state_manager=None):
        self.cvd_history = deque(maxlen=history_size)
        self.cumulative_cvd = 0
        # CVD sempre começa do ZERO - sem persistência!
        self.cumulative_cvd_total = {'WDO': 0, 'DOL': 0}
        # Ignora state_manager mesmo se passado
        logger.info("CVD Calculator inicializado sem persistência - valores começam em 0")

    def calculate_cvd_for_trades(self, trades: List[Trade]) -> int:
        """Calcula o CVD para uma lista de trades."""
        if not trades:
            return 0
        
        try:
            volumes = np.array([trade.volume for trade in trades])
            sides = np.array([1 if trade.side == TradeSide.BUY else -1 for trade in trades])
            
            if volumes.size == 0 or sides.size == 0:
                return 0

            return int(np.sum(volumes * sides))
        except (IndexError, TypeError) as e:
            logger.error(f"Erro ao calcular CVD para trades. Erro: {e}", exc_info=True)
            return 0

    def update_and_get_roc(self, recent_trades: List[Trade], roc_period=10) -> float:
        """Atualiza o histórico de CVD e calcula o Rate of Change (ROC)."""
        if not recent_trades:
            return 0.0

        current_cvd = self.calculate_cvd_for_trades(recent_trades)
        self.cvd_history.append(current_cvd)

        if len(self.cvd_history) < roc_period:
            return 0.0
            
        try:
            cvd_then = self.cvd_history[-roc_period]
            
            if cvd_then != 0:
                return ((current_cvd - cvd_then) / abs(cvd_then)) * 100
            
            return 0.0 if current_cvd == 0 else 100.0
        except IndexError as e:
            logger.error(
                f"Erro de índice ao calcular ROC. "
                f"Tamanho do histórico: {len(self.cvd_history)}, Período ROC: {roc_period}. Erro: {e}",
                exc_info=True
            )
            return 0.0

    def update_cumulative(self, trade: Trade):
        """Atualiza o CVD acumulado TOTAL (apenas em memória)."""
        symbol = trade.symbol
        
        if symbol not in self.cumulative_cvd_total:
            logger.warning(f"Símbolo desconhecido: {symbol}")
            return
        
        if trade.side == TradeSide.BUY:
            self.cumulative_cvd_total[symbol] += trade.volume
        else:
            self.cumulative_cvd_total[symbol] -= trade.volume
        
        # NÃO SALVA EM LUGAR NENHUM - apenas mantém em memória!
    
    def get_cumulative_total(self, symbol: str) -> int:
        """Retorna o CVD acumulado total para um símbolo."""
        return self.cumulative_cvd_total.get(symbol, 0)
    
    def get_cvd_momentum(self, recent_trades: List[Trade], periods: List[int] = [5, 10, 20]) -> Dict[int, float]:
        """Calcula o momentum do CVD em diferentes períodos."""
        if not recent_trades:
            return {p: 0.0 for p in periods}
        
        momentum = {}
        current_cvd = self.calculate_cvd_for_trades(recent_trades)
        
        for period in periods:
            if len(self.cvd_history) >= period:
                try:
                    past_cvd = self.cvd_history[-period]
                    if past_cvd != 0:
                        momentum[period] = ((current_cvd - past_cvd) / abs(past_cvd)) * 100
                    else:
                        momentum[period] = 100.0 if current_cvd > 0 else -100.0 if current_cvd < 0 else 0.0
                except IndexError:
                    momentum[period] = 0.0
            else:
                momentum[period] = 0.0
        
        return momentum
    
    def reset_cumulative(self, symbol: str = None):
        """Reseta o CVD cumulativo para zero."""
        if symbol:
            if symbol in self.cumulative_cvd_total:
                logger.info(f"Resetando CVD cumulativo para {symbol}: era {self.cumulative_cvd_total[symbol]:+,}")
                self.cumulative_cvd_total[symbol] = 0
        else:
            # Reseta todos
            for sym in self.cumulative_cvd_total:
                logger.info(f"Resetando CVD cumulativo para {sym}: era {self.cumulative_cvd_total[sym]:+,}")
                self.cumulative_cvd_total[sym] = 0
    
    def get_statistics(self) -> Dict[str, Any]:
        """Retorna estatísticas sobre o CVD."""
        stats = {
            'cumulative_totals': self.cumulative_cvd_total.copy(),
            'history_size': len(self.cvd_history),
            'current_session': {
                'mean': np.mean(list(self.cvd_history)) if self.cvd_history else 0,
                'std': np.std(list(self.cvd_history)) if self.cvd_history else 0,
                'min': min(self.cvd_history) if self.cvd_history else 0,
                'max': max(self.cvd_history) if self.cvd_history else 0
            }
        }
        return stats