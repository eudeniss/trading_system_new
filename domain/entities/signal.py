# domain/entities/signal.py
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from typing import Dict, Any

class SignalSource(str, Enum):
    ARBITRAGE = "ARBITRAGE"
    TAPE_READING = "TAPE_READING"
    CONFLUENCE = "CONFLUENCE"
    SYSTEM = "SYSTEM"
    MANIPULATION = "MANIPULATION"
    STRATEGIC = "STRATEGIC"  # NOVO: Para sinais estratégicos
    DIVERGENCE_WARNING = "DIVERGENCE_WARNING"  # NOVO: Para avisos de divergência

class SignalLevel(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ALERT = "ALERT"

class Signal(BaseModel):
    """Representa um sinal de trading gerado pelo sistema."""
    source: SignalSource
    level: SignalLevel
    message: str
    timestamp: datetime = Field(default_factory=datetime.now)
    details: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        frozen = True