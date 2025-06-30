# domain/entities/book.py
from pydantic import BaseModel, Field
from typing import List

class BookLevel(BaseModel):
    """Representa um nível de preço no livro de ofertas."""
    price: float = Field(gt=0)
    volume: int = Field(ge=0)
    
    class Config:
        frozen = True

class OrderBook(BaseModel):
    """Representa o livro de ofertas de um ativo."""
    bids: List[BookLevel] = Field(default_factory=list)
    asks: List[BookLevel] = Field(default_factory=list)

    @property
    def best_bid(self) -> float:
        return self.bids[0].price if self.bids else 0.0

    @property
    def best_ask(self) -> float:
        return self.asks[0].price if self.asks else 0.0
    
    class Config:
        frozen = True