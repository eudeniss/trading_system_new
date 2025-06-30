# application/services/setup_lifecycle_manager.py
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from collections import deque
import logging

from domain.entities.strategic_signal import StrategicSignal, SignalState, SetupType
from application.interfaces.system_event_bus import ISystemEventBus

logger = logging.getLogger(__name__)


class SetupLifecycleManager:
    """
    Gerencia o ciclo de vida dos sinais estratégicos.
    Responsável por:
    - Transições de estado
    - Expiração automática
    - Gestão de timers
    - Emissão de eventos
    """
    
    # application/services/setup_lifecycle_manager.py
    # Atualizar o __init__ (linhas 29-44):

    def __init__(self, event_bus: ISystemEventBus, config: Dict = None):
        self.event_bus = event_bus
        
        # Armazena sinais ativos por ID
        self.active_signals: Dict[str, StrategicSignal] = {}
        
        # Histórico de sinais (últimos 100)
        self.signal_history: deque[StrategicSignal] = deque(maxlen=100)
        
        # Carrega configurações de timeout
        from config import settings
        timeout_config = config.get('setup_timeouts') if config else settings.SETUP_TIMEOUTS_CONFIG
        
        # Configurações de timeout por tipo de setup (em segundos)
        self.timeout_config = {
            SetupType.REVERSAL_SLOW: timeout_config.get('reversal_slow', 600),
            SetupType.REVERSAL_VIOLENT: timeout_config.get('reversal_violent', 300),
            SetupType.BREAKOUT_IGNITION: timeout_config.get('breakout_ignition', 900),
            SetupType.PULLBACK_REJECTION: timeout_config.get('pullback_rejection', 600),
            SetupType.DIVERGENCE_SETUP: timeout_config.get('divergence_setup', 480)
        }
        
        logger.info(f"SetupLifecycleManager inicializado com timeouts: {self.timeout_config}")
    
        # Thread de monitoramento
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.lock = threading.RLock()
        
        # Callbacks para transições
        self.state_callbacks: Dict[SignalState, List[Callable]] = {
            state: [] for state in SignalState
        }
        
        # Estatísticas
        self.stats = {
            'total_created': 0,
            'total_executed': 0,
            'total_expired': 0,
            'total_stopped': 0,
            'total_targets_hit': 0
        }
        
        logger.info("SetupLifecycleManager inicializado")
    
    def start(self):
        """Inicia o gerenciador de ciclo de vida."""
        with self.lock:
            if not self.running:
                self.running = True
                self.monitor_thread = threading.Thread(
                    target=self._monitor_loop,
                    daemon=True,
                    name="SetupLifecycleMonitor"
                )
                self.monitor_thread.start()
                logger.info("Lifecycle manager iniciado")
    
    def stop(self):
        """Para o gerenciador."""
        with self.lock:
            self.running = False
        
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2)
        
        logger.info("Lifecycle manager parado")
    
    def create_signal(self, signal: StrategicSignal) -> bool:
        """
        Cria um novo sinal estratégico e inicia seu ciclo de vida.
        
        Returns:
            bool: True se criado com sucesso
        """
        with self.lock:
            # Define timeout baseado no tipo
            timeout_seconds = self.timeout_config.get(
                signal.setup_type, 
                300  # Default 5 minutos
            )
            
            # Configura expiração
            signal.expiration_time = datetime.now() + timedelta(seconds=timeout_seconds)
            signal.time_to_expiry_seconds = timeout_seconds
            
            # Inicia como PENDING
            signal.state = SignalState.PENDING
            
            # Adiciona ao tracking
            self.active_signals[signal.id] = signal
            self.stats['total_created'] += 1
            
            # Emite evento
            self.event_bus.publish("STRATEGIC_SIGNAL_CREATED", {
                'signal': signal,
                'timeout_seconds': timeout_seconds
            })
            
            logger.info(
                f"Sinal estratégico criado: {signal.id} - "
                f"{signal.setup_type.value} {signal.direction} @ {signal.entry_price}"
            )
            
            # Agenda ativação automática após validação inicial (2 segundos)
            threading.Timer(2.0, self._auto_activate_signal, args=[signal.id]).start()
            
            return True
    
    def _auto_activate_signal(self, signal_id: str):
        """Ativa automaticamente um sinal após validação inicial."""
        with self.lock:
            signal = self.active_signals.get(signal_id)
            if signal and signal.state == SignalState.PENDING:
                self.transition_state(signal_id, SignalState.ACTIVE)
    
    def transition_state(self, signal_id: str, new_state: SignalState, **kwargs) -> bool:
        """
        Transiciona um sinal para um novo estado.
        
        Args:
            signal_id: ID do sinal
            new_state: Novo estado
            **kwargs: Parâmetros adicionais (execution_price, exit_price, etc)
        
        Returns:
            bool: True se transição bem sucedida
        """
        with self.lock:
            signal = self.active_signals.get(signal_id)
            if not signal:
                logger.warning(f"Sinal {signal_id} não encontrado para transição")
                return False
            
            old_state = signal.state
            
            # Valida transição
            if not self._is_valid_transition(old_state, new_state):
                logger.warning(
                    f"Transição inválida: {old_state.value} -> {new_state.value}"
                )
                return False
            
            # Atualiza estado
            signal.update_state(new_state, **kwargs)
            
            # Emite evento de transição
            self.event_bus.publish("STRATEGIC_SIGNAL_STATE_CHANGED", {
                'signal_id': signal_id,
                'old_state': old_state,
                'new_state': new_state,
                'signal': signal
            })
            
            # Executa callbacks
            for callback in self.state_callbacks.get(new_state, []):
                try:
                    callback(signal)
                except Exception as e:
                    logger.error(f"Erro em callback de estado: {e}")
            
            # Atualiza estatísticas
            if new_state == SignalState.EXECUTED:
                self.stats['total_executed'] += 1
            elif new_state == SignalState.EXPIRED:
                self.stats['total_expired'] += 1
            elif new_state == SignalState.STOPPED:
                self.stats['total_stopped'] += 1
            elif new_state == SignalState.TARGET_HIT:
                self.stats['total_targets_hit'] += 1
            
            # Remove de ativos se estado final
            if new_state in [SignalState.EXPIRED, SignalState.STOPPED, SignalState.TARGET_HIT]:
                self._archive_signal(signal)
            
            logger.info(
                f"Sinal {signal_id} transicionou: "
                f"{old_state.value} -> {new_state.value}"
            )
            
            return True
    
    def _is_valid_transition(self, from_state: SignalState, to_state: SignalState) -> bool:
        """Valida se uma transição de estado é permitida."""
        valid_transitions = {
            SignalState.PENDING: [SignalState.ACTIVE, SignalState.EXPIRED],
            SignalState.ACTIVE: [SignalState.EXECUTED, SignalState.EXPIRED],
            SignalState.EXECUTED: [SignalState.STOPPED, SignalState.TARGET_HIT],
            SignalState.EXPIRED: [],  # Estado final
            SignalState.STOPPED: [],  # Estado final
            SignalState.TARGET_HIT: []  # Estado final
        }
        
        return to_state in valid_transitions.get(from_state, [])
    
    def _monitor_loop(self):
        """Loop principal de monitoramento de sinais."""
        logger.info("Monitor de ciclo de vida iniciado")
        
        while self.running:
            try:
                with self.lock:
                    # Copia IDs para evitar modificação durante iteração
                    signal_ids = list(self.active_signals.keys())
                
                for signal_id in signal_ids:
                    with self.lock:
                        signal = self.active_signals.get(signal_id)
                        if not signal:
                            continue
                        
                        # Verifica expiração
                        if signal.is_expired() and signal.state in [SignalState.PENDING, SignalState.ACTIVE]:
                            self.transition_state(signal_id, SignalState.EXPIRED)
                            
                            # Emite evento de expiração
                            self.event_bus.publish("STRATEGIC_SIGNAL_EXPIRED", {
                                'signal': signal,
                                'reason': 'timeout'
                            })
                
                # Dorme por 1 segundo
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Erro no monitor de ciclo de vida: {e}", exc_info=True)
                time.sleep(1)
    
    def _archive_signal(self, signal: StrategicSignal):
        """Move sinal para histórico."""
        self.signal_history.append(signal)
        del self.active_signals[signal.id]
        
        logger.debug(f"Sinal {signal.id} arquivado")
    
    def get_active_signals(self, symbol: Optional[str] = None) -> List[StrategicSignal]:
        """Retorna sinais ativos, opcionalmente filtrados por símbolo."""
        with self.lock:
            signals = list(self.active_signals.values())
            
            if symbol:
                signals = [s for s in signals if s.symbol == symbol]
            
            # Filtra apenas ACTIVE (não PENDING)
            return [s for s in signals if s.state == SignalState.ACTIVE]
    
    def get_signal_by_id(self, signal_id: str) -> Optional[StrategicSignal]:
        """Retorna um sinal específico por ID."""
        with self.lock:
            return self.active_signals.get(signal_id)
    
    def register_state_callback(self, state: SignalState, callback: Callable):
        """Registra callback para mudanças de estado."""
        self.state_callbacks[state].append(callback)
    
    def get_statistics(self) -> Dict[str, any]:
        """Retorna estatísticas do gerenciador."""
        with self.lock:
            active_by_state = {}
            for state in SignalState:
                count = sum(1 for s in self.active_signals.values() if s.state == state)
                active_by_state[state.value] = count
            
            return {
                'active_signals': len(self.active_signals),
                'active_by_state': active_by_state,
                'historical_stats': self.stats.copy(),
                'history_size': len(self.signal_history)
            }
    
    def cleanup_expired(self):
        """Limpa sinais expirados manualmente."""
        with self.lock:
            expired_ids = [
                sid for sid, signal in self.active_signals.items()
                if signal.is_expired() and signal.state in [SignalState.PENDING, SignalState.ACTIVE]
            ]
            
            for signal_id in expired_ids:
                self.transition_state(signal_id, SignalState.EXPIRED)
            
            return len(expired_ids)