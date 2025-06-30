# orchestration/event_handlers.py - SPRINT 5 COMPLETO
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from application.interfaces.system_event_bus import ISystemEventBus
from application.interfaces.signal_repository import ISignalRepository
from application.services.arbitrage_service import ArbitrageService
from application.services.tape_reading_service import TapeReadingService
from application.services.strategic_signal_service import StrategicSignalService
from application.services.risk_management_service import RiskManagementService
from application.services.position_manager import PositionManager
from analyzers.regimes.market_regime_detector import MarketRegimeDetector
from domain.entities.market_data import MarketData
from domain.entities.trade import Trade
from domain.entities.signal import Signal, SignalSource, SignalLevel
from domain.entities.strategic_signal import SetupType
from presentation.display.monitor_app import TextualMonitorDisplay
from config import settings

# Importa os detectores
from analyzers.setups import (
    ReversalSetupDetector,
    ContinuationSetupDetector,
    DivergenceSetupDetector
)

logger = logging.getLogger(__name__)


class OrchestrationHandlers:
    """
    Sprint 5 - Versão completa com todos os handlers de eventos integrados.
    """
    def __init__(
        self,
        event_bus: ISystemEventBus,
        signal_repo: ISignalRepository,
        display: TextualMonitorDisplay,
        arbitrage_service: ArbitrageService,
        tape_reading_service: TapeReadingService,
        strategic_signal_service: StrategicSignalService,
        risk_management_service: RiskManagementService,
        market_regime_detector: MarketRegimeDetector,
        position_manager: Optional[PositionManager] = None,
        state_manager=None  # Ignorado - sem persistência
    ):
        self.event_bus = event_bus
        self.signal_repo = signal_repo
        self.display = display
        self.arbitrage_service = arbitrage_service
        self.tape_reading_service = tape_reading_service
        self.strategic_signal_service = strategic_signal_service
        self.risk_management_service = risk_management_service
        self.market_regime_detector = market_regime_detector
        self.position_manager = position_manager
        
        self.processed_trades: Dict[str, set] = {'WDO': set(), 'DOL': set()}
        
        # Inicializa detectores de setup
        self.setup_detectors = self._initialize_setup_detectors()
        
        # Registra detectores no serviço estratégico
        self._register_detectors()
        
        logger.info("OrchestrationHandlers Sprint 5 inicializado")

    def _initialize_setup_detectors(self) -> Dict[str, Any]:
        """Inicializa todos os detectores de setup."""
        return {
            'reversal': ReversalSetupDetector(),
            'continuation': ContinuationSetupDetector(),
            'divergence': DivergenceSetupDetector(event_bus=self.event_bus)  # Passar event_bus
        }
    
    def _register_detectors(self):
        """Registra detectores no serviço de sinais estratégicos."""
        self.strategic_signal_service.register_detector(
            SetupType.REVERSAL_SLOW, 
            self.setup_detectors['reversal']
        )
        self.strategic_signal_service.register_detector(
            SetupType.REVERSAL_VIOLENT, 
            self.setup_detectors['reversal']
        )
        self.strategic_signal_service.register_detector(
            SetupType.BREAKOUT_IGNITION,
            self.setup_detectors['continuation']
        )
        self.strategic_signal_service.register_detector(
            SetupType.PULLBACK_REJECTION,
            self.setup_detectors['continuation']
        )
        self.strategic_signal_service.register_detector(
            SetupType.DIVERGENCE_SETUP,
            self.setup_detectors['divergence']
        )

    def subscribe_to_events(self):
        """Inscreve handlers em TODOS os eventos do sistema."""
        # Eventos de mercado
        self.event_bus.subscribe("MARKET_DATA_UPDATED", self.handle_market_data)
        
        # Eventos de sinais
        self.event_bus.subscribe("SIGNAL_GENERATED", self.handle_signal_generated)
        self.event_bus.subscribe("SIGNAL_APPROVED", self.handle_signal_approved)
        self.event_bus.subscribe("SIGNAL_REJECTED", self.handle_signal_rejected)
        
        # Eventos de sinais estratégicos
        self.event_bus.subscribe("STRATEGIC_SIGNAL_CREATED", self.handle_strategic_signal_created)
        self.event_bus.subscribe("STRATEGIC_SIGNAL_STATE_CHANGED", self.handle_strategic_signal_state_changed)
        self.event_bus.subscribe("STRATEGIC_SIGNAL_EXPIRED", self.handle_strategic_signal_expired)
        
        # Eventos de warnings
        self.event_bus.subscribe("DIVERGENCE_WARNING", self.handle_divergence_warning)
        self.event_bus.subscribe("MANIPULATION_DETECTED", self.handle_manipulation_detected)
        
        # Eventos de posições (se position manager existir)
        if self.position_manager:
            self.event_bus.subscribe("POSITION_OPENED", self.handle_position_opened)
            self.event_bus.subscribe("POSITION_CLOSED", self.handle_position_closed)
        
        # Eventos de sistema
        self.event_bus.subscribe("DAILY_RESET", self.handle_daily_reset)
        self.event_bus.subscribe("RISK_OVERRIDE", self.handle_risk_override)
        
        logger.info("Todos os event handlers registrados")

    def handle_market_data(self, market_data: MarketData):
        """Handler principal que integra análise tática e estratégica."""
        # 1. Atualiza books no tape reading
        for symbol in ['WDO', 'DOL']:
            if symbol in market_data.data:
                self.tape_reading_service.update_book(symbol, market_data.data[symbol].book)
        
        # 2. Atualiza regime de mercado
        self.market_regime_detector.update(market_data)
        
        # 3. Processa trades para Tape Reading (sinais táticos)
        new_trades = self._get_new_trades(market_data)
        if new_trades:
            tape_signals = self.tape_reading_service.process_new_trades(new_trades)
            for signal in tape_signals:
                self._process_signal_with_risk(signal)
        
        # 4. Verifica setups estratégicos
        self._check_strategic_setups(market_data, new_trades)
        
        # 5. Analisa Arbitragem
        self._check_arbitrage(market_data)
        
        # 6. Atualiza Display com posições se disponível
        analysis_data = self._build_analysis_data()
        self.display.update(market_data, analysis_data)

    def _check_strategic_setups(self, market_data: MarketData, new_trades: List[Trade]):
        """Verifica setups estratégicos através dos detectores."""
        for symbol in ['WDO', 'DOL']:
            if symbol not in market_data.data:
                continue
            
            symbol_data = market_data.data[symbol]
            if not symbol_data.trades:
                continue
            
            market_context = self._build_market_context(symbol, market_data)
            symbol_trades = [t for t in new_trades if t.symbol == symbol]
            
            if not symbol_trades:
                continue
            
            # Processa todos os detectores da mesma forma
            for detector_name, detector in self.setup_detectors.items():
                try:
                    # TODOS os detectores agora retornam apenas List[StrategicSignal]
                    strategic_signals = detector.detect(
                        symbol,
                        symbol_data.trades,
                        symbol_data.book,
                        market_context
                    )
                    
                    # Processa cada sinal estratégico detectado
                    for signal in strategic_signals:
                        self.strategic_signal_service.create_strategic_signal(
                            setup_type=signal.setup_type,
                            symbol=signal.symbol,
                            direction=signal.direction,
                            entry_price=signal.entry_price,
                            stop_loss=signal.stop_loss,
                            targets=signal.targets,
                            confidence=signal.confidence,
                            confluence_factors=signal.confluence_factors,
                            setup_details=signal.setup_details,  # CORREÇÃO: era signal.metadata
                            detected_by=f"{detector_name}_detector"
                        )
                        
                except Exception as e:
                    logger.error(f"Erro no detector {detector_name} para {symbol}: {e}", exc_info=True)

    def _check_arbitrage(self, market_data: MarketData):
        """Verifica oportunidades de arbitragem."""
        dol_data = market_data.data.get('DOL')
        wdo_data = market_data.data.get('WDO')
        
        if dol_data and wdo_data:
            opportunities = self.arbitrage_service.calculate_opportunities(
                dol_data.book, 
                wdo_data.book
            )
            
            if opportunities:
                min_profit = settings.ARBITRAGE_CONFIG.get('min_profit', 15.0)
                best_opp = max(opportunities.values(), key=lambda x: x.get('profit', 0))
                if best_opp and best_opp['profit'] >= min_profit:
                    arb_signal = Signal(
                        source=SignalSource.ARBITRAGE,
                        level=SignalLevel.ALERT,
                        message=f"Arbitragem: {best_opp['action']} | R${best_opp['profit']:.0f}",
                        details=best_opp
                    )
                    self._process_signal_with_risk(arb_signal)

    def handle_signal_approved(self, data: Dict):
        """Handler para sinais aprovados pelo risk management."""
        signal = data.get('signal')
        assessment = data.get('assessment')
        
        if signal and assessment:
            logger.info(f"Sinal aprovado: {signal.message} - Qualidade: {assessment['quality']}")

    def handle_signal_rejected(self, data: Dict):
        """Handler para sinais rejeitados pelo risk management."""
        signal = data.get('signal')
        assessment = data.get('assessment')
        
        if signal and assessment:
            logger.debug(f"Sinal rejeitado: {assessment['reasons']}")

    def handle_strategic_signal_created(self, data: Dict):
        """Handler para quando um sinal estratégico é criado."""
        signal = data.get('signal')
        timeout_seconds = data.get('timeout_seconds', 300)
        
        if signal:
            # Adiciona ao display
            signal_dict = signal.to_display_dict()
            self.display.add_strategic_signal(signal_dict)
            
            # Log detalhado
            logger.info(
                f"Sinal estratégico criado: {signal.setup_type.value} "
                f"{signal.direction} @ {signal.entry_price:.2f} "
                f"(confiança: {signal.confidence:.0%}, timeout: {timeout_seconds}s)"
            )
            
            # Salva no repositório
            self.signal_repo.save_tape_reading_pattern({
                'type': 'STRATEGIC_SIGNAL',
                'signal_id': signal.id,
                'setup_type': signal.setup_type.value,
                'symbol': signal.symbol,
                'direction': signal.direction,
                'entry': signal.entry_price,
                'confidence': signal.confidence,
                'confluence_factors': signal.confluence_factors
            })

    def handle_strategic_signal_state_changed(self, data: Dict):
        """Handler para mudança de estado de sinal estratégico."""
        signal_id = data.get('signal_id')
        old_state = data.get('old_state')
        new_state = data.get('new_state')
        signal = data.get('signal')
        
        logger.info(f"Sinal {signal_id[:8]} mudou de {old_state.value} para {new_state.value}")
        
        # Atualiza display se necessário
        if signal:
            signal_dict = signal.to_display_dict()
            self.display.add_strategic_signal(signal_dict)

    def handle_strategic_signal_expired(self, data: Dict):
        """Handler específico para sinais estratégicos expirados."""
        signal = data.get('signal')
        reason = data.get('reason', 'timeout')
        
        if signal:
            logger.info(f"Sinal estratégico expirado: {signal.id[:8]} - Razão: {reason}")
            
            # Remove do display
            self.display.remove_strategic_signal(signal.id)
            
            # Notifica usuário se foi um bom setup que não foi aproveitado
            if signal.confidence > 0.8:
                missed_signal = Signal(
                    source=SignalSource.SYSTEM,
                    level=SignalLevel.WARNING,
                    message=f"⏰ Setup perdido: {signal.setup_type.value} {signal.direction} (conf: {signal.confidence:.0%})",
                    details={'missed_signal': signal.id}
                )
                self.display.add_signal(missed_signal)

    def handle_divergence_warning(self, warning_signal: Signal):
        """Handler específico para warnings de divergência."""
        self.display.add_signal(warning_signal)
        self.signal_repo.save(warning_signal)
        
        # Log adicional para divergências fortes
        details = warning_signal.details
        if details.get('divergence_event'):
            div_event = details['divergence_event']
            if div_event.strength > 0.8:
                logger.warning(f"Divergência FORTE detectada em {div_event.symbol}: {div_event.divergence_type}")

    def handle_position_opened(self, data: Dict):
        """Handler para quando uma posição é aberta."""
        position = data.get('position')
        data.get('signal')
        
        if position:
            logger.info(f"Posição aberta: {position.id} - {position.direction} {position.symbol}")
            
            # Notifica display
            position_signal = Signal(
                source=SignalSource.SYSTEM,
                level=SignalLevel.INFO,
                message=f"📈 Posição aberta: {position.direction} {position.symbol} @ {position.entry_price:.2f}",
                details={'position_id': position.id}
            )
            self.display.add_signal(position_signal)

    def handle_position_closed(self, data: Dict):
        """Handler para quando uma posição é fechada."""
        position = data.get('position')
        reason = data.get('reason')
        pnl = data.get('pnl', 0)
        
        if position:
            pnl_color = "green" if pnl > 0 else "red"
            
            # Notifica display
            close_signal = Signal(
                source=SignalSource.SYSTEM,
                level=SignalLevel.ALERT if abs(pnl) > 100 else SignalLevel.INFO,
                message=f"📊 Posição fechada: {reason} - PnL: [{pnl_color}]R${pnl:+.2f}[/{pnl_color}]",
                details={
                    'position_id': position.id,
                    'pnl': pnl,
                    'reason': reason
                }
            )
            self.display.add_signal(close_signal)

    def handle_daily_reset(self, data: Dict):
        """Handler para reset diário."""
        timestamp = data.get('timestamp')
        logger.info(f"Reset diário executado às {timestamp}")
        
        # Limpa trades processados
        self.processed_trades = {'WDO': set(), 'DOL': set()}
        
        # Notifica display
        reset_signal = Signal(
            source=SignalSource.SYSTEM,
            level=SignalLevel.INFO,
            message="🔄 Reset diário executado - métricas zeradas",
            details={'reset_time': timestamp}
        )
        self.display.add_signal(reset_signal)

    def handle_risk_override(self, data: Dict):
        """Handler para override manual de risco."""
        breaker = data.get('breaker')
        new_state = data.get('new_state')
        reason = data.get('reason', '')
        
        override_signal = Signal(
            source=SignalSource.SYSTEM,
            level=SignalLevel.ALERT,
            message=f"⚙️ Override de risco: {breaker} {'ativado' if new_state else 'desativado'} - {reason}",
            details=data
        )
        self.display.add_signal(override_signal)

    def handle_manipulation_detected(self, data: Dict):
        """Handler para detecção de manipulação."""
        symbol = data.get('symbol', 'UNKNOWN')
        risk_info = data.get('risk_info', {})
        action = risk_info.get('action_required', 'Possível manipulação')
        
        manipulation_signal = Signal(
            source=SignalSource.MANIPULATION,
            level=SignalLevel.ALERT,
            message=f"🚨 {symbol} - {action}",
            details=data
        )
        
        self.display.add_signal(manipulation_signal)
        self.signal_repo.save(manipulation_signal)

    def _build_market_context(self, symbol: str, market_data: MarketData) -> Dict[str, Any]:
        """Constrói contexto completo para os detectores."""
        tape_summary = self.tape_reading_service.get_market_summary(symbol)
        regime_summary = self.market_regime_detector.get_regime_summary(symbol)
        risk_status = self.risk_management_service.get_risk_status()
        
        context = {
            'cvd': {symbol: tape_summary.get('cvd', 0)},
            'cvd_roc': {symbol: tape_summary.get('cvd_roc', 0)},
            'cvd_total': tape_summary.get('cvd_total', 0),
            'regime': regime_summary['regime'],
            'volatility': regime_summary['metrics'].get('volatility'),
            'liquidity': regime_summary['metrics'].get('liquidity'),
            'risk_level': risk_status.get('risk_level', 'LOW'),
            'timestamp': datetime.now()
        }
        
        # Adiciona info de posições se disponível
        if self.position_manager:
            positions = self.position_manager.get_open_positions()
            context['open_positions'] = len(positions)
            context['position_exposure'] = sum(p.size for p in positions if p.symbol == symbol)
        
        return context

    def _build_analysis_data(self) -> Dict[str, Any]:
        """Constrói dados de análise incluindo posições."""
        analysis_data = {
            'arbitrage_stats': self.arbitrage_service.get_spread_statistics(),
            'tape_summaries': {
                'WDO': self.tape_reading_service.get_market_summary('WDO'),
                'DOL': self.tape_reading_service.get_market_summary('DOL')
            },
            'risk_status': self.risk_management_service.get_risk_status(),
            'strategic_signals': self.strategic_signal_service.lifecycle_manager.get_active_signals(),
            'regime_info': {
                'WDO': self.market_regime_detector.get_regime_summary('WDO'),
                'DOL': self.market_regime_detector.get_regime_summary('DOL')
            }
        }
        
        # Adiciona info de posições se disponível
        if self.position_manager:
            analysis_data['position_stats'] = self.position_manager.get_statistics()
            analysis_data['daily_summary'] = self.position_manager.get_daily_summary()
        
        return analysis_data

    def _get_new_trades(self, market_data: MarketData) -> List[Trade]:
        """Filtra trades novos."""
        new_trades = []
        for symbol, data in market_data.data.items():
            for trade in data.trades:
                trade_key = f"{trade.time_str}_{trade.price}_{trade.volume}"
                if trade_key not in self.processed_trades[symbol]:
                    self.processed_trades[symbol].add(trade_key)
                    new_trades.append(trade)
            
            # Limita tamanho do cache
            if len(self.processed_trades[symbol]) > 500:
                self.processed_trades[symbol] = set(list(self.processed_trades[symbol])[-250:])
        
        return new_trades

    def _process_signal_with_risk(self, signal: Signal):
        """Processa sinal através do risk management."""
        approved, assessment = self.risk_management_service.evaluate_signal(signal)
        if approved:
            self.event_bus.publish("SIGNAL_GENERATED", signal)

    def handle_signal_generated(self, signal: Signal):
        """Handler para sinais aprovados."""
        self.display.add_signal(signal)
        self.signal_repo.save(signal)