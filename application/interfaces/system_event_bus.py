# application/interfaces/system_event_bus.py
from abc import ABC, abstractmethod
from typing import Callable, Any

class ISystemEventBus(ABC):
    """Interface para o barramento de eventos do sistema."""

    @abstractmethod
    def subscribe(self, event_type: str, handler: Callable):
        """Inscreve um handler para um tipo de evento."""

    @abstractmethod
    def publish(self, event_type: str, data: Any):
        """Publica um evento para todos os seus assinantes."""
