# analyzers/setups/reversal_setup_detector.py
"""
Detector de setups de reversão (lenta e violenta).
Identifica pontos de entrada em reversões de tendência.
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
import logging

# Import da classe base do detector e entidades do domínio
from application.services.base_setup_detector import SetupDetector
from domain.entities.trade import Trade
from domain.entities.book import OrderBook
from domain.entities.strategic_signal import SetupType, StrategicSignal

logger = logging.getLogger(__name__)


@dataclass
class AbsorptionEvent:
    """Evento de absorção detectado."""
    timestamp: datetime
    price: float
    volume: int
    direction: str  # COMPRA ou VENDA
    strength: float  # 0.0 a 1.0


class ReversalSetupDetector(SetupDetector): # CORREÇÃO: Herda de SetupDetector
    """
    Detecta setups de reversão lenta e violenta.
    
    Reversão Lenta: Absorção + Reversão CVD em até 2 minutos
    Reversão Violenta: Spike de volume 3x + Momentum reverso em 5 segundos
    """
    
    def __init__(self, config: Dict = None):
        super().__init__(config) # CORREÇÃO: Chama o __init__ da classe pai
        
        # Configurações Reversão Lenta
        self.slow_absorption_threshold = self.config.get('slow_absorption_threshold', 300)
        self.slow_cvd_reversal_threshold = self.config.get('slow_cvd_reversal_threshold', 100)
        self.slow_timer_minutes = self.config.get('slow_timer_minutes', 2)
        self.slow_entry_offset = self.config.get('slow_entry_offset', 1.0)  # ticks
        
        # Configurações Reversão Violenta
        self.violent_spike_multiplier = self.config.get('violent_spike_multiplier', 3.0)
        self.violent_momentum_threshold = self.config.get('violent_momentum_threshold', 150)
        self.violent_timer_seconds = self.config.get('violent_timer_seconds', 5)
        
        # Estado interno
        self.absorption_events: List[AbsorptionEvent] = []
        self.volume_baseline = {'WDO': 100, 'DOL': 50}  # Volumes médios
        self.last_cvd = {'WDO': 0, 'DOL': 0}
        self.price_history = {'WDO': [], 'DOL': []}
        
        logger.info("ReversalSetupDetector inicializado")
        
    # CORREÇÃO: Adição do método get_supported_types
    def get_supported_types(self) -> List[SetupType]:
        """
        Retorna a lista de tipos de setup que este detector suporta.
        """
        # Os nomes (REVERSAL_SLOW, REVERSAL_VIOLENT) devem existir no seu Enum SetupType
        return [SetupType.REVERSAL_SLOW, SetupType.REVERSAL_VIOLENT]

    def detect(self, 
               symbol: str,
               trades: List[Trade],
               book: Optional[OrderBook],
               market_context: Dict) -> List[StrategicSignal]:
        """
        Detecta setups de reversão nos dados fornecidos.
        
        Returns:
            Lista de sinais estratégicos detectados
        """
        signals = []
        
        if not trades or len(trades) < 10:
            return signals
        
        # Atualiza histórico de preços
        self._update_price_history(symbol, trades)
        
        # 1. Detecta Reversão Lenta
        slow_signal = self._detect_slow_reversal(symbol, trades, book, market_context)
        if slow_signal:
            signals.append(slow_signal)
        
        # 2. Detecta Reversão Violenta
        violent_signal = self._detect_violent_reversal(symbol, trades, book, market_context)
        if violent_signal:
            signals.append(violent_signal)
        
        return signals
    
    def _detect_slow_reversal(self,
                              symbol: str,
                              trades: List[Trade],
                              book: Optional[OrderBook],
                              market_context: Dict) -> Optional[StrategicSignal]:
        """Detecta reversão lenta (absorção + CVD reversal)."""
        
        # 1. Procura por absorção recente
        absorption = self._find_recent_absorption(symbol, trades)
        if not absorption:
            return None
        
        # 2. Verifica se está dentro do timer (2 minutos)
        time_since_absorption = datetime.now() - absorption.timestamp
        if time_since_absorption > timedelta(minutes=self.slow_timer_minutes):
            return None
        
        # 3. Verifica reversão do CVD
        current_cvd = market_context.get('cvd', {}).get(symbol, 0)
        cvd_delta = current_cvd - self.last_cvd.get(symbol, 0)
        
        # Para reversão de ALTA: absorção vendedora + CVD virando positivo
        if absorption.direction == "VENDA" and cvd_delta > self.slow_cvd_reversal_threshold:
            return self._create_slow_reversal_signal(
                symbol, "COMPRA", absorption, book, market_context
            )
        
        # Para reversão de BAIXA: absorção compradora + CVD virando negativo
        elif absorption.direction == "COMPRA" and cvd_delta < -self.slow_cvd_reversal_threshold:
            return self._create_slow_reversal_signal(
                symbol, "VENDA", absorption, book, market_context
            )
        
        return None
    
    def _detect_violent_reversal(self,
                                 symbol: str,
                                 trades: List[Trade],
                                 book: Optional[OrderBook],
                                 market_context: Dict) -> Optional[StrategicSignal]:
        """Detecta reversão violenta (spike + momentum)."""
        
        # 1. Detecta spike de volume
        recent_volume = sum(t.volume for t in trades[-10:])
        baseline = self.volume_baseline.get(symbol, 100)
        
        if recent_volume < baseline * self.violent_spike_multiplier:
            return None
        
        # 2. Analisa momentum dos últimos 5 segundos
        five_seconds_ago = datetime.now() - timedelta(seconds=self.violent_timer_seconds)
        recent_trades = [t for t in trades if t.timestamp > five_seconds_ago]
        
        if len(recent_trades) < 5:
            return None
        
        # 3. Calcula direção do momentum
        buy_volume = sum(t.volume for t in recent_trades if t.side.name == "BUY")
        sell_volume = sum(t.volume for t in recent_trades if t.side.name == "SELL")

        # Evita divisão por zero se não houver trades
        if (buy_volume + sell_volume) == 0:
            return None

        momentum = (buy_volume - sell_volume) / (buy_volume + sell_volume) * 100
        
        # 4. Verifica reversão baseada no contexto
        prices = self.price_history.get(symbol, [])
        if len(prices) < 30:
            return None
        
        # Tendência anterior (últimos 20 trades antes do spike)
        prior_trend = prices[-20] - prices[-30]
        
        # Reversão para ALTA: queda anterior + momentum comprador forte
        if prior_trend < -2.0 and momentum > self.violent_momentum_threshold:
            return self._create_violent_reversal_signal(
                symbol, "COMPRA", recent_volume, momentum, book, market_context
            )
        
        # Reversão para BAIXA: alta anterior + momentum vendedor forte
        elif prior_trend > 2.0 and momentum < -self.violent_momentum_threshold:
            return self._create_violent_reversal_signal(
                symbol, "VENDA", recent_volume, abs(momentum), book, market_context
            )
        
        return None
    
    def _find_recent_absorption(self, symbol: str, trades: List[Trade]) -> Optional[AbsorptionEvent]:
        """Encontra eventos de absorção recentes."""
        # Remove eventos antigos
        cutoff = datetime.now() - timedelta(minutes=self.slow_timer_minutes + 1)
        self.absorption_events = [e for e in self.absorption_events if e.timestamp > cutoff]
        
        # Analisa trades para nova absorção
        level_volumes = {}
        for trade in trades[-100:]:  # Últimos 100 trades
            level = round(trade.price / 0.5) * 0.5
            if level not in level_volumes:
                level_volumes[level] = {'buy': 0, 'sell': 0, 'total': 0}
            
            if trade.side.name == "BUY":
                level_volumes[level]['buy'] += trade.volume
            else:
                level_volumes[level]['sell'] += trade.volume
            level_volumes[level]['total'] += trade.volume
        
        # Procura por absorção significativa
        for level, volumes in level_volumes.items():
            if volumes['total'] < self.slow_absorption_threshold:
                continue
            
            # Absorção vendedora (muita venda mas preço segura)
            if volumes['sell'] > volumes['buy'] * 1.5:
                event = AbsorptionEvent(
                    timestamp=datetime.now(),
                    price=level,
                    volume=volumes['total'],
                    direction="VENDA",
                    strength=volumes['sell'] / volumes['total']
                )
                self.absorption_events.append(event)
                return event
            
            # Absorção compradora (muita compra mas preço não sobe)
            elif volumes['buy'] > volumes['sell'] * 1.5:
                event = AbsorptionEvent(
                    timestamp=datetime.now(),
                    price=level,
                    volume=volumes['total'],
                    direction="COMPRA",
                    strength=volumes['buy'] / volumes['total']
                )
                self.absorption_events.append(event)
                return event
        
        # Retorna absorção mais recente se houver
        return self.absorption_events[-1] if self.absorption_events else None
    
    def _create_slow_reversal_signal(self,
                                     symbol: str,
                                     direction: str,
                                     absorption: AbsorptionEvent,
                                     book: Optional[OrderBook],
                                     market_context: Dict) -> StrategicSignal:
        """Cria sinal de reversão lenta."""
        if not book: return None # Adiciona verificação para o book
        current_price = book.best_ask if direction == "COMPRA" else book.best_bid
        
        # Entrada conservadora (offset do preço atual)
        if direction == "COMPRA":
            entry_price = current_price + self.slow_entry_offset
            stop_loss = absorption.price - 2.0
            target1 = entry_price + 5.0
            target2 = entry_price + 10.0
        else:
            entry_price = current_price - self.slow_entry_offset
            stop_loss = absorption.price + 2.0
            target1 = entry_price - 5.0
            target2 = entry_price - 10.0
        
        risk = abs(entry_price - stop_loss)
        reward = abs(target1 - entry_price)
        risk_reward = reward / risk if risk > 0 else 0
        
        return StrategicSignal(
            id=f"REV_SLOW_{symbol}_{datetime.now().timestamp()}",
            symbol=symbol,
            setup_type=SetupType.REVERSAL_SLOW,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            targets=[target1, target2],
            confidence=0.7 + (absorption.strength * 0.15),  # 70-85%
            risk_reward=risk_reward,
            expiration_time=datetime.now() + timedelta(minutes=10),  # 10 minutos para reversão lenta
            confluence_factors=[
                f"Absorção {absorption.direction} @ {absorption.price:.2f}",
                f"Volume absorvido: {absorption.volume}",
                "Reversão CVD confirmada"
            ],
            metadata={
                'absorption_event': absorption,
                'cvd_reversal': True,
                'time_since_absorption': str(datetime.now() - absorption.timestamp)
            }
        )
    
    def _create_violent_reversal_signal(self,
                                        symbol: str,
                                        direction: str,
                                        spike_volume: int,
                                        momentum: float,
                                        book: Optional[OrderBook],
                                        market_context: Dict) -> StrategicSignal:
        """Cria sinal de reversão violenta."""
        if not book: return None # Adiciona verificação para o book

        # Entrada a mercado (imediata)
        if direction == "COMPRA":
            entry_price = book.best_ask
            stop_loss = entry_price - 3.0
            target1 = entry_price + 8.0
            target2 = entry_price + 15.0
        else:
            entry_price = book.best_bid
            stop_loss = entry_price + 3.0
            target1 = entry_price - 8.0
            target2 = entry_price - 15.0
        
        risk = abs(entry_price - stop_loss)
        reward = abs(target1 - entry_price)
        risk_reward = reward / risk if risk > 0 else 0
        
        return StrategicSignal(
            id=f"REV_VIOLENT_{symbol}_{datetime.now().timestamp()}",
            symbol=symbol,
            setup_type=SetupType.REVERSAL_VIOLENT,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            targets=[target1, target2],
            confidence=0.8 + (min(momentum, 200) / 1000),  # 80-100%
            risk_reward=risk_reward,
            expiration_time=datetime.now() + timedelta(minutes=5),  # 5 minutos para reversão violenta
            confluence_factors=[
                f"Spike de volume: {spike_volume / self.volume_baseline[symbol]:.1f}x",
                f"Momentum {direction}: {momentum:.0f}%",
                "Reversão violenta detectada"
            ],
            metadata={
                'spike_volume': spike_volume,
                'momentum': momentum,
                'entry_type': 'MARKET'
            }
        )
    
    def _update_price_history(self, symbol: str, trades: List[Trade]):
        """Mantém histórico de preços para análise de tendência."""
        if symbol not in self.price_history:
            self.price_history[symbol] = []
        
        for trade in trades:
            self.price_history[symbol].append(trade.price)
        
        # Limita tamanho do histórico
        if len(self.price_history[symbol]) > 1000:
            self.price_history[symbol] = self.price_history[symbol][-500:]
    
    def update_cvd(self, symbol: str, cvd: int):
        """Atualiza CVD para detecção de reversão."""
        self.last_cvd[symbol] = cvd
    
    def update_volume_baseline(self, symbol: str, avg_volume: float):
        """Atualiza baseline de volume para detecção de spikes."""
        self.volume_baseline[symbol] = avg_volume