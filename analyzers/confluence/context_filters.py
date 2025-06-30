# analyzers/confluence/context_filters.py
"""
Filtros de contexto simplificados para validação de sinais estratégicos.
Versão otimizada removendo complexidade desnecessária.
"""

from typing import Dict, List, Any
from dataclasses import dataclass, field
from enum import Enum
import logging

from domain.entities.strategic_signal import StrategicSignal
from domain.entities.book import OrderBook

logger = logging.getLogger(__name__)


@dataclass
class FilterResult:
    """Resultado simplificado da aplicação de um filtro."""
    passed: bool
    score: float = 1.0
    reason: str = ""
    adjustments: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


class FilterType(str, Enum):
    """Tipos de filtro disponíveis."""
    BASIC = "BASIC"
    MANIPULATION = "MANIPULATION"
    VOLATILITY = "VOLATILITY"


class ContextFilters:
    """
    Versão simplificada dos filtros de contexto.
    Foca apenas em validações essenciais.
    """
    
    def __init__(self):
        self.enabled = True
        self.manipulation_threshold = 5.0  # Ratio bid/ask para considerar suspeito
        logger.info("ContextFilters simplificado inicializado")
    
    def apply_all(self, signal: StrategicSignal, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Aplica validações básicas ao sinal.
        
        Returns:
            Dict com resultados consolidados
        """
        if not self.enabled:
            return self._create_pass_result()
        
        results = {}
        warnings = []
        adjustments = {}
        
        # 1. Validação básica de sanidade
        basic_result = self._check_basic_validity(signal, context)
        results['basic'] = basic_result
        if not basic_result.passed:
            return self._create_fail_result(basic_result.reason, basic_result.warnings)
        
        # 2. Verificação simples de manipulação
        book = context.get('book')
        if book:
            manip_result = self._check_manipulation(book, signal)
            results['manipulation'] = manip_result
            warnings.extend(manip_result.warnings)
            adjustments.update(manip_result.adjustments)
        
        # 3. Ajuste por volatilidade (se disponível)
        volatility = context.get('volatility')
        if volatility:
            vol_result = self._adjust_for_volatility(signal, volatility)
            results['volatility'] = vol_result
            adjustments.update(vol_result.adjustments)
        
        # Calcula score final
        total_score = sum(r.score for r in results.values()) / len(results)
        passed = total_score >= 0.5 and not any(r.score < 0.3 for r in results.values())
        
        # Calcula multiplicador de confiança
        confidence_multiplier = min(max(total_score, 0.5), 1.0)
        
        return {
            'passed': passed,
            'final_score': total_score,
            'confidence_multiplier': confidence_multiplier,
            'filter_results': results,
            'adjustments': adjustments,
            'warnings': warnings[:3],  # Máximo 3 warnings
            'recommendation': self._get_recommendation(passed, total_score)
        }
    
    def _check_basic_validity(self, signal: StrategicSignal, context: Dict[str, Any]) -> FilterResult:
        """Verifica validade básica do sinal."""
        # Verifica se preços fazem sentido
        if signal.stop_loss <= 0 or signal.entry_price <= 0:
            return FilterResult(
                passed=False,
                score=0.0,
                reason="Preços inválidos",
                warnings=["Preço de entrada ou stop inválido"]
            )
        
        # Verifica risk/reward mínimo
        if signal.risk_reward < 1.0:
            return FilterResult(
                passed=True,
                score=0.6,
                reason="Risk/reward baixo",
                warnings=["R/R abaixo de 1:1"]
            )
        
        return FilterResult(passed=True, score=1.0, reason="Validações básicas OK")
    
    def _check_manipulation(self, book: OrderBook, signal: StrategicSignal) -> FilterResult:
        """Verificação simplificada de manipulação."""
        if not book.bids or not book.asks:
            return FilterResult(passed=True, score=1.0)
        
        # Calcula desbalanceamento do book
        bid_volume = sum(level.volume for level in book.bids[:5])
        ask_volume = sum(level.volume for level in book.asks[:5])
        
        if bid_volume == 0 or ask_volume == 0:
            return FilterResult(passed=True, score=1.0)
        
        imbalance_ratio = max(bid_volume / ask_volume, ask_volume / bid_volume)
        
        if imbalance_ratio > self.manipulation_threshold:
            heavier_side = "compra" if bid_volume > ask_volume else "venda"
            return FilterResult(
                passed=True,
                score=0.5,
                warnings=[f"Book desbalanceado na {heavier_side} ({imbalance_ratio:.1f}x)"],
                adjustments={'reduce_size': 0.7, 'use_limit_orders': True}
            )
        
        return FilterResult(passed=True, score=1.0)
    
    def _adjust_for_volatility(self, signal: StrategicSignal, volatility: str) -> FilterResult:
        """Ajusta baseado na volatilidade."""
        adjustments = {}
        
        if volatility == "HIGH":
            adjustments['widen_stop'] = 1.3
            adjustments['reduce_size'] = 0.8
        elif volatility == "EXTREME":
            adjustments['widen_stop'] = 1.5
            adjustments['reduce_size'] = 0.6
        elif volatility == "LOW":
            adjustments['tighten_stop'] = 0.8
        
        return FilterResult(
            passed=True,
            score=0.8 if volatility in ["HIGH", "EXTREME"] else 1.0,
            adjustments=adjustments
        )
    
    def _get_recommendation(self, passed: bool, score: float) -> str:
        """Gera recomendação simples."""
        if not passed:
            return "SKIP - Filtros não aprovaram"
        elif score >= 0.8:
            return "PROCEED - Contexto favorável"
        elif score >= 0.6:
            return "PROCEED_CAUTIOUS - Contexto moderado"
        else:
            return "WAIT - Aguarde melhor contexto"
    
    def _create_pass_result(self) -> Dict[str, Any]:
        """Resultado padrão quando filtros estão desabilitados."""
        return {
            'passed': True,
            'final_score': 1.0,
            'confidence_multiplier': 1.0,
            'filter_results': {},
            'adjustments': {},
            'warnings': [],
            'recommendation': 'PROCEED - Filtros desabilitados'
        }
    
    def _create_fail_result(self, reason: str, warnings: List[str]) -> Dict[str, Any]:
        """Resultado quando falha validação básica."""
        return {
            'passed': False,
            'final_score': 0.0,
            'confidence_multiplier': 0.5,
            'filter_results': {},
            'adjustments': {},
            'warnings': warnings,
            'recommendation': f'SKIP - {reason}'
        }
    
    def enable(self):
        """Habilita os filtros."""
        self.enabled = True
        logger.info("Filtros de contexto habilitados")
    
    def disable(self):
        """Desabilita os filtros."""
        self.enabled = False
        logger.info("Filtros de contexto desabilitados")