# analyzers/setups/divergence_setup_detector.py
"""
Detector de divergências com uso duplo:
1. Emite warnings para gestão de risco
2. Cria setups estratégicos quando força > 0.7
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import numpy as np
import logging

# CORREÇÃO: Imports da classe base e entidades do domínio
from application.services.base_setup_detector import SetupDetector
from domain.entities.trade import Trade
from domain.entities.book import OrderBook
from domain.entities.strategic_signal import SetupType, StrategicSignal
from domain.entities.signal import Signal, SignalSource, SignalLevel

logger = logging.getLogger(__name__)


@dataclass
class DivergenceEvent:
    """Evento de divergência detectado."""
    timestamp: datetime
    symbol: str
    divergence_type: str  # PRICE_CVD, PRICE_VOLUME, CVD_MOMENTUM
    direction: str  # BULLISH ou BEARISH
    strength: float  # 0.0 a 1.0
    price_change: float
    indicator_change: float
    duration: int  # segundos


class DivergenceType(str, Enum):
    """Tipos de divergência detectáveis."""
    PRICE_CVD = "PRICE_CVD"  # Preço vs CVD
    PRICE_VOLUME = "PRICE_VOLUME"  # Preço vs Volume
    CVD_MOMENTUM = "CVD_MOMENTUM"  # CVD vs Momentum
    MULTIPLE = "MULTIPLE"  # Múltiplas divergências


class DivergenceSetupDetector(SetupDetector): # CORREÇÃO: Herda de SetupDetector
    """
    Detector de divergências com uso duplo.
    
    Detecta divergências entre:
    - Preço e CVD
    - Preço e Volume
    - CVD e Momentum
    
    Emite warning sempre, cria setup se força > 0.7
    """
# analyzers/setups/divergence_setup_detector.py
# Modificar o __init__ (linhas 45-57 aproximadamente):

    def __init__(self, config: Dict = None, event_bus=None):
        super().__init__(config)
        
        # Adicionar o event_bus
        self.event_bus = event_bus
        
        # Configurações de detecção
        self.min_bars_for_divergence = self.config.get('min_bars_for_divergence', 20)
        self.divergence_threshold = self.config.get('divergence_threshold', 0.3)  # 30%
        self.setup_strength_threshold = self.config.get('setup_strength_threshold', 0.7)
        self.warning_cooldown_seconds = self.config.get('warning_cooldown_seconds', 60)
        
        # Calculadores de preços
        self.entry_calculator = EntryPriceCalculator(config)
        self.stop_calculator = StopLossCalculator(config)
        self.target_calculator = TargetCalculator(config)
        
        # Estado interno
        self.price_history = {'WDO': [], 'DOL': []}
        self.cvd_history = {'WDO': [], 'DOL': []}
        self.volume_history = {'WDO': [], 'DOL': []}
        self.momentum_history = {'WDO': [], 'DOL': []}
        self.last_warning_time = {'WDO': datetime.min, 'DOL': datetime.min}
        self.active_divergences = {'WDO': [], 'DOL': []}
        
        logger.info("DivergenceSetupDetector inicializado")

    # CORREÇÃO: Adição do método obrigatório
    def get_supported_types(self) -> List[SetupType]:
        """
        Retorna a lista de tipos de setup que este detector suporta.
        """
        # Supondo que você tenha 'DIVERGENCE_SETUP' em seu Enum SetupType
        return [SetupType.DIVERGENCE_SETUP]

    # CORREÇÃO: Assinatura do método para retornar apenas List[StrategicSignal]
    # analyzers/setups/divergence_setup_detector.py
    # Substituir o método detect() (linhas 76-111) por:

    def detect(self,
            symbol: str,
            trades: List[Trade],
            book: Optional[OrderBook],
            market_context: Dict) -> List[StrategicSignal]:
        """
        Detecta divergências e retorna sinais estratégicos.
        Warnings são emitidos via event_bus internamente.
        
        Returns:
            Lista de sinais estratégicos detectados
        """
        strategic_signals = []
        
        if not trades or len(trades) < self.min_bars_for_divergence:
            return strategic_signals
        
        # Atualiza históricos
        self._update_histories(symbol, trades, market_context)
        
        # Detecta todas as divergências
        divergences = self._detect_all_divergences(symbol)
        
        # Processa cada divergência
        for divergence in divergences:
            # Sempre emite warning (com cooldown) via event_bus
            warning_signal = self._create_warning_signal(divergence)
            if warning_signal:
                # Emite o warning via event_bus ao invés de retorná-lo
                if hasattr(self, 'event_bus') and self.event_bus:
                    self.event_bus.publish("DIVERGENCE_WARNING", warning_signal)
                else:
                    logger.warning(f"DIVERGENCE WARNING: {warning_signal.message}")
            
            # Cria setup estratégico se força > threshold
            if divergence.strength >= self.setup_strength_threshold:
                setup = self._create_divergence_setup(divergence, book, market_context)
                if setup:
                    strategic_signals.append(setup)
        
        return strategic_signals
        
    def _detect_all_divergences(self, symbol: str) -> List[DivergenceEvent]:
        """Detecta todos os tipos de divergência."""
        divergences = []
        
        # 1. Divergência Preço vs CVD
        price_cvd_div = self._detect_price_cvd_divergence(symbol)
        if price_cvd_div:
            divergences.append(price_cvd_div)
        
        # 2. Divergência Preço vs Volume
        price_volume_div = self._detect_price_volume_divergence(symbol)
        if price_volume_div:
            divergences.append(price_volume_div)
        
        # 3. Divergência CVD vs Momentum
        cvd_momentum_div = self._detect_cvd_momentum_divergence(symbol)
        if cvd_momentum_div:
            divergences.append(cvd_momentum_div)
        
        # 4. Verifica divergências múltiplas (mais forte)
        if len(divergences) >= 2:
            multiple_div = self._create_multiple_divergence(symbol, divergences)
            divergences = [multiple_div]  # Substitui por divergência múltipla
        
        return divergences
    
    def _detect_price_cvd_divergence(self, symbol: str) -> Optional[DivergenceEvent]:
        """Detecta divergência entre preço e CVD."""
        prices = self.price_history[symbol]
        cvds = self.cvd_history[symbol]
        
        if len(prices) < self.min_bars_for_divergence or len(cvds) < self.min_bars_for_divergence:
            return None
        
        # Calcula mudanças percentuais
        price_change = (prices[-1] - prices[-20]) / (prices[-20] if prices[-20] != 0 else 1) * 100
        cvd_change = cvds[-1] - cvds[-20]  # CVD é absoluto, não percentual
        
        # Divergência Bullish: preço cai mas CVD sobe
        if price_change < -self.divergence_threshold and cvd_change > 50:
            strength = min(abs(cvd_change) / 200, 1.0)  # Normaliza força
            return DivergenceEvent(
                timestamp=datetime.now(),
                symbol=symbol,
                divergence_type=DivergenceType.PRICE_CVD,
                direction="BULLISH",
                strength=strength,
                price_change=price_change,
                indicator_change=cvd_change,
                duration=self.min_bars_for_divergence
            )
        
        # Divergência Bearish: preço sobe mas CVD cai
        elif price_change > self.divergence_threshold and cvd_change < -50:
            strength = min(abs(cvd_change) / 200, 1.0)
            return DivergenceEvent(
                timestamp=datetime.now(),
                symbol=symbol,
                divergence_type=DivergenceType.PRICE_CVD,
                direction="BEARISH",
                strength=strength,
                price_change=price_change,
                indicator_change=cvd_change,
                duration=self.min_bars_for_divergence
            )
        
        return None
    
    def _detect_price_volume_divergence(self, symbol: str) -> Optional[DivergenceEvent]:
        """Detecta divergência entre preço e volume."""
        prices = self.price_history[symbol]
        volumes = self.volume_history[symbol]
        
        if len(prices) < self.min_bars_for_divergence or len(volumes) < self.min_bars_for_divergence:
            return None
        
        # Mudanças
        price_change = (prices[-1] - prices[-20]) / (prices[-20] if prices[-20] != 0 else 1) * 100
        avg_volume_recent = np.mean(volumes[-10:])
        avg_volume_prior = np.mean(volumes[-20:-10])
        volume_change = (avg_volume_recent - avg_volume_prior) / (avg_volume_prior if avg_volume_prior != 0 else 1) * 100
        
        # Divergência: movimento de preço sem suporte de volume
        if abs(price_change) > self.divergence_threshold and abs(volume_change) < 20:
            # Movimento suspeito - preço move mas volume não acompanha
            direction = "BEARISH" if price_change > 0 else "BULLISH"
            strength = min(abs(price_change) / (abs(volume_change) + 1), 1.0) * 0.8
            
            return DivergenceEvent(
                timestamp=datetime.now(),
                symbol=symbol,
                divergence_type=DivergenceType.PRICE_VOLUME,
                direction=direction,
                strength=strength,
                price_change=price_change,
                indicator_change=volume_change,
                duration=self.min_bars_for_divergence
            )
        
        return None
    
    def _detect_cvd_momentum_divergence(self, symbol: str) -> Optional[DivergenceEvent]:
        """Detecta divergência entre CVD e momentum."""
        cvds = self.cvd_history[symbol]
        momentums = self.momentum_history[symbol]
        
        if len(cvds) < 10 or len(momentums) < 10:
            return None
        
        # Tendências recentes
        cvd_trend = cvds[-1] - cvds[-10]
        momentum_trend = momentums[-1] - momentums[-10]
        
        # Divergência: CVD e momentum em direções opostas
        if abs(cvd_trend) > 50 and abs(momentum_trend) > 30:
            if (cvd_trend > 0 and momentum_trend < 0) or (cvd_trend < 0 and momentum_trend > 0):
                direction = "BULLISH" if cvd_trend > 0 else "BEARISH"
                strength = min((abs(cvd_trend) + abs(momentum_trend)) / 200, 1.0) * 0.9
                
                return DivergenceEvent(
                    timestamp=datetime.now(),
                    symbol=symbol,
                    divergence_type=DivergenceType.CVD_MOMENTUM,
                    direction=direction,
                    strength=strength,
                    price_change=0,  # Não aplicável
                    indicator_change=cvd_trend,
                    duration=10
                )
        
        return None
    
    def _create_multiple_divergence(self, symbol: str, divergences: List[DivergenceEvent]) -> DivergenceEvent:
        """Cria evento de divergência múltipla (mais forte)."""
        # Calcula força combinada
        avg_strength = np.mean([d.strength for d in divergences])
        boost = 0.1 * (len(divergences) - 1)  # Bonus por múltiplas divergências
        combined_strength = min(avg_strength + boost, 1.0)
        
        # Direção dominante
        bullish_count = sum(1 for d in divergences if d.direction == "BULLISH")
        direction = "BULLISH" if bullish_count > len(divergences) / 2 else "BEARISH"
        
        return DivergenceEvent(
            timestamp=datetime.now(),
            symbol=symbol,
            divergence_type=DivergenceType.MULTIPLE,
            direction=direction,
            strength=combined_strength,
            price_change=divergences[0].price_change,
            indicator_change=divergences[0].indicator_change,
            duration=self.min_bars_for_divergence
        )
    
    def _create_warning_signal(self, divergence: DivergenceEvent) -> Optional[Signal]:
        """Cria sinal de warning para divergência (com cooldown)."""
        # Verifica cooldown
        if datetime.now() - self.last_warning_time[divergence.symbol] < timedelta(seconds=self.warning_cooldown_seconds):
            return None
        
        self.last_warning_time[divergence.symbol] = datetime.now()
        
        # Mensagem baseada no tipo e direção
        emoji = "⚠️" if divergence.strength < 0.7 else "🚨"
        direction_text = "ALTA" if divergence.direction == "BULLISH" else "BAIXA"
        
        type_messages = {
            DivergenceType.PRICE_CVD: f"Preço vs CVD divergindo para {direction_text}",
            DivergenceType.PRICE_VOLUME: f"Volume não confirma movimento de preço",
            DivergenceType.CVD_MOMENTUM: f"CVD e Momentum em conflito",
            DivergenceType.MULTIPLE: f"MÚLTIPLAS divergências para {direction_text}"
        }
        
        message = f"{emoji} {divergence.symbol} - {type_messages.get(divergence.divergence_type, 'Divergência detectada')}"
        
        return Signal(
            source=SignalSource.STRATEGIC,
            level=SignalLevel.WARNING,
            message=message,
            details={
                'divergence_event': divergence,
                'is_setup_candidate': divergence.strength >= self.setup_strength_threshold
            }
        )
    
    def _create_divergence_setup(self,
                                  divergence: DivergenceEvent,
                                  book: Optional[OrderBook],
                                  market_context: Dict) -> Optional[StrategicSignal]:
        """Cria setup estratégico baseado em divergência forte."""
        if not book:
            return None
        
        # Direção do trade baseada no tipo de divergência
        direction = "COMPRA" if divergence.direction == "BULLISH" else "VENDA"
        
        # Calcula preços usando calculadores unificados
        entry_price = self.entry_calculator.calculate(
            setup_type=SetupType.DIVERGENCE_SETUP,
            direction=direction,
            book=book,
            context={'divergence': divergence}
        )
        
        stop_loss = self.stop_calculator.calculate(
            setup_type=SetupType.DIVERGENCE_SETUP,
            direction=direction,
            entry_price=entry_price,
            context={'divergence': divergence, 'volatility': market_context.get('volatility', 'NORMAL')}
        )
        
        targets = self.target_calculator.calculate(
            setup_type=SetupType.DIVERGENCE_SETUP,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            context={'divergence': divergence}
        )
        
        risk = abs(entry_price - stop_loss)
        reward = abs(targets[0] - entry_price) if targets else 0
        risk_reward = reward / risk if risk > 0 else 0
        
        # Fatores de confluência
        confluence_factors = [
            f"Divergência {divergence.divergence_type.value}",
            f"Força: {divergence.strength*100:.0f}%",
            f"Direção: {divergence.direction}"
        ]
        
        if divergence.divergence_type == DivergenceType.MULTIPLE:
            confluence_factors.append("MÚLTIPLAS divergências confirmadas")
        
        return StrategicSignal(
            id=f"DIV_{divergence.symbol}_{datetime.now().timestamp()}",
            symbol=divergence.symbol,
            setup_type=SetupType.DIVERGENCE_SETUP,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            targets=targets,
            confidence=divergence.strength,
            risk_reward=risk_reward,
            expiration_time=datetime.now() + timedelta(minutes=8),  # 8 minutos para divergência
            confluence_factors=confluence_factors,
            metadata={
                'divergence_type': divergence.divergence_type.value,
                'divergence_strength': divergence.strength,
                'price_change': divergence.price_change,
                'indicator_change': divergence.indicator_change
            }
        )
    
    def _update_histories(self, symbol: str, trades: List[Trade], market_context: Dict):
        """Atualiza históricos para análise."""
        # Preço
        if trades:
            avg_price = np.mean([t.price for t in trades[-10:]])
            self.price_history[symbol].append(avg_price)
            if len(self.price_history[symbol]) > 100:
                self.price_history[symbol].pop(0)
        
        # CVD
        cvd = market_context.get('cvd', {}).get(symbol, 0)
        self.cvd_history[symbol].append(cvd)
        if len(self.cvd_history[symbol]) > 100:
            self.cvd_history[symbol].pop(0)
        
        # Volume
        total_volume = sum(t.volume for t in trades[-10:]) if trades else 0
        self.volume_history[symbol].append(total_volume)
        if len(self.volume_history[symbol]) > 100:
            self.volume_history[symbol].pop(0)
        
        # Momentum (simplificado)
        if len(trades) >= 10:
            buy_vol = sum(t.volume for t in trades[-10:] if t.side.name == "BUY")
            sell_vol = sum(t.volume for t in trades[-10:] if t.side.name == "SELL")
            total_vol = buy_vol + sell_vol
            momentum = ((buy_vol - sell_vol) / (total_vol if total_vol != 0 else 1)) * 100
        else:
            momentum = 0
        
        self.momentum_history[symbol].append(momentum)
        if len(self.momentum_history[symbol]) > 100:
            self.momentum_history[symbol].pop(0)


class EntryPriceCalculator:
    """Calculador unificado de preços de entrada."""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.default_offsets = {
            "REVERSAL_SLOW": 1.0,  # Conservador
            "REVERSAL_VIOLENT": 0.0,  # A mercado
            "BREAKOUT_IGNITION": 0.0,  # A mercado
            "PULLBACK_REJECTION": 0.5, # Meio termo
            "DIVERGENCE_SETUP": 0.5  # Meio termo
        }
    
    def calculate(self, 
                  setup_type: SetupType,
                  direction: str,
                  book: OrderBook,
                  context: Dict = None) -> float:
        """Calcula preço de entrada baseado no setup."""
        context = context or {}
        
        # Preço base
        base_price = book.best_ask if direction == "COMPRA" else book.best_bid
        
        # Offset baseado no tipo
        offset = self.default_offsets.get(setup_type.name, 0.5)
        
        # Ajustes contextuais
        if setup_type == SetupType.PULLBACK_REJECTION:
            entry_type = context.get('entry_type', 'LIMIT')
            if entry_type == 'MARKET':
                offset = 0.0
            elif entry_type == 'STOP':
                offset = 2.0
        
        # Aplica offset
        return base_price + offset if direction == "COMPRA" else base_price - offset


class StopLossCalculator:
    """Calculador unificado de stop loss."""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.default_stops = {
            "REVERSAL_SLOW": 2.0,
            "REVERSAL_VIOLENT": 3.0,
            "BREAKOUT_IGNITION": 2.0,
            "PULLBACK_REJECTION": 3.0,
            "DIVERGENCE_SETUP": 2.5
        }
    
    def calculate(self,
                  setup_type: SetupType,
                  direction: str,
                  entry_price: float,
                  context: Dict = None) -> float:
        """Calcula stop loss baseado no setup e contexto."""
        context = context or {}
        
        # Stop base
        base_stop = self.default_stops.get(setup_type.name, 2.5)
        
        # Ajusta por volatilidade
        volatility = context.get('volatility', 'NORMAL')
        if volatility == 'HIGH':
            base_stop *= 1.5
        elif volatility == 'LOW':
            base_stop *= 0.8
        
        # Ajusta por força do sinal
        if setup_type == SetupType.DIVERGENCE_SETUP:
            divergence = context.get('divergence')
            if divergence and divergence.strength > 0.85:
                base_stop *= 0.8  # Stop mais apertado para sinais fortes
        
        # Aplica stop
        return entry_price - base_stop if direction == "COMPRA" else entry_price + base_stop


class TargetCalculator:
    """Calculador unificado de alvos."""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.risk_reward_ratios = {
            "REVERSAL_SLOW": [2.5, 5.0],  # Conservador
            "REVERSAL_VIOLENT": [3.0, 6.0],  # Agressivo
            "BREAKOUT_IGNITION": [4.0, 8.0],  # Muito agressivo
            "PULLBACK_REJECTION": [2.0, 4.0], # Moderado
            "DIVERGENCE_SETUP": [2.5, 5.0]  # Conservador
        }
    
    def calculate(self,
                  setup_type: SetupType,
                  direction: str,
                  entry_price: float,
                  stop_loss: float,
                  context: Dict = None) -> List[float]:
        """Calcula alvos baseados em risk/reward."""
        context = context or {}
        
        # Risk/reward base
        rr_ratios = self.risk_reward_ratios.get(setup_type.name, [2.0, 4.0])
        
        # Calcula risco
        risk = abs(entry_price - stop_loss)
        
        # Calcula alvos
        targets = []
        for ratio in rr_ratios:
            if direction == "COMPRA":
                target = entry_price + (risk * ratio)
            else:
                target = entry_price - (risk * ratio)
            targets.append(round(target, 2))
        
        return targets