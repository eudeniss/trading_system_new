# application/services/position_manager.py
"""
Gerenciador de posições que reage a sinais estratégicos e warnings.
Responsável por rastrear posições abertas e gerenciar stops/alvos.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, field
import logging
import threading
from collections import deque

from domain.entities.strategic_signal import StrategicSignal, SignalState, SetupType
from domain.entities.signal import Signal
from application.interfaces.system_event_bus import ISystemEventBus

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Representa uma posição aberta."""
    id: str
    signal_id: str
    symbol: str
    direction: str
    entry_price: float
    entry_time: datetime
    size: int
    stop_loss: float
    targets: List[float]
    current_price: float = 0.0
    pnl: float = 0.0
    pnl_points: float = 0.0
    status: str = "OPEN"  # OPEN, CLOSED, STOPPED
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    exit_reason: Optional[str] = None
    max_profit: float = 0.0
    max_loss: float = 0.0
    warnings_received: List[str] = field(default_factory=list)
    
    def update_price(self, price: float):
        """Atualiza preço atual e calcula P&L."""
        self.current_price = price
        
        if self.direction == "COMPRA":
            self.pnl_points = price - self.entry_price
        else:
            self.pnl_points = self.entry_price - price
        
        self.pnl = self.pnl_points * self.size * 10  # Point value
        
        # Atualiza máximos
        self.max_profit = max(self.max_profit, self.pnl)
        self.max_loss = min(self.max_loss, self.pnl)
    
    def should_stop(self) -> bool:
        """Verifica se deve ser stopada."""
        if self.direction == "COMPRA":
            return self.current_price <= self.stop_loss
        else:
            return self.current_price >= self.stop_loss
    
    def check_targets(self) -> Optional[int]:
        """Verifica se algum alvo foi atingido. Retorna índice do alvo ou None."""
        for i, target in enumerate(self.targets):
            if self.direction == "COMPRA":
                if self.current_price >= target:
                    return i
            else:
                if self.current_price <= target:
                    return i
        return None


class PositionManager:
    """
    Gerencia posições abertas e reage a eventos do sistema.
    """
    
    def __init__(self, event_bus: ISystemEventBus, config: Optional[Dict] = None):
        self.event_bus = event_bus
        self.config = config or {}
        
        # Configurações
        self.max_positions = self.config.get('max_positions', 3)
        self.default_size = self.config.get('default_size', 1)
        self.auto_manage = self.config.get('auto_manage', True)
        self.trailing_stop_enabled = self.config.get('trailing_stop_enabled', False)
        self.trailing_stop_distance = self.config.get('trailing_stop_distance', 10.0)
        
        # Estado interno
        self.positions: Dict[str, Position] = {}  # position_id -> Position
        self.signal_to_position: Dict[str, str] = {}  # signal_id -> position_id
        self.closed_positions: deque[Position] = deque(maxlen=100)
        
        # Estatísticas
        self.stats = {
            'total_opened': 0,
            'total_closed': 0,
            'total_stopped': 0,
            'total_target_hit': 0,
            'total_pnl': 0.0,
            'win_count': 0,
            'loss_count': 0
        }
        
        # Thread safety
        self.lock = threading.RLock()
        
        # Inscrever aos eventos
        self._subscribe_events()
        
        logger.info("PositionManager inicializado")
    
    def _subscribe_events(self):
        """Inscreve aos eventos relevantes."""
        # Eventos de sinais estratégicos
        self.event_bus.subscribe("STRATEGIC_SIGNAL_STATE_CHANGED", self._handle_signal_state_changed)
        self.event_bus.subscribe("STRATEGIC_SIGNAL_EXPIRED", self._handle_signal_expired)
        
        # Eventos de warning
        self.event_bus.subscribe("DIVERGENCE_WARNING", self._handle_divergence_warning)
        self.event_bus.subscribe("MANIPULATION_DETECTED", self._handle_manipulation_warning)
        
        # Eventos de mercado
        self.event_bus.subscribe("MARKET_DATA_UPDATED", self._handle_market_update)
        
        # Eventos de risco
        self.event_bus.subscribe("RISK_OVERRIDE", self._handle_risk_override)
    
    def _handle_signal_state_changed(self, data: Dict):
        """Handler para mudança de estado de sinal estratégico."""
        signal_id = data.get('signal_id')
        new_state = data.get('new_state')
        signal = data.get('signal')
        
        if not signal:
            return
        
        with self.lock:
            # Se sinal foi executado, cria posição
            if new_state == SignalState.EXECUTED and self.can_open_position():
                self._open_position(signal)
            
            # Se sinal tem posição e foi stopado/target hit
            elif signal_id in self.signal_to_position:
                position_id = self.signal_to_position[signal_id]
                if position_id in self.positions:
                    position = self.positions[position_id]
                    
                    if new_state == SignalState.STOPPED:
                        self._close_position(position, "SIGNAL_STOPPED", signal.exit_price)
                    elif new_state == SignalState.TARGET_HIT:
                        self._close_position(position, "TARGET_HIT", signal.exit_price)
    
    def _handle_signal_expired(self, data: Dict):
        """Handler para sinal expirado."""
        signal = data.get('signal')
        if not signal:
            return
        
        # Se tinha posição aberta, pode fechar ou manter
        with self.lock:
            if signal.id in self.signal_to_position:
                position_id = self.signal_to_position[signal.id]
                if position_id in self.positions:
                    position = self.positions[position_id]
                    
                    # Se posição está no prejuízo, fecha
                    if position.pnl < 0:
                        logger.warning(f"Fechando posição {position_id} - sinal expirou com prejuízo")
                        self._close_position(position, "SIGNAL_EXPIRED", position.current_price)
    
    def _handle_divergence_warning(self, signal: Signal):
        """Handler para warning de divergência."""
        details = signal.details
        divergence_event = details.get('divergence_event')
        
        if not divergence_event:
            return
        
        symbol = divergence_event.symbol
        direction = "VENDA" if divergence_event.direction == "BULLISH" else "COMPRA"
        
        with self.lock:
            # Alerta posições contrárias à divergência
            for position in self.positions.values():
                if position.symbol == symbol and position.direction == direction:
                    position.warnings_received.append(f"DIVERGENCE_{divergence_event.direction}")
                    
                    # Se já tem múltiplos warnings, considera fechar
                    if len(position.warnings_received) >= 2 and self.auto_manage:
                        logger.warning(f"Posição {position.id} com múltiplos warnings - fechando")
                        self._close_position(position, "MULTIPLE_WARNINGS", position.current_price)
    
    def _handle_manipulation_warning(self, data: Dict):
        """Handler para warning de manipulação."""
        symbol = data.get('symbol')
        data.get('risk_info', {})
        
        if not symbol:
            return
        
        with self.lock:
            # Alerta todas as posições do símbolo
            for position in self.positions.values():
                if position.symbol == symbol:
                    position.warnings_received.append("MANIPULATION_RISK")
                    
                    # Se manipulação detectada, reduz stops
                    if self.auto_manage:
                        self._tighten_stop(position, factor=0.5)
                        logger.warning(f"Stop apertado para posição {position.id} devido a risco de manipulação")
    
    def _handle_market_update(self, market_data):
        """Atualiza preços e verifica stops/alvos."""
        with self.lock:
            for symbol_data in market_data.data.values():
                if not symbol_data.trades:
                    continue
                
                symbol = symbol_data.trades[0].symbol
                current_price = symbol_data.trades[-1].price
                
                # Atualiza todas as posições do símbolo
                positions_to_check = [p for p in self.positions.values() if p.symbol == symbol]
                
                for position in positions_to_check:
                    position.update_price(current_price)
                    
                    # Verifica stop loss
                    if position.should_stop():
                        self._close_position(position, "STOP_LOSS", current_price)
                        continue
                    
                    # Verifica targets
                    target_hit = position.check_targets()
                    if target_hit is not None:
                        self._close_position(position, f"TARGET_{target_hit + 1}", current_price)
                        continue
                    
                    # Trailing stop (se habilitado)
                    if self.trailing_stop_enabled and position.pnl_points > self.trailing_stop_distance:
                        self._update_trailing_stop(position)
    
    def _handle_risk_override(self, data: Dict):
        """Handler para override de risco."""
        breaker = data.get('breaker')
        new_state = data.get('new_state')
        
        # Se circuit breaker de emergência ativado, fecha todas as posições
        if breaker == 'emergency' and new_state:
            logger.warning("Circuit breaker de emergência - fechando todas as posições")
            with self.lock:
                self.close_all_positions("EMERGENCY_STOP")
    
    def _open_position(self, signal: StrategicSignal) -> Optional[Position]:
        """Abre uma nova posição baseada em sinal estratégico."""
        if not self.can_open_position():
            logger.warning(f"Não pode abrir posição - limite atingido ({self.max_positions})")
            return None
        
        position_id = f"POS_{signal.symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Define tamanho baseado no tipo de setup
        size = self._calculate_position_size(signal)
        
        position = Position(
            id=position_id,
            signal_id=signal.id,
            symbol=signal.symbol,
            direction=signal.direction,
            entry_price=signal.execution_price or signal.entry_price,
            entry_time=datetime.now(),
            size=size,
            stop_loss=signal.stop_loss,
            targets=signal.targets,
            current_price=signal.execution_price or signal.entry_price
        )
        
        self.positions[position_id] = position
        self.signal_to_position[signal.id] = position_id
        self.stats['total_opened'] += 1
        
        # Emite evento
        self.event_bus.publish("POSITION_OPENED", {
            'position': position,
            'signal': signal
        })
        
        logger.info(
            f"Posição aberta: {position_id} - "
            f"{position.direction} {position.symbol} @ {position.entry_price}"
        )
        
        return position
    
    def _close_position(self, position: Position, reason: str, exit_price: float):
        """Fecha uma posição."""
        position.exit_price = exit_price
        position.exit_time = datetime.now()
        position.exit_reason = reason
        position.status = "STOPPED" if reason == "STOP_LOSS" else "CLOSED"
        position.update_price(exit_price)
        
        # Remove do tracking ativo
        del self.positions[position.id]
        if position.signal_id in self.signal_to_position:
            del self.signal_to_position[position.signal_id]
        
        # Adiciona ao histórico
        self.closed_positions.append(position)
        
        # Atualiza estatísticas
        self.stats['total_closed'] += 1
        self.stats['total_pnl'] += position.pnl
        
        if reason == "STOP_LOSS":
            self.stats['total_stopped'] += 1
        elif reason.startswith("TARGET"):
            self.stats['total_target_hit'] += 1
        
        if position.pnl > 0:
            self.stats['win_count'] += 1
        else:
            self.stats['loss_count'] += 1
        
        # Emite evento
        self.event_bus.publish("POSITION_CLOSED", {
            'position': position,
            'reason': reason,
            'pnl': position.pnl
        })
        
        logger.info(
            f"Posição fechada: {position.id} - "
            f"Motivo: {reason} - PnL: R${position.pnl:+.2f}"
        )
    
    def _calculate_position_size(self, signal: StrategicSignal) -> int:
        """Calcula tamanho da posição baseado no sinal."""
        base_size = self.default_size
        
        # Ajusta por confiança
        if signal.confidence > 0.8:
            size = int(base_size * 1.5)
        elif signal.confidence < 0.6:
            size = max(1, int(base_size * 0.7))
        else:
            size = base_size
        
        # Ajusta por tipo de setup
        if signal.setup_type == SetupType.REVERSAL_VIOLENT:
            size = max(1, int(size * 0.8))  # Reduz em reversões violentas
        elif signal.setup_type == SetupType.BREAKOUT_IGNITION:
            size = int(size * 1.2)  # Aumenta em breakouts
        
        return size
    
    def _tighten_stop(self, position: Position, factor: float = 0.7):
        """Aperta o stop loss de uma posição."""
        if position.direction == "COMPRA":
            new_stop = position.entry_price - (position.entry_price - position.stop_loss) * factor
            position.stop_loss = max(position.stop_loss, new_stop)
        else:
            new_stop = position.entry_price + (position.stop_loss - position.entry_price) * factor
            position.stop_loss = min(position.stop_loss, new_stop)
    
    def _update_trailing_stop(self, position: Position):
        """Atualiza trailing stop."""
        if position.direction == "COMPRA":
            new_stop = position.current_price - self.trailing_stop_distance
            if new_stop > position.stop_loss:
                position.stop_loss = new_stop
                logger.debug(f"Trailing stop atualizado para {position.id}: {new_stop:.2f}")
        else:
            new_stop = position.current_price + self.trailing_stop_distance
            if new_stop < position.stop_loss:
                position.stop_loss = new_stop
                logger.debug(f"Trailing stop atualizado para {position.id}: {new_stop:.2f}")
    
    def can_open_position(self) -> bool:
        """Verifica se pode abrir nova posição."""
        return len(self.positions) < self.max_positions
    
    def get_open_positions(self) -> List[Position]:
        """Retorna lista de posições abertas."""
        with self.lock:
            return list(self.positions.values())
    
    def get_position_by_signal(self, signal_id: str) -> Optional[Position]:
        """Retorna posição associada a um sinal."""
        with self.lock:
            position_id = self.signal_to_position.get(signal_id)
            if position_id:
                return self.positions.get(position_id)
        return None
    
    def close_all_positions(self, reason: str = "MANUAL_CLOSE"):
        """Fecha todas as posições abertas."""
        with self.lock:
            positions_to_close = list(self.positions.values())
            
            for position in positions_to_close:
                self._close_position(position, reason, position.current_price)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Retorna estatísticas do gerenciador."""
        with self.lock:
            win_rate = 0
            if self.stats['win_count'] + self.stats['loss_count'] > 0:
                win_rate = self.stats['win_count'] / (self.stats['win_count'] + self.stats['loss_count'])
            
            return {
                'open_positions': len(self.positions),
                'max_positions': self.max_positions,
                'total_opened': self.stats['total_opened'],
                'total_closed': self.stats['total_closed'],
                'total_pnl': self.stats['total_pnl'],
                'win_rate': f"{win_rate*100:.1f}%",
                'wins': self.stats['win_count'],
                'losses': self.stats['loss_count'],
                'stopped': self.stats['total_stopped'],
                'targets_hit': self.stats['total_target_hit'],
                'active_positions': [
                    {
                        'id': p.id[:8],
                        'symbol': p.symbol,
                        'direction': p.direction,
                        'pnl': p.pnl,
                        'warnings': len(p.warnings_received)
                    }
                    for p in self.positions.values()
                ]
            }
    
    def get_daily_summary(self) -> Dict[str, Any]:
        """Retorna resumo diário."""
        with self.lock:
            today = datetime.now().date()
            
            # Filtra posições de hoje
            today_closed = [
                p for p in self.closed_positions 
                if p.exit_time and p.exit_time.date() == today
            ]
            
            today_pnl = sum(p.pnl for p in today_closed)
            today_wins = sum(1 for p in today_closed if p.pnl > 0)
            today_losses = sum(1 for p in today_closed if p.pnl <= 0)
            
            return {
                'date': today.isoformat(),
                'closed_today': len(today_closed),
                'pnl_today': today_pnl,
                'wins_today': today_wins,
                'losses_today': today_losses,
                'open_positions': len(self.positions),
                'open_pnl': sum(p.pnl for p in self.positions.values())
            }