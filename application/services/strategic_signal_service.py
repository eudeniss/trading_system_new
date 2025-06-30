# application/services/strategic_signal_service.py
"""
Serviço principal para sinais estratégicos.
Coordena detecção, filtros, confluência e ciclo de vida.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging
import uuid

from domain.entities.strategic_signal import (
    StrategicSignal, SetupType, SignalState, 
    ConflictStatus, EntryType
)
from domain.entities.signal import Signal, SignalSource, SignalLevel
from domain.entities.market_data import MarketData
from application.interfaces.system_event_bus import ISystemEventBus
from application.services.setup_lifecycle_manager import SetupLifecycleManager
from analyzers.confluence.context_filters import ContextFilters
from analyzers.regimes.market_regime_detector import MarketRegimeDetector
from analyzers.patterns.defensive_filter import DefensiveSignalFilter

logger = logging.getLogger(__name__)


class StrategicSignalService:
    """
    Serviço que gerencia todo o fluxo de sinais estratégicos.
    Responsabilidades:
    - Coordenar detecção de setups
    - Aplicar filtros de contexto
    - Verificar confluência DOL/WDO
    - Ajustar confiança
    - Gerenciar ciclo de vida
    """
    
    def __init__(
        self,
        event_bus: ISystemEventBus,
        lifecycle_manager: SetupLifecycleManager,
        regime_detector: MarketRegimeDetector
    ):
        self.event_bus = event_bus
        self.lifecycle_manager = lifecycle_manager
        self.regime_detector = regime_detector
        
        # Filtros e validadores
        self.context_filters = ContextFilters()
        self.defensive_filter = DefensiveSignalFilter()
        
        # Cache de sinais pendentes (aguardando confluência)
        self.pending_confluence: Dict[str, Dict] = {}  # symbol -> signal_data
        
        # Configurações de confluência
        self.confluence_config = {
            'timeout_seconds': 10,           # Tempo máximo para aguardar par
            'price_divergence_max': 0.0005,  # 0.05% máximo de divergência
            'cvd_divergence_max': 200,       # Divergência máxima de CVD
            'direction_must_match': True,    # Direções devem ser iguais
            'confidence_boost': 0.15,        # Boost por confluência perfeita
            'confidence_penalty': 0.20       # Penalidade por conflito
        }
        
        # Estatísticas
        self.stats = {
            'signals_created': 0,
            'signals_filtered': 0,
            'confluence_matches': 0,
            'confluence_conflicts': 0,
            'signals_executed': 0
        }
        
        # Callbacks de detecção
        self.setup_detectors = {}  # Será preenchido pelos detectores
        
        # Inscrever eventos
        self._subscribe_events()
        
        logger.info("StrategicSignalService inicializado")
    
    def _subscribe_events(self):
        """Inscreve aos eventos relevantes."""
        # Eventos de ciclo de vida
        self.event_bus.subscribe("STRATEGIC_SIGNAL_EXPIRED", self._handle_signal_expired)
        self.event_bus.subscribe("STRATEGIC_SIGNAL_STATE_CHANGED", self._handle_state_changed)
        
        # Eventos de mercado para atualizar contexto
        self.event_bus.subscribe("MARKET_DATA_UPDATED", self._handle_market_update)
    
    def create_strategic_signal(
        self,
        setup_type: SetupType,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        targets: List[float],
        confidence: float,
        confluence_factors: List[str],
        setup_details: Dict[str, Any],
        detected_by: str = "SYSTEM"
    ) -> Optional[StrategicSignal]:
        """
        Cria um novo sinal estratégico aplicando todos os filtros e validações.
        
        Returns:
            StrategicSignal se aprovado, None se filtrado
        """
        # Gera ID único
        signal_id = str(uuid.uuid4())
        
        # Calcula risk/reward
        risk = abs(entry_price - stop_loss)
        reward = abs(targets[0] - entry_price) if targets else risk
        risk_reward = reward / risk if risk > 0 else 0
        
        # Cria sinal inicial
        signal = StrategicSignal(
            id=signal_id,
            symbol=symbol,
            setup_type=setup_type,
            direction=direction,
            entry_price=entry_price,
            entry_type=self._determine_entry_type(setup_type),
            stop_loss=stop_loss,
            targets=targets,
            confidence=confidence,
            risk_reward=risk_reward,
            confluence_factors=confluence_factors,
            expiration_time=datetime.now() + timedelta(minutes=5),  # Temporário
            setup_details=setup_details,
            created_by=detected_by
        )
        
        # 1. Aplica filtros de contexto
        context = self._build_context(symbol)
        filter_results = self.context_filters.apply_all(signal, context)
        
        if not filter_results['passed']:
            logger.info(
                f"Sinal estratégico filtrado: {setup_type.value} {direction} @ {entry_price} - "
                f"Razão: {filter_results['recommendation']}"
            )
            self.stats['signals_filtered'] += 1
            
            # Emite aviso se foi por manipulação
            if 'MANIPULATION' in [w for w in filter_results['warnings'] if 'manipulação' in w.lower()]:
                self._emit_manipulation_warning(signal, filter_results)
            
            return None
        
        # 2. Ajusta confiança baseado nos filtros
        adjusted_confidence = confidence * filter_results['confidence_multiplier']
        signal.confidence = min(adjusted_confidence, 1.0)
        
        # 3. Aplica ajustes dos filtros
        self._apply_filter_adjustments(signal, filter_results['adjustments'])
        
        # 4. Verifica confluência DOL/WDO
        confluence_result = self._check_confluence(signal)
        signal.conflict_status = confluence_result['status']
        
        # Ajusta confiança baseado na confluência
        if confluence_result['status'] == ConflictStatus.NO_CONFLICT:
            signal.confidence = min(signal.confidence + self.confluence_config['confidence_boost'], 1.0)
            self.stats['confluence_matches'] += 1
        elif confluence_result['status'] == ConflictStatus.MAJOR_CONFLICT:
            signal.confidence *= (1 - self.confluence_config['confidence_penalty'])
            self.stats['confluence_conflicts'] += 1
            
            # Se conflito muito grande, pode filtrar
            if signal.confidence < 0.5:
                logger.info(f"Sinal filtrado por conflito DOL/WDO: confiança {signal.confidence:.2f}")
                return None
        
        # 5. Adiciona warnings dos filtros aos fatores de confluência
        if filter_results['warnings']:
            signal.confluence_factors.extend(
                [f"⚠️ {w}" for w in filter_results['warnings'][:2]]  # Max 2 warnings
            )
        
        # 6. Cria sinal no lifecycle manager
        self.lifecycle_manager.create_signal(signal)
        self.stats['signals_created'] += 1
        
        # 7. Emite evento de sinal estratégico
        self._emit_strategic_signal(signal)
        
        logger.info(
            f"Sinal estratégico criado: {signal.id[:8]} - "
            f"{setup_type.value} {direction} @ {entry_price} "
            f"(confiança: {signal.confidence:.0%})"
        )
        
        return signal
    
    def _determine_entry_type(self, setup_type: SetupType) -> EntryType:
        """Determina tipo de entrada baseado no setup."""
        if setup_type == SetupType.REVERSAL_VIOLENT:
            return EntryType.MARKET  # Entrada rápida
        elif setup_type in [SetupType.REVERSAL_SLOW, SetupType.PULLBACK_REJECTION]:
            return EntryType.LIMIT   # Entrada paciente
        elif setup_type == SetupType.BREAKOUT_IGNITION:
            return EntryType.STOP    # Entrada no rompimento
        else:
            return EntryType.ADAPTIVE  # Adaptativa ao contexto
    
    def _build_context(self, symbol: str) -> Dict[str, Any]:
        """Constrói contexto completo para os filtros."""
        # Pega dados mais recentes
        market_data = self.last_market_data if hasattr(self, 'last_market_data') else None
        
        # Regime atual
        regime_summary = self.regime_detector.get_regime_summary(symbol)
        
        # Padrões recentes (seria preenchido pelos detectores)
        recent_patterns = self.recent_patterns.get(symbol, []) if hasattr(self, 'recent_patterns') else []
        
        # Book atual
        book = None
        if market_data and symbol in market_data.data:
            book = market_data.data[symbol].book
        
        return {
            'market_data': market_data,
            'regime_info': {
                'regime': regime_summary['regime'],
                'confidence': regime_summary['confidence'],
                'volatility': regime_summary['metrics'].get('volatility'),
                'liquidity': regime_summary['metrics'].get('liquidity'),
                'time_in_current_regime': 120  # TODO: Implementar tracking real
            },
            'book': book,
            'recent_patterns': recent_patterns,
            'manipulation_alerts': []  # TODO: Conectar com defensive filter
        }
    
    def _check_confluence(self, signal: StrategicSignal) -> Dict[str, Any]:
        """
        Verifica confluência entre DOL e WDO.
        
        Returns:
            Dict com status e detalhes da confluência
        """
        other_symbol = 'DOL' if signal.symbol == 'WDO' else 'WDO'
        
        # Verifica se há sinal pendente do outro símbolo
        if other_symbol in self.pending_confluence:
            other_data = self.pending_confluence[other_symbol]
            other_signal = other_data['signal']
            
            # Verifica timeout
            if (datetime.now() - other_data['timestamp']).seconds > self.confluence_config['timeout_seconds']:
                # Expirou, remove
                del self.pending_confluence[other_symbol]
            else:
                # Analisa confluência
                confluence = self._analyze_confluence(signal, other_signal)
                
                # Remove do pending
                del self.pending_confluence[other_symbol]
                
                return confluence
        
        # Não há par, adiciona ao pending
        self.pending_confluence[signal.symbol] = {
            'signal': signal,
            'timestamp': datetime.now()
        }
        
        # Retorna sem conflito por enquanto
        return {
            'status': ConflictStatus.NO_CONFLICT,
            'details': {'waiting_pair': True}
        }
    
    def _analyze_confluence(
        self, 
        signal1: StrategicSignal, 
        signal2: StrategicSignal
    ) -> Dict[str, Any]:
        """Analisa confluência entre dois sinais de símbolos diferentes."""
        # 1. Direções devem ser iguais
        if signal1.direction != signal2.direction:
            return {
                'status': ConflictStatus.MAJOR_CONFLICT,
                'details': {
                    'reason': 'Direções opostas',
                    'signal1_direction': signal1.direction,
                    'signal2_direction': signal2.direction
                }
            }
        
        # 2. Verifica divergência de preços (normalizada)
        # WDO e DOL deveriam ter preços muito próximos
        price_diff = abs(signal1.entry_price - signal2.entry_price)
        avg_price = (signal1.entry_price + signal2.entry_price) / 2
        price_divergence = price_diff / avg_price if avg_price > 0 else 0
        
        if price_divergence > self.confluence_config['price_divergence_max']:
            return {
                'status': ConflictStatus.MINOR_CONFLICT,
                'details': {
                    'reason': 'Divergência de preços',
                    'divergence': f"{price_divergence:.2%}"
                }
            }
        
        # 3. Tipos de setup compatíveis
        compatible_setups = {
            SetupType.REVERSAL_SLOW: [SetupType.REVERSAL_SLOW, SetupType.DIVERGENCE_SETUP],
            SetupType.REVERSAL_VIOLENT: [SetupType.REVERSAL_VIOLENT, SetupType.REVERSAL_SLOW],
            SetupType.BREAKOUT_IGNITION: [SetupType.BREAKOUT_IGNITION, SetupType.PULLBACK_REJECTION],
            SetupType.PULLBACK_REJECTION: [SetupType.PULLBACK_REJECTION, SetupType.BREAKOUT_IGNITION],
            SetupType.DIVERGENCE_SETUP: [SetupType.DIVERGENCE_SETUP, SetupType.REVERSAL_SLOW]
        }
        
        if signal2.setup_type not in compatible_setups.get(signal1.setup_type, []):
            return {
                'status': ConflictStatus.MINOR_CONFLICT,
                'details': {
                    'reason': 'Setups incompatíveis',
                    'setup1': signal1.setup_type.value,
                    'setup2': signal2.setup_type.value
                }
            }
        
        # 4. Timing deve ser próximo
        time_diff = abs((signal1.timestamp - signal2.timestamp).total_seconds())
        if time_diff > 30:  # Mais de 30 segundos
            return {
                'status': ConflictStatus.MINOR_CONFLICT,
                'details': {
                    'reason': 'Sinais defasados no tempo',
                    'time_diff_seconds': time_diff
                }
            }
        
        # Passou em todos os testes - confluência perfeita!
        return {
            'status': ConflictStatus.NO_CONFLICT,
            'details': {
                'perfect_match': True,
                'price_alignment': f"{price_divergence:.3%}",
                'time_alignment': f"{time_diff:.0f}s"
            }
        }
    
    def _apply_filter_adjustments(self, signal: StrategicSignal, adjustments: Dict[str, Any]):
        """Aplica ajustes dos filtros ao sinal."""
        # Ajusta stops
        if 'tighten_stop' in adjustments:
            factor = adjustments['tighten_stop']
            if signal.direction == "COMPRA":
                signal.stop_loss = signal.entry_price - (signal.entry_price - signal.stop_loss) / factor
            else:
                signal.stop_loss = signal.entry_price + (signal.stop_loss - signal.entry_price) / factor
        
        elif 'widen_stop' in adjustments:
            factor = adjustments['widen_stop']
            if signal.direction == "COMPRA":
                signal.stop_loss = signal.entry_price - (signal.entry_price - signal.stop_loss) * factor
            else:
                signal.stop_loss = signal.entry_price + (signal.stop_loss - signal.entry_price) * factor
        
        # Ajusta tipo de entrada
        if 'use_limit_orders' in adjustments and signal.entry_type == EntryType.MARKET:
            signal.entry_type = EntryType.LIMIT
        
        # Adiciona notas aos detalhes
        if adjustments:
            signal.setup_details['filter_adjustments'] = adjustments
    
    def _emit_strategic_signal(self, signal: StrategicSignal):
        """Emite sinal estratégico como Signal normal para o display."""
        # Formata mensagem principal
        confidence_pct = int(signal.confidence * 100)
        risk_reward_str = f"{signal.risk_reward:.1f}:1"
        
        message = (
            f"🎯 SETUP {signal.setup_type.value} - {signal.direction} @ {signal.entry_price:.2f} "
            f"[{confidence_pct}%] RR: {risk_reward_str}"
        )
        
        # Cria Signal para o sistema
        display_signal = Signal(
            source=SignalSource.STRATEGIC,
            level=SignalLevel.ALERT if signal.confidence >= 0.7 else SignalLevel.WARNING,
            message=message,
            details={
                'strategic_signal_id': signal.id,
                'setup_type': signal.setup_type.value,
                'symbol': signal.symbol,
                'direction': signal.direction,
                'confidence': signal.confidence,
                'entry': signal.entry_price,
                'stop': signal.stop_loss,
                'targets': signal.targets
            }
        )
        
        self.event_bus.publish("SIGNAL_GENERATED", display_signal)
    
    def _emit_manipulation_warning(self, signal: StrategicSignal, filter_results: Dict):
        """Emite aviso de manipulação."""
        warnings = [w for w in filter_results['warnings'] if 'manipulação' in w.lower()]
        
        message = (
            f"⚠️ Setup {signal.setup_type.value} bloqueado - "
            f"Possível manipulação em {signal.symbol}: {warnings[0]}"
        )
        
        warning_signal = Signal(
            source=SignalSource.DIVERGENCE_WARNING,
            level=SignalLevel.WARNING,
            message=message,
            details={
                'blocked_setup': signal.setup_type.value,
                'symbol': signal.symbol,
                'warnings': warnings
            }
        )
        
        self.event_bus.publish("SIGNAL_GENERATED", warning_signal)
    
    def _handle_market_update(self, market_data: MarketData):
        """Atualiza dados de mercado para contexto."""
        self.last_market_data = market_data
        
        # Limpa sinais pendentes expirados
        now = datetime.now()
        expired_symbols = []
        
        for symbol, data in self.pending_confluence.items():
            if (now - data['timestamp']).seconds > self.confluence_config['timeout_seconds']:
                expired_symbols.append(symbol)
        
        for symbol in expired_symbols:
            del self.pending_confluence[symbol]
    
    def _handle_signal_expired(self, data: Dict):
        """Handler para sinais expirados."""
        signal = data['signal']
        logger.info(f"Sinal estratégico expirado: {signal.id[:8]}")
    
    def _handle_state_changed(self, data: Dict):
        """Handler para mudanças de estado."""
        if data['new_state'] == SignalState.EXECUTED:
            self.stats['signals_executed'] += 1
    
    def register_detector(self, setup_type: SetupType, detector_callback):
        """Registra um detector de setup."""
        self.setup_detectors[setup_type] = detector_callback
        logger.info(f"Detector registrado para {setup_type.value}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Retorna estatísticas do serviço."""
        return {
            **self.stats,
            'pending_confluence': len(self.pending_confluence),
            'active_signals': len(self.lifecycle_manager.get_active_signals()),
            'filters_enabled': len(self.context_filters.enabled_filters)
        }