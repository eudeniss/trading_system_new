# application/services/setup_detector.py
"""
Define a interface (classe base abstrata) para todos os detectores de setup.

Este módulo é fundamental para a arquitetura de detecção, garantindo que
diferentes tipos de detectores (reversão, continuação, etc.) possam ser
tratados de forma uniforme pelo resto do sistema, como pelo 
StrategicSignalService e pelo SetupDetectorRegistry.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional

# Importa as entidades do domínio para definir as assinaturas dos métodos
from domain.entities.trade import Trade
from domain.entities.book import OrderBook
from domain.entities.strategic_signal import StrategicSignal, SetupType


class SetupDetector(ABC):
    """
    Classe base abstrata para todos os detectores de setup.

    Define um contrato que força todas as classes filhas (detectores concretos)
    a implementarem os métodos essenciais, garantindo a interoperabilidade
    e a consistência em todo o sistema.
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        Inicializa o detector com uma configuração.

        Args:
            config (Dict[str, Any], optional): Dicionário de configuração para 
                                             o detector específico (ex: thresholds, timers).
                                             Defaults to None.
        """
        self.config = config or {}

    @abstractmethod
    def get_supported_types(self) -> List[SetupType]:
        """
        Método abstrato obrigatório.

        Deve retornar uma lista dos tipos de setup (do Enum SetupType)
        que este detector é capaz de identificar. O SetupDetectorRegistry
        usa esta informação para mapear os tipos aos detectores corretos.

        Returns:
            List[SetupType]: Uma lista de enums SetupType suportados.
        """

    @abstractmethod
    def detect(self, 
               symbol: str,
               trades: List[Trade],
               book: Optional[OrderBook],
               market_context: Dict[str, Any]) -> List[StrategicSignal]:
        """
        Método abstrato obrigatório para executar a lógica de detecção.

        Este método processa os dados de mercado e retorna uma lista de
        sinais estratégicos encontrados. Deve retornar uma lista vazia
        se nenhum sinal for detectado.

        Args:
            symbol (str): O símbolo do ativo sendo analisado (ex: "WDO").
            trades (List[Trade]): Uma lista de trades recentes para análise.
            book (Optional[OrderBook]): O estado atual do order book.
            market_context (Dict[str, Any]): Um dicionário com dados de contexto 
                                             adicionais, como CVD, indicadores
                                             de volatilidade, etc.

        Returns:
            List[StrategicSignal]: Uma lista de objetos StrategicSignal encontrados.
        """
