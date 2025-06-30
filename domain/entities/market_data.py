# domain/entities/market_data.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Dict
from .trade import Trade
from .book import OrderBook

class MarketSymbolData(BaseModel):
    """Agrega todos os dados de mercado para um único símbolo."""
    trades: List[Trade] = Field(default_factory=list)
    book: OrderBook = Field(default_factory=OrderBook)
    last_price: float = 0.0
    total_volume: int = 0
    
    class Config:
        frozen = True

class MarketData(BaseModel):
    """Snapshot completo dos dados de mercado para todos os ativos."""
    timestamp: datetime
    data: Dict[str, MarketSymbolData] = Field(default_factory=dict)
    
    class Config:
        frozen = True