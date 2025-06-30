# infrastructure/event_bus/local_event_bus.py
import logging
from collections import defaultdict
from typing import Callable, Any, List
from application.interfaces.system_event_bus import ISystemEventBus

logger = logging.getLogger(__name__)

class LocalEventBus(ISystemEventBus):
    """Implementação simples de um barramento de eventos em memória."""

    def __init__(self):
        self.handlers: defaultdict[str, List[Callable]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Callable):
        """Inscreve um handler para um tipo de evento."""
        self.handlers[event_type].append(handler)
        logger.debug(f"Handler {handler.__name__} inscrito para o evento '{event_type}'.")

    def publish(self, event_type: str, data: Any):
        """Publica um evento, acionando todos os handlers inscritos."""
        if event_type in self.handlers:
            logger.debug(f"Publicando evento '{event_type}' com dados: {data}")
            for handler in self.handlers[event_type]:
                try:
                    handler(data)
                except Exception as e:
                    logger.error(
                        f"Erro ao executar o handler {handler.__name__} para o evento '{event_type}': {e}",
                        exc_info=True
                    )