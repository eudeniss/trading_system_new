# infrastructure/setup_detector_registry.py
"""
Registry centralizado para detectores de setup estratégico.
Facilita a manutenção e permite configuração dinâmica.
"""

from typing import Dict, Any, Optional
from abc import ABC, abstractmethod
import logging

from domain.entities.strategic_signal import SetupType
from domain.entities.trade import Trade
from domain.entities.book import OrderBook

logger = logging.getLogger(__name__)


class BaseSetupDetector(ABC):
    """Interface base para todos os detectores de setup."""
    
    @abstractmethod
    def detect(self, symbol: str, trades: list[Trade], 
              book: Optional[OrderBook], market_context: Dict) -> list:
        """Detecta setups nos dados fornecidos."""
    
    @abstractmethod
    def get_supported_types(self) -> list[SetupType]:
        """Retorna tipos de setup suportados por este detector."""


class SetupDetectorRegistry:
    """
    Registry para gerenciar detectores de setup estratégico.
    Permite registro dinâmico e configuração centralizada.
    """
    
    def __init__(self):
        self.detectors: Dict[SetupType, BaseSetupDetector] = {}
        self.detector_configs: Dict[str, Dict[str, Any]] = {}
        logger.info("SetupDetectorRegistry inicializado")
    
    def register_detector(self, detector: BaseSetupDetector, config: Optional[Dict] = None):
        """
        Registra um detector para seus tipos de setup suportados.
        
        Args:
            detector: Instância do detector
            config: Configuração opcional específica do detector
        """
        detector_name = detector.__class__.__name__
        
        # Salva configuração se fornecida
        if config:
            self.detector_configs[detector_name] = config
        
        # Registra para cada tipo suportado
        for setup_type in detector.get_supported_types():
            if setup_type in self.detectors:
                logger.warning(
                    f"Sobrescrevendo detector para {setup_type.value}. "
                    f"Anterior: {self.detectors[setup_type].__class__.__name__}, "
                    f"Novo: {detector_name}"
                )
            
            self.detectors[setup_type] = detector
            logger.info(f"Detector {detector_name} registrado para {setup_type.value}")
    
    def get_detector(self, setup_type: SetupType) -> Optional[BaseSetupDetector]:
        """Retorna o detector para um tipo de setup específico."""
        return self.detectors.get(setup_type)
    
    def get_all_detectors(self) -> Dict[SetupType, BaseSetupDetector]:
        """Retorna todos os detectores registrados."""
        return self.detectors.copy()
    
    def get_unique_detectors(self) -> list[BaseSetupDetector]:
        """Retorna lista de detectores únicos (sem duplicatas)."""
        seen = set()
        unique = []
        
        for detector in self.detectors.values():
            detector_id = id(detector)
            if detector_id not in seen:
                seen.add(detector_id)
                unique.append(detector)
        
        return unique
    
    def get_config(self, detector_name: str) -> Optional[Dict[str, Any]]:
        """Retorna configuração de um detector específico."""
        return self.detector_configs.get(detector_name)
    
    def update_config(self, detector_name: str, config: Dict[str, Any]):
        """Atualiza configuração de um detector."""
        self.detector_configs[detector_name] = config
        logger.info(f"Configuração atualizada para {detector_name}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Retorna estatísticas do registry."""
        detector_counts = {}
        for detector in self.detectors.values():
            name = detector.__class__.__name__
            detector_counts[name] = detector_counts.get(name, 0) + 1
        
        return {
            'total_mappings': len(self.detectors),
            'unique_detectors': len(self.get_unique_detectors()),
            'detector_types': list(detector_counts.keys()),
            'mappings_per_detector': detector_counts,
            'configured_detectors': list(self.detector_configs.keys())
        }


def create_default_registry() -> SetupDetectorRegistry:
    """
    Cria e configura o registry padrão com todos os detectores.
    """
    from analyzers.setups import (
        ReversalSetupDetector,
        ContinuationSetupDetector,
        DivergenceSetupDetector
    )
    
    registry = SetupDetectorRegistry()
    
    # Registra detectores com configurações padrão
    registry.register_detector(
        ReversalSetupDetector(),
        config={
            'slow_absorption_threshold': 300,
            'slow_cvd_reversal_threshold': 100,
            'violent_spike_multiplier': 3.0
        }
    )
    
    registry.register_detector(
        ContinuationSetupDetector(),
        config={
            'breakout_momentum_threshold': 100,
            'pullback_depth_range': (0.3, 0.6)
        }
    )
    
    registry.register_detector(
        DivergenceSetupDetector(),
        config={
            'min_bars_for_divergence': 20,
            'setup_strength_threshold': 0.7
        }
    )
    
    logger.info(f"Registry padrão criado: {registry.get_statistics()}")
    
    return registry