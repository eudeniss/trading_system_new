# analyzers/setups/__init__.py
"""
Módulo de detectores de setup estratégicos.
Identifica padrões de entrada com alta probabilidade.
"""

from .reversal_setup_detector import ReversalSetupDetector
from .continuation_setup_detector import ContinuationSetupDetector
from .divergence_setup_detector import DivergenceSetupDetector

__all__ = [
    'ReversalSetupDetector',
    'ContinuationSetupDetector', 
    'DivergenceSetupDetector'
]