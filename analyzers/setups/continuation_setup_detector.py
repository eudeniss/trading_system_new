# analyzers/setups/continuation_setup_detector.py
"""
Detector de setups de continuação (breakout e pullback).
Identifica pontos de entrada em continuações de tendência.
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
import numpy as np
import logging

# CORREÇÃO: Imports da classe base e entidades do domínio
from application.services.base_setup_detector import SetupDetector
from domain.entities.trade import Trade
from domain.entities.book import OrderBook
from domain.entities.strategic_signal import SetupType, StrategicSignal

logger = logging.getLogger(__name__)


@dataclass
class TrendInfo:
    """Informações sobre a tendência atual."""
    direction: str  # ALTA, BAIXA, LATERAL
    strength: float  # 0.0 a 1.0
    duration: int  # segundos
    slope: float  # inclinação da tendência


@dataclass
class PullbackInfo:
    """Informações sobre um pullback detectado."""
    start_price: float
    current_price: float
    depth_percent: float
    duration: int  # segundos
    volume: int


class ContinuationSetupDetector(SetupDetector): # CORREÇÃO: Herda de SetupDetector
    """
    Detecta setups de continuação.
    
    Ignição de Breakout: Momentum + Pressão simultâneos com confirmação opcional CVD
    Rejeição de Pullback: Detecta pullback após tendência com 3 tipos de confirmação
    """
    
    def __init__(self, config: Dict = None):
        super().__init__(config) # CORREÇÃO: Chama o __init__ da classe pai
        
        # Configurações Ignição de Breakout
        self.breakout_momentum_threshold = self.config.get('breakout_momentum_threshold', 100)
        self.breakout_pressure_threshold = self.config.get('breakout_pressure_threshold', 0.75)
        self.breakout_cvd_confirmation = self.config.get('breakout_cvd_confirmation', True)
        self.breakout_cvd_threshold = self.config.get('breakout_cvd_threshold', 150)
        
        # Configurações Rejeição de Pullback
        self.pullback_min_trend_bars = self.config.get('pullback_min_trend_bars', 20)
        self.pullback_depth_range = self.config.get('pullback_depth_range', (0.3, 0.6))  # 30-60%
        self.pullback_confirmation_types = self.config.get('pullback_confirmation_types', 
                                                           ['absorption', 'divergence', 'pressure'])
        
        # Estado interno
        self.trend_info = {'WDO': None, 'DOL': None}
        self.resistance_levels = {'WDO': [], 'DOL': []}
        self.support_levels = {'WDO': [], 'DOL': []}
        self.pullback_candidates = {'WDO': [], 'DOL': []}
        
        logger.info("ContinuationSetupDetector inicializado")
        
    # CORREÇÃO: Adição do método obrigatório
    def get_supported_types(self) -> List[SetupType]:
        """
        Retorna a lista de tipos de setup que este detector suporta.
        """
        return [SetupType.BREAKOUT_IGNITION, SetupType.PULLBACK_REJECTION]

    def detect(self,
               symbol: str,
               trades: List[Trade],
               book: Optional[OrderBook],
               market_context: Dict) -> List[StrategicSignal]:
        """
        Detecta setups de continuação nos dados fornecidos.
        
        Returns:
            Lista de sinais estratégicos detectados
        """
        signals = []
        
        if not trades or len(trades) < 20 or not book:
            return signals
        
        # Atualiza análise de tendência
        self._update_trend_analysis(symbol, trades)
        
        # 1. Detecta Ignição de Breakout
        breakout_signal = self._detect_breakout_ignition(symbol, trades, book, market_context)
        if breakout_signal:
            signals.append(breakout_signal)
        
        # 2. Detecta Rejeição de Pullback
        pullback_signal = self._detect_pullback_rejection(symbol, trades, book, market_context)
        if pullback_signal:
            signals.append(pullback_signal)
        
        return signals
    
    def _detect_breakout_ignition(self,
                                  symbol: str,
                                  trades: List[Trade],
                                  book: Optional[OrderBook],
                                  market_context: Dict) -> Optional[StrategicSignal]:
        """Detecta ignição de breakout (momentum + pressão)."""
        
        # 1. Verifica momentum
        momentum = self._calculate_momentum(trades)
        if abs(momentum) < self.breakout_momentum_threshold:
            return None
        
        # 2. Verifica pressão
        pressure = self._calculate_pressure(trades)
        buy_pressure = pressure.get('buy_ratio', 0)
        sell_pressure = pressure.get('sell_ratio', 0)
        
        # Determina direção baseada em momentum e pressão
        if momentum > 0 and buy_pressure < self.breakout_pressure_threshold:
            return None
        elif momentum < 0 and sell_pressure < self.breakout_pressure_threshold:
            return None
        
        direction = "COMPRA" if momentum > 0 else "VENDA"
        
        # 3. Confirmação opcional com CVD
        if self.breakout_cvd_confirmation:
            cvd = market_context.get('cvd', {}).get(symbol, 0)
            if direction == "COMPRA" and cvd < self.breakout_cvd_threshold:
                return None
            elif direction == "VENDA" and cvd > -self.breakout_cvd_threshold:
                return None
        
        # 4. Identifica nível de breakout
        breakout_level = self._find_breakout_level(symbol, trades, direction)
        if not breakout_level:
            return None
        
        return self._create_breakout_signal(
            symbol, direction, momentum, pressure, breakout_level, book, market_context
        )
    
    def _detect_pullback_rejection(self,
                                   symbol: str,
                                   trades: List[Trade],
                                   book: Optional[OrderBook],
                                   market_context: Dict) -> Optional[StrategicSignal]:
        """Detecta rejeição de pullback com confirmação."""
        
        trend = self.trend_info.get(symbol)
        if not trend or trend.strength < 0.6:
            return None
        
        # 1. Identifica pullback
        pullback = self._identify_pullback(symbol, trades, trend)
        if not pullback:
            return None
        
        # 2. Verifica profundidade adequada (30-60%)
        min_depth, max_depth = self.pullback_depth_range
        if not (min_depth <= pullback.depth_percent <= max_depth):
            return None
        
        # 3. Busca confirmações
        confirmations = self._check_pullback_confirmations(
            symbol, trades, pullback, trend, market_context
        )
        
        if len(confirmations) < 2:  # Precisa pelo menos 2 confirmações
            return None
        
        # 4. Determina tipo de entrada baseado nas confirmações
        entry_type = self._determine_pullback_entry(confirmations)
        
        return self._create_pullback_signal(
            symbol, trend.direction, pullback, confirmations, entry_type, book, market_context
        )

    def _update_trend_analysis(self, symbol: str, trades: List[Trade]):
        """Atualiza análise de tendência com tratamento de erros."""
        if len(trades) < self.pullback_min_trend_bars:
            return
        
        prices = [t.price for t in trades[-50:]]
        
        # Verifica se há dados suficientes e variados
        if len(prices) < 20:
            return
        
        # Verifica se há variação nos preços
        price_variance = np.var(prices[-20:])
        if price_variance < 1e-10:  # Praticamente sem variação
            logger.debug(f"Sem variação de preço suficiente em {symbol} para análise de tendência")
            self.trend_info[symbol] = TrendInfo(
                direction="LATERAL",
                strength=0.0,
                duration=0,
                slope=0.0
            )
            return
        
        try:
            # Cria timestamps relativos em segundos
            base_time = trades[-50].timestamp
            timestamps = [(t.timestamp - base_time).total_seconds() for t in trades[-50:]]
            
            # Verifica se há variação temporal
            if len(set(timestamps[-20:])) < 5:  # Menos de 5 timestamps únicos
                logger.debug(f"Timestamps muito próximos em {symbol}, usando índices")
                # Usa índices simples se timestamps são muito próximos
                timestamps = list(range(len(trades[-50:])))
            
            # Regressão linear para determinar tendência
            try:
                slope, intercept = np.polyfit(timestamps[-20:], prices[-20:], 1)
            except np.linalg.LinAlgError:
                # Fallback: usa média móvel simples
                logger.debug(f"Polyfit falhou para {symbol}, usando média móvel")
                ma_short = np.mean(prices[-10:])
                ma_long = np.mean(prices[-20:])
                slope = (ma_short - ma_long) / 10  # Aproximação simples
                intercept = ma_long
            
            # R-squared para força da tendência
            try:
                y_pred = [slope * t + intercept for t in timestamps[-20:]]
                ss_res = sum((prices[-20:][i] - y_pred[i]) ** 2 for i in range(20))
                ss_tot = sum((p - np.mean(prices[-20:])) ** 2 for p in prices[-20:])
                r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
                r_squared = max(0, min(1, r_squared))  # Clamp entre 0 e 1
            except:
                r_squared = 0.5  # Valor padrão se cálculo falhar
            
            # Determina direção
            avg_price = np.mean(prices[-20:]) if prices[-20:] else 1
            normalized_slope = slope / avg_price if avg_price != 0 else 0
            
            if abs(normalized_slope) < 0.001:  # Threshold para considerar lateral
                direction = "LATERAL"
            else:
                direction = "ALTA" if normalized_slope > 0 else "BAIXA"
            
            # Calcula duração da tendência
            duration = int((trades[-1].timestamp - trades[-50].timestamp).total_seconds())
            
            self.trend_info[symbol] = TrendInfo(
                direction=direction,
                strength=r_squared,
                duration=duration,
                slope=normalized_slope
            )
            
            # Atualiza níveis de suporte/resistência
            self._update_support_resistance(symbol, prices)
            
        except Exception as e:
            logger.error(f"Erro ao analisar tendência para {symbol}: {e}")
            # Define tendência padrão em caso de erro
            self.trend_info[symbol] = TrendInfo(
                direction="LATERAL",
                strength=0.0,
                duration=0,
                slope=0.0
            )
    
    def _calculate_momentum(self, trades: List[Trade]) -> float:
        """Calcula momentum baseado em volume e direção."""
        if len(trades) < 10:
            return 0
        
        recent_trades = trades[-10:]
        buy_volume = sum(t.volume for t in recent_trades if t.side.name == "BUY")
        sell_volume = sum(t.volume for t in recent_trades if t.side.name == "SELL")
        
        total_volume = buy_volume + sell_volume
        if total_volume == 0:
            return 0
        
        # Momentum direcional ponderado por volume
        momentum = ((buy_volume - sell_volume) / total_volume) * 100
        
        # Ajusta por velocidade (trades por segundo)
        time_span = (trades[-1].timestamp - trades[-10].timestamp).total_seconds()
        if time_span > 0:
            trades_per_second = len(recent_trades) / time_span
            momentum *= (1 + trades_per_second / 10)  # Boost por velocidade
        
        return momentum
    
    def _calculate_pressure(self, trades: List[Trade]) -> Dict[str, float]:
        """Calcula pressão compradora/vendedora."""
        if len(trades) < 20:
            return {'buy_ratio': 0.5, 'sell_ratio': 0.5}
        
        recent_trades = trades[-20:]
        buy_volume = sum(t.volume for t in recent_trades if t.side.name == "BUY")
        sell_volume = sum(t.volume for t in recent_trades if t.side.name == "SELL")
        
        total_volume = buy_volume + sell_volume
        if total_volume == 0:
            return {'buy_ratio': 0.5, 'sell_ratio': 0.5}
        
        return {
            'buy_ratio': buy_volume / total_volume,
            'sell_ratio': sell_volume / total_volume,
            'buy_volume': buy_volume,
            'sell_volume': sell_volume
        }
    
    def _find_breakout_level(self, symbol: str, trades: List[Trade], direction: str) -> Optional[float]:
        """Identifica o nível sendo rompido."""
        current_price = trades[-1].price
        
        if direction == "COMPRA":
            # Procura resistência sendo rompida
            resistances = [r for r in self.resistance_levels[symbol] if r < current_price]
            if resistances:
                return max(resistances)  # Resistência mais próxima
        else:
            # Procura suporte sendo rompido
            supports = [s for s in self.support_levels[symbol] if s > current_price]
            if supports:
                return min(supports)  # Suporte mais próximo
        
        return None
    
    def _identify_pullback(self, symbol: str, trades: List[Trade], trend: TrendInfo) -> Optional[PullbackInfo]:
        """Identifica um pullback na tendência."""
        if len(trades) < 30:
            return None
        
        prices = [t.price for t in trades[-30:]]
        
        start_price = 0
        current_price = trades[-1].price

        if trend.direction == "ALTA":
            # Procura por retração em tendência de alta
            start_price = max(prices[:-10])  # Pico antes dos últimos 10 trades
            if current_price >= start_price:  # Não há pullback
                return None
            depth = start_price - current_price
            depth_percent = (depth / start_price) * 100 if start_price > 0 else 0
            
        elif trend.direction == "BAIXA":
            # Procura por retração em tendência de baixa
            start_price = min(prices[:-10])  # Vale antes dos últimos 10 trades
            if current_price <= start_price:  # Não há pullback
                return None
            depth = current_price - start_price
            depth_percent = (depth / start_price) * 100 if start_price > 0 else 0
            
        else:
            return None
        
        # Calcula duração e volume do pullback
        pullback_start_idx = prices.index(start_price)
        pullback_trades = trades[-(30-pullback_start_idx):]
        
        duration = (trades[-1].timestamp - pullback_trades[0].timestamp).total_seconds()
        volume = sum(t.volume for t in pullback_trades)
        
        return PullbackInfo(
            start_price=start_price,
            current_price=current_price,
            depth_percent=depth_percent,
            duration=int(duration),
            volume=volume
        )
    
    def _check_pullback_confirmations(self,
                                      symbol: str,
                                      trades: List[Trade],
                                      pullback: PullbackInfo,
                                      trend: TrendInfo,
                                      market_context: Dict) -> List[str]:
        """Verifica confirmações para rejeição do pullback."""
        confirmations = []
        
        # 1. Confirmação por Absorção
        if 'absorption' in self.pullback_confirmation_types:
            if self._check_absorption_at_pullback(trades, pullback, trend):
                confirmations.append("ABSORÇÃO")
        
        # 2. Confirmação por Divergência
        if 'divergence' in self.pullback_confirmation_types:
            cvd_divergence = self._check_cvd_divergence(symbol, pullback, trend, market_context)
            if cvd_divergence:
                confirmations.append("DIVERGÊNCIA_CVD")
        
        # 3. Confirmação por Pressão
        if 'pressure' in self.pullback_confirmation_types:
            pressure = self._calculate_pressure(trades[-10:])
            if trend.direction == "ALTA" and pressure['buy_ratio'] > 0.65:
                confirmations.append("PRESSÃO_COMPRADORA")
            elif trend.direction == "BAIXA" and pressure['sell_ratio'] > 0.65:
                confirmations.append("PRESSÃO_VENDEDORA")
        
        return confirmations
    
    def _check_absorption_at_pullback(self, trades: List[Trade], pullback: PullbackInfo, trend: TrendInfo) -> bool:
        """Verifica se há absorção no nível do pullback."""
        pullback_level = round(pullback.current_price / 0.5) * 0.5
        level_volume = 0
        level_imbalance = 0
        
        for trade in trades[-50:]:
            if abs(trade.price - pullback_level) < 0.5:
                level_volume += trade.volume
                if trade.side.name == "BUY":
                    level_imbalance += trade.volume
                else:
                    level_imbalance -= trade.volume
        
        # Absorção em alta: vendedores sendo absorvidos
        if trend.direction == "ALTA" and level_volume > 200 and level_imbalance < -100:
            return True
        # Absorção em baixa: compradores sendo absorvidos
        elif trend.direction == "BAIXA" and level_volume > 200 and level_imbalance > 100:
            return True
        
        return False
    
    def _check_cvd_divergence(self, symbol: str, pullback: PullbackInfo, trend: TrendInfo, market_context: Dict) -> bool:
        """Verifica divergência no CVD durante pullback."""
        cvd_roc = market_context.get('cvd_roc', {}).get(symbol, 0)
        
        # Em alta: pullback com CVD crescente = divergência positiva
        if trend.direction == "ALTA" and cvd_roc > 50:
            return True
        # Em baixa: pullback com CVD caindo = divergência negativa
        elif trend.direction == "BAIXA" and cvd_roc < -50:
            return True
        
        return False
    
    def _determine_pullback_entry(self, confirmations: List[str]) -> str:
        """Determina tipo de entrada baseado nas confirmações."""
        if "ABSORÇÃO" in confirmations:
            return "LIMIT"  # Entrada limitada no nível de absorção
        elif "DIVERGÊNCIA_CVD" in confirmations and len(confirmations) >= 2:
            return "MARKET"  # Entrada a mercado com múltiplas confirmações
        else:
            return "STOP"  # Entrada stop (aguarda rompimento)
    
    def _create_breakout_signal(self,
                                 symbol: str,
                                 direction: str,
                                 momentum: float,
                                 pressure: Dict,
                                 breakout_level: float,
                                 book: Optional[OrderBook],
                                 market_context: Dict) -> StrategicSignal:
        """Cria sinal de ignição de breakout."""
        current_price = book.best_ask if direction == "COMPRA" else book.best_bid
        
        if direction == "COMPRA":
            entry_price = current_price
            stop_loss = breakout_level - 2.0
            target1 = entry_price + 10.0
            target2 = entry_price + 20.0
        else:
            entry_price = current_price
            stop_loss = breakout_level + 2.0
            target1 = entry_price - 10.0
            target2 = entry_price - 20.0
        
        risk = abs(entry_price - stop_loss)
        reward = abs(target1 - entry_price)
        risk_reward = reward / risk if risk > 0 else 0
        
        # Confiança baseada em momentum e pressão
        pressure_ratio = pressure['buy_ratio'] if direction == "COMPRA" else pressure['sell_ratio']
        confidence = 0.6 + (min(abs(momentum), 150) / 500) + (pressure_ratio - 0.5) * 0.4
        confidence = min(max(confidence, 0.6), 0.95)
        
        confluence_factors = [
            f"Rompimento de {'resistência' if direction == 'COMPRA' else 'suporte'} @ {breakout_level:.2f}",
            f"Momentum: {momentum:.0f}%",
            f"Pressão {direction.lower()}: {pressure_ratio*100:.0f}%"
        ]
        
        if market_context.get('cvd', {}).get(symbol):
            confluence_factors.append(f"CVD confirmado: {market_context['cvd'][symbol]:+d}")
        
        return StrategicSignal(
            id=f"BREAKOUT_{symbol}_{datetime.now().timestamp()}",
            symbol=symbol,
            setup_type=SetupType.BREAKOUT_IGNITION,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            targets=[target1, target2],
            confidence=confidence,
            risk_reward=risk_reward,
            expiration_time=datetime.now() + timedelta(minutes=15),  # 15 minutos para breakout
            confluence_factors=confluence_factors,
            metadata={
                'momentum': momentum,
                'pressure': pressure,
                'breakout_level': breakout_level,
                'entry_type': 'MARKET'
            }
        )
    
    def _create_pullback_signal(self,
                                 symbol: str,
                                 direction: str,
                                 pullback: PullbackInfo,
                                 confirmations: List[str],
                                 entry_type: str,
                                 book: Optional[OrderBook],
                                 market_context: Dict) -> StrategicSignal:
        """Cria sinal de rejeição de pullback."""
        current_price = book.best_ask if direction == "COMPRA" else book.best_bid
        
        # Define entrada baseada no tipo
        if entry_type == "LIMIT":
            entry_price = pullback.current_price
        elif entry_type == "MARKET":
            entry_price = current_price
        else:  # STOP
            entry_price = pullback.start_price + (1.0 if direction == "COMPRA" else -1.0)
        
        # Define stops e alvos
        if direction == "COMPRA":
            stop_loss = pullback.current_price - 3.0
            target1 = pullback.start_price + 5.0
            target2 = pullback.start_price + 12.0
        else:
            stop_loss = pullback.current_price + 3.0
            target1 = pullback.start_price - 5.0
            target2 = pullback.start_price - 12.0
        
        risk = abs(entry_price - stop_loss)
        reward = abs(target1 - entry_price)
        risk_reward = reward / risk if risk > 0 else 0
        
        # Confiança baseada no número e tipo de confirmações
        base_confidence = 0.65
        confidence_boost = len(confirmations) * 0.1
        if "ABSORÇÃO" in confirmations:
            confidence_boost += 0.05
        if "DIVERGÊNCIA_CVD" in confirmations:
            confidence_boost += 0.05
        
        confidence = min(base_confidence + confidence_boost, 0.90)
        
        confluence_factors = [
            f"Pullback {pullback.depth_percent:.1f}% em tendência de {direction.lower()}",
            f"Confirmações: {', '.join(confirmations)}",
            f"Entrada tipo: {entry_type}"
        ]
        
        return StrategicSignal(
            id=f"PULLBACK_{symbol}_{datetime.now().timestamp()}",
            symbol=symbol,
            setup_type=SetupType.PULLBACK_REJECTION,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            targets=[target1, target2],
            confidence=confidence,
            risk_reward=risk_reward,
            expiration_time=datetime.now() + timedelta(minutes=10),  # 10 minutos para pullback
            confluence_factors=confluence_factors,
            metadata={
                'pullback_info': pullback,
                'confirmations': confirmations,
                'entry_type': entry_type,
                'trend_strength': self.trend_info[symbol].strength
            }
        )
    
    def _update_support_resistance(self, symbol: str, prices: List[float]):
        """Atualiza níveis de suporte e resistência."""
        if len(prices) < 50:
            return
        
        # Encontra máximos e mínimos locais
        resistance_candidates = []
        support_candidates = []
        
        for i in range(10, len(prices) - 10):
            # Resistência: ponto mais alto em janela de 20 trades
            if prices[i] == max(prices[i-10:i+10]):
                resistance_candidates.append(prices[i])
            # Suporte: ponto mais baixo em janela de 20 trades
            elif prices[i] == min(prices[i-10:i+10]):
                support_candidates.append(prices[i])
        
        # Agrupa níveis próximos
        self.resistance_levels[symbol] = self._cluster_levels(resistance_candidates)
        self.support_levels[symbol] = self._cluster_levels(support_candidates)
    
    def _cluster_levels(self, levels: List[float], tolerance: float = 1.0) -> List[float]:
        """Agrupa níveis próximos em clusters."""
        if not levels:
            return []
        
        sorted_levels = sorted(list(set(levels))) # Evita duplicatas que podem quebrar a lógica de cluster
        clusters = []
        if not sorted_levels:
            return []
            
        current_cluster = [sorted_levels[0]]
        
        for level in sorted_levels[1:]:
            if level - current_cluster[-1] <= tolerance:
                current_cluster.append(level)
            else:
                # Finaliza cluster atual
                clusters.append(sum(current_cluster) / len(current_cluster))
                current_cluster = [level]
        
        # Adiciona último cluster
        if current_cluster:
            clusters.append(sum(current_cluster) / len(current_cluster))
        
        return sorted(clusters, reverse=True)[:5] # Mantém apenas os 5 níveis mais recentes/relevantes