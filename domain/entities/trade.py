# domain/entities/trade.py
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class TradeSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    UNKNOWN = "UNKNOWN"

class Trade(BaseModel):
    """Representa um único negócio executado no mercado."""
    symbol: str
    price: float = Field(gt=0)
    volume: int = Field(gt=0)
    side: TradeSide
    timestamp: datetime
    time_str: str
    
    class Config:
        frozen = True