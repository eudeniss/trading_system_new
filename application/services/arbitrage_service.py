# application/services/arbitrage_service.py
from typing import Optional, Dict
from collections import deque
import numpy as np

from domain.entities.book import OrderBook
from config import settings

class ArbitrageService:
    """Serviço responsável pela lógica de cálculo de arbitragem."""

    def __init__(self):
        self.config = settings.ARBITRAGE_CONFIG
        self.spread_history = deque(maxlen=self.config.get('history_size', 100))
        self.point_value = self.config.get('point_value', 10.0)

    def calculate_opportunities(self, dol_book: OrderBook, wdo_book: OrderBook) -> Optional[Dict]:
        """Calcula as oportunidades de arbitragem com base nos livros de ofertas."""
        if not all([dol_book.bids, dol_book.asks, wdo_book.bids, wdo_book.asks]):
            return None

        dol_bid, dol_ask = dol_book.best_bid, dol_book.best_ask
        wdo_bid, wdo_ask = wdo_book.best_bid, wdo_book.best_ask

        # Oportunidade 1: Vender DOL (no bid) e Comprar WDO (no ask)
        spread_sell_dol = dol_bid - wdo_ask
        profit_sell_dol = spread_sell_dol * self.point_value

        # Oportunidade 2: Comprar DOL (no ask) e Vender WDO (no bid)
        spread_buy_dol = wdo_bid - dol_ask
        profit_buy_dol = spread_buy_dol * self.point_value
        
        best_spread = max(spread_sell_dol, spread_buy_dol)
        self.spread_history.append(best_spread)

        opportunities = {
            'sell_dol': {
                'spread': spread_sell_dol,
                'profit': profit_sell_dol,
                'action': 'VENDER DOL / COMPRAR WDO',
                'dol_price': dol_bid,
                'wdo_price': wdo_ask
            },
            'buy_dol': {
                'spread': spread_buy_dol,
                'profit': profit_buy_dol,
                'action': 'COMPRAR DOL / VENDER WDO',
                'dol_price': dol_ask,
                'wdo_price': wdo_bid
            }
        }
        
        return opportunities

    def get_spread_statistics(self) -> Optional[Dict]:
        """Calcula estatísticas sobre o histórico de spreads."""
        if len(self.spread_history) < 30:
            return None
            
        spreads = np.array(self.spread_history)
        return {
            'current': spreads[-1],
            'mean': np.mean(spreads),
            'std': np.std(spreads),
            'min': np.min(spreads),
            'max': np.max(spreads),
            'samples': len(spreads)
        }