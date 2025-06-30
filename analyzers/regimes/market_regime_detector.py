# analyzers/regimes/market_regime_detector.py
import numpy as np
from typing import Dict, List, Tuple
from datetime import datetime
from collections import deque
from enum import Enum
import logging

from domain.entities.trade import Trade
from domain.entities.book import OrderBook
from domain.entities.market_data import MarketData

logger = logging.getLogger(__name__)


class MarketRegime(str, Enum):
    """Tipos de regime de mercado."""
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"
    QUIET = "QUIET"
    BREAKOUT = "BREAKOUT"
    REVERSAL = "REVERSAL"


class VolatilityLevel(str, Enum):
    """Níveis de volatilidade."""
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


class LiquidityLevel(str, Enum):
    """Níveis de liquidez."""
    THIN = "THIN"
    NORMAL = "NORMAL"
    DEEP = "DEEP"


class MarketRegimeDetector:
    """
    Detecta o regime atual do mercado analisando múltiplos fatores
    como tendência, volatilidade, liquidez e estrutura de mercado.
    """
    
    def __init__(self, lookback_period: int = 300, update_interval: int = 10):
        """
        Args:
            lookback_period: Período em segundos para análise (padrão: 5 minutos)
            update_interval: Intervalo em segundos entre atualizações (padrão: 10s)
        """
        self.lookback_period = lookback_period
        self.update_interval = update_interval
        
        # Histórico de dados por símbolo
        self.price_history = {
            'WDO': deque(maxlen=1000),
            'DOL': deque(maxlen=1000)
        }
        
        self.volume_history = {
            'WDO': deque(maxlen=1000),
            'DOL': deque(maxlen=1000)
        }
        
        self.spread_history = {
            'WDO': deque(maxlen=500),
            'DOL': deque(maxlen=500)
        }
        
        self.trade_flow = {
            'WDO': deque(maxlen=2000),
            'DOL': deque(maxlen=2000)
        }
        
        # Regime atual
        self.current_regime = {
            'WDO': MarketRegime.RANGING,
            'DOL': MarketRegime.RANGING
        }
        
        self.regime_confidence = {
            'WDO': 0.5,
            'DOL': 0.5
        }
        
        # Métricas derivadas
        self.metrics = {
            'WDO': self._create_empty_metrics(),
            'DOL': self._create_empty_metrics()
        }
        
        # Última atualização
        self.last_update = datetime.now()
        
        # Parâmetros adaptativos
        self.adaptive_params = {
            'trend_threshold': 0.001,  # 0.1% de movimento
            'volatility_multiplier': 1.5,
            'volume_spike_threshold': 3.0,
            'liquidity_depth_levels': 5
        }
    
    def _create_empty_metrics(self) -> Dict:
        """Cria estrutura vazia de métricas."""
        return {
            'trend_strength': 0.0,
            'trend_direction': 0,
            'volatility': VolatilityLevel.NORMAL,
            'volatility_value': 0.0,
            'liquidity': LiquidityLevel.NORMAL,
            'liquidity_score': 0.0,
            'momentum': 0.0,
            'market_depth_imbalance': 0.0,
            'price_acceleration': 0.0,
            'volume_profile_skew': 0.0,
            'microstructure_score': 0.0
        }
    
    def update(self, market_data: MarketData) -> Dict[str, MarketRegime]:
        """
        Atualiza a detecção de regime com novos dados de mercado.
        
        Returns:
            Dict com o regime atual para cada símbolo
        """
        now = datetime.now()
        
        # Atualiza apenas no intervalo definido
        if (now - self.last_update).seconds < self.update_interval:
            return self.current_regime
        
        for symbol, data in market_data.data.items():
            if data.trades:
                self._update_price_history(symbol, data.trades)
                self._update_volume_history(symbol, data.trades)
                self._update_trade_flow(symbol, data.trades)
            
            if data.book:
                self._update_spread_history(symbol, data.book)
            
            # Analisa regime se houver dados suficientes
            if len(self.price_history[symbol]) >= 30:
                self._analyze_market_regime(symbol)
        
        self.last_update = now
        return self.current_regime
    
    def _update_price_history(self, symbol: str, trades: List[Trade]):
        """Atualiza histórico de preços."""
        for trade in trades:
            self.price_history[symbol].append({
                'price': trade.price,
                'volume': trade.volume,
                'timestamp': trade.timestamp
            })
    
    def _update_volume_history(self, symbol: str, trades: List[Trade]):
        """Atualiza histórico de volume."""
        total_volume = sum(t.volume for t in trades)
        if total_volume > 0:
            self.volume_history[symbol].append({
                'volume': total_volume,
                'timestamp': datetime.now()
            })
    
    def _update_spread_history(self, symbol: str, book: OrderBook):
        """Atualiza histórico de spread."""
        if book.best_bid > 0 and book.best_ask > 0:
            spread = book.best_ask - book.best_bid
            self.spread_history[symbol].append({
                'spread': spread,
                'bid_size': book.bids[0].volume if book.bids else 0,
                'ask_size': book.asks[0].volume if book.asks else 0,
                'timestamp': datetime.now()
            })
    
    def _update_trade_flow(self, symbol: str, trades: List[Trade]):
        """Atualiza fluxo de trades para análise de microestrutura."""
        for trade in trades:
            self.trade_flow[symbol].append({
                'price': trade.price,
                'volume': trade.volume,
                'side': trade.side.value,
                'timestamp': trade.timestamp
            })
    
    def _analyze_market_regime(self, symbol: str):
        """Analisa e determina o regime de mercado atual."""
        # 1. Análise de Tendência
        trend_analysis = self._analyze_trend(symbol)
        self.metrics[symbol]['trend_strength'] = trend_analysis['strength']
        self.metrics[symbol]['trend_direction'] = trend_analysis['direction']
        
        # 2. Análise de Volatilidade
        volatility_analysis = self._analyze_volatility(symbol)
        self.metrics[symbol]['volatility'] = volatility_analysis['level']
        self.metrics[symbol]['volatility_value'] = volatility_analysis['value']
        
        # 3. Análise de Liquidez
        liquidity_analysis = self._analyze_liquidity(symbol)
        self.metrics[symbol]['liquidity'] = liquidity_analysis['level']
        self.metrics[symbol]['liquidity_score'] = liquidity_analysis['score']
        
        # 4. Análise de Momentum
        momentum = self._calculate_momentum(symbol)
        self.metrics[symbol]['momentum'] = momentum
        
        # 5. Análise de Microestrutura
        microstructure = self._analyze_microstructure(symbol)
        self.metrics[symbol]['microstructure_score'] = microstructure['score']
        self.metrics[symbol]['market_depth_imbalance'] = microstructure['depth_imbalance']
        
        # 6. Determina o regime baseado nas análises
        regime, confidence = self._determine_regime(symbol)
        self.current_regime[symbol] = regime
        self.regime_confidence[symbol] = confidence
        
        # Log mudanças significativas
        if confidence > 0.7:
            logger.info(f"{symbol} - Regime: {regime.value} (Confiança: {confidence:.2f})")
    
    def _analyze_trend(self, symbol: str) -> Dict:
        """Analisa a tendência de preço."""
        prices = [p['price'] for p in list(self.price_history[symbol])[-100:]]
        
        if len(prices) < 20:
            return {'strength': 0, 'direction': 0}
        
        # Regressão linear para tendência
        x = np.arange(len(prices))
        slope, intercept = np.polyfit(x, prices, 1)
        
        # Normaliza o slope pelo preço médio
        avg_price = np.mean(prices)
        normalized_slope = slope / avg_price if avg_price > 0 else 0
        
        # R-squared para força da tendência
        y_pred = slope * x + intercept
        ss_res = np.sum((prices - y_pred) ** 2)
        ss_tot = np.sum((prices - np.mean(prices)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        # Média móvel para confirmação
        sma_20 = np.mean(prices[-20:])
        sma_50 = np.mean(prices[-50:]) if len(prices) >= 50 else sma_20
        ma_signal = 1 if sma_20 > sma_50 else -1 if sma_20 < sma_50 else 0
        
        # Combina sinais
        direction = 1 if normalized_slope > self.adaptive_params['trend_threshold'] else \
                   -1 if normalized_slope < -self.adaptive_params['trend_threshold'] else 0
        
        # Ajusta direção com confirmação de MA
        if direction != 0 and ma_signal == direction:
            strength = min(r_squared * 1.2, 1.0)  # Bonus por confirmação
        else:
            strength = r_squared * 0.8
        
        return {
            'strength': strength,
            'direction': direction,
            'slope': normalized_slope,
            'ma_confirmation': ma_signal == direction
        }
    
    def _analyze_volatility(self, symbol: str) -> Dict:
        """Analisa a volatilidade do mercado."""
        prices = [p['price'] for p in list(self.price_history[symbol])[-60:]]
        
        if len(prices) < 20:
            return {'level': VolatilityLevel.NORMAL, 'value': 0}
        
        # Calcula retornos
        returns = np.diff(prices) / prices[:-1]
        
        # Volatilidade realizada
        volatility = np.std(returns) * np.sqrt(252)  # Anualizada
        
        # Volatilidade de Parkinson (high-low)
        period_high_low = []
        for i in range(0, len(prices)-5, 5):
            period_prices = prices[i:i+5]
            if period_prices:
                hl_vol = (max(period_prices) - min(period_prices)) / np.mean(period_prices)
                period_high_low.append(hl_vol)
        
        parkinson_vol = np.mean(period_high_low) if period_high_low else 0
        
        # ATR-like measure
        true_ranges = []
        for i in range(1, len(prices)):
            tr = abs(prices[i] - prices[i-1])
            true_ranges.append(tr)
        
        atr = np.mean(true_ranges[-20:]) if true_ranges else 0
        atr_pct = (atr / np.mean(prices)) * 100 if prices else 0
        
        # Classifica volatilidade
        if volatility < 0.15 and atr_pct < 0.5:
            level = VolatilityLevel.LOW
        elif volatility < 0.25 and atr_pct < 1.0:
            level = VolatilityLevel.NORMAL
        elif volatility < 0.40 and atr_pct < 2.0:
            level = VolatilityLevel.HIGH
        else:
            level = VolatilityLevel.EXTREME
        
        return {
            'level': level,
            'value': volatility,
            'parkinson': parkinson_vol,
            'atr_pct': atr_pct
        }
    
    def _analyze_liquidity(self, symbol: str) -> Dict:
        """Analisa a liquidez do mercado."""
        # Volume médio
        recent_volumes = [v['volume'] for v in list(self.volume_history[symbol])[-30:]]
        avg_volume = np.mean(recent_volumes) if recent_volumes else 0
        
        # Spread médio
        recent_spreads = [s['spread'] for s in list(self.spread_history[symbol])[-30:]]
        avg_spread = np.mean(recent_spreads) if recent_spreads else 0
        
        # Profundidade do book (bid/ask sizes)
        recent_depths = [(s['bid_size'] + s['ask_size']) 
                        for s in list(self.spread_history[symbol])[-30:]]
        avg_depth = np.mean(recent_depths) if recent_depths else 0
        
        # Kyle's Lambda (impacto de preço)
        price_impacts = []
        trades = list(self.trade_flow[symbol])[-50:]
        
        for i in range(1, len(trades)):
            if trades[i]['volume'] > 0:
                price_change = abs(trades[i]['price'] - trades[i-1]['price'])
                impact = price_change / trades[i]['volume']
                price_impacts.append(impact)
        
        avg_impact = np.mean(price_impacts) if price_impacts else 0
        
        # Score de liquidez (0-1)
        volume_score = min(avg_volume / 100, 1.0)  # Normalizado para 100
        spread_score = max(1 - (avg_spread / 2.0), 0)  # Spread menor = melhor
        depth_score = min(avg_depth / 200, 1.0)  # Normalizado para 200
        impact_score = max(1 - (avg_impact * 1000), 0)  # Impacto menor = melhor
        
        liquidity_score = np.mean([volume_score, spread_score, depth_score, impact_score])
        
        # Classifica liquidez
        if liquidity_score < 0.3:
            level = LiquidityLevel.THIN
        elif liquidity_score < 0.7:
            level = LiquidityLevel.NORMAL
        else:
            level = LiquidityLevel.DEEP
        
        return {
            'level': level,
            'score': liquidity_score,
            'avg_volume': avg_volume,
            'avg_spread': avg_spread,
            'avg_depth': avg_depth,
            'price_impact': avg_impact
        }
    
    def _calculate_momentum(self, symbol: str) -> float:
        """Calcula o momentum do mercado."""
        prices = [p['price'] for p in list(self.price_history[symbol])[-60:]]
        
        if len(prices) < 20:
            return 0.0
        
        # RSI
        deltas = np.diff(prices)
        gains = deltas[deltas > 0]
        losses = -deltas[deltas < 0]
        
        avg_gain = np.mean(gains) if len(gains) > 0 else 0
        avg_loss = np.mean(losses) if len(losses) > 0 else 0
        
        rs = avg_gain / avg_loss if avg_loss > 0 else 100
        rsi = 100 - (100 / (1 + rs))
        
        # Rate of Change
        if len(prices) >= 10:
            roc = ((prices[-1] - prices[-10]) / prices[-10]) * 100
        else:
            roc = 0
        
        # MACD-like indicator
        if len(prices) >= 26:
            ema_12 = self._calculate_ema(prices[-26:], 12)
            ema_26 = self._calculate_ema(prices[-26:], 26)
            macd = ema_12 - ema_26
            signal_line = self._calculate_ema([macd], 9)
            macd_histogram = macd - signal_line
        else:
            macd_histogram = 0
        
        # Normaliza momentum (-1 a 1)
        rsi_momentum = (rsi - 50) / 50
        roc_momentum = np.tanh(roc / 10)  # Tanh para limitar entre -1 e 1
        macd_momentum = np.tanh(macd_histogram)
        
        # Combina indicadores
        momentum = np.mean([rsi_momentum, roc_momentum, macd_momentum])
        
        return momentum
    
    def _calculate_ema(self, data: List[float], period: int) -> float:
        """Calcula Exponential Moving Average."""
        if not data or period <= 0:
            return 0
        
        multiplier = 2 / (period + 1)
        ema = data[0]
        
        for price in data[1:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    def _analyze_microstructure(self, symbol: str) -> Dict:
        """Analisa a microestrutura do mercado."""
        trades = list(self.trade_flow[symbol])[-100:]
        spreads = list(self.spread_history[symbol])[-50:]
        
        if len(trades) < 20 or len(spreads) < 10:
            return {'score': 0.5, 'depth_imbalance': 0}
        
        # Order Flow Imbalance
        buy_volume = sum(t['volume'] for t in trades if t['side'] == 'BUY')
        sell_volume = sum(t['volume'] for t in trades if t['side'] == 'SELL')
        total_volume = buy_volume + sell_volume
        
        if total_volume > 0:
            ofi = (buy_volume - sell_volume) / total_volume
        else:
            ofi = 0
        
        # Depth Imbalance
        recent_imbalances = []
        for spread in spreads:
            total_depth = spread['bid_size'] + spread['ask_size']
            if total_depth > 0:
                imbalance = (spread['bid_size'] - spread['ask_size']) / total_depth
                recent_imbalances.append(imbalance)
        
        avg_depth_imbalance = np.mean(recent_imbalances) if recent_imbalances else 0
        
        # Trade Size Distribution
        trade_sizes = [t['volume'] for t in trades]
        if trade_sizes:
            size_cv = np.std(trade_sizes) / np.mean(trade_sizes)  # Coefficient of variation
        else:
            size_cv = 0
        
        # Price Discovery (velocidade de ajuste de preço)
        price_changes = []
        for i in range(1, len(trades)):
            if trades[i]['price'] != trades[i-1]['price']:
                price_changes.append(abs(trades[i]['price'] - trades[i-1]['price']))
        
        avg_tick_size = np.mean(price_changes) if price_changes else 0
        
        # Microstructure score (0-1)
        ofi_score = abs(ofi)  # 0-1
        depth_score = abs(avg_depth_imbalance)  # 0-1
        size_score = min(size_cv / 2, 1)  # Normalizado
        discovery_score = min(avg_tick_size / 1.0, 1)  # Normalizado para 1 ponto
        
        microstructure_score = np.mean([ofi_score, depth_score, size_score, discovery_score])
        
        return {
            'score': microstructure_score,
            'depth_imbalance': avg_depth_imbalance,
            'order_flow_imbalance': ofi,
            'size_distribution': size_cv,
            'price_discovery': avg_tick_size
        }
    
    def _determine_regime(self, symbol: str) -> Tuple[MarketRegime, float]:
        """Determina o regime de mercado baseado em todas as análises."""
        metrics = self.metrics[symbol]
        
        # Extrai valores
        trend_strength = metrics['trend_strength']
        trend_direction = metrics['trend_direction']
        volatility = metrics['volatility']
        liquidity = metrics['liquidity']
        momentum = metrics['momentum']
        micro_score = metrics['microstructure_score']
        
        # Sistema de pontuação para cada regime
        scores = {
            MarketRegime.TRENDING_UP: 0,
            MarketRegime.TRENDING_DOWN: 0,
            MarketRegime.RANGING: 0,
            MarketRegime.VOLATILE: 0,
            MarketRegime.QUIET: 0,
            MarketRegime.BREAKOUT: 0,
            MarketRegime.REVERSAL: 0
        }
        
        # TRENDING UP
        if trend_direction > 0:
            scores[MarketRegime.TRENDING_UP] = trend_strength * 0.4 + max(momentum, 0) * 0.3
            if volatility == VolatilityLevel.NORMAL:
                scores[MarketRegime.TRENDING_UP] += 0.2
            if liquidity in [LiquidityLevel.NORMAL, LiquidityLevel.DEEP]:
                scores[MarketRegime.TRENDING_UP] += 0.1
        
        # TRENDING DOWN
        if trend_direction < 0:
            scores[MarketRegime.TRENDING_DOWN] = trend_strength * 0.4 + abs(min(momentum, 0)) * 0.3
            if volatility == VolatilityLevel.NORMAL:
                scores[MarketRegime.TRENDING_DOWN] += 0.2
            if liquidity in [LiquidityLevel.NORMAL, LiquidityLevel.DEEP]:
                scores[MarketRegime.TRENDING_DOWN] += 0.1
        
        # RANGING
        if abs(trend_direction) == 0 or trend_strength < 0.3:
            scores[MarketRegime.RANGING] = (1 - trend_strength) * 0.5
            if volatility == VolatilityLevel.LOW:
                scores[MarketRegime.RANGING] += 0.3
            if abs(momentum) < 0.3:
                scores[MarketRegime.RANGING] += 0.2
        
        # VOLATILE
        if volatility in [VolatilityLevel.HIGH, VolatilityLevel.EXTREME]:
            scores[MarketRegime.VOLATILE] = 0.5
            if micro_score > 0.7:
                scores[MarketRegime.VOLATILE] += 0.3
            if liquidity == LiquidityLevel.THIN:
                scores[MarketRegime.VOLATILE] += 0.2
        
        # QUIET
        if volatility == VolatilityLevel.LOW and liquidity == LiquidityLevel.THIN:
            scores[MarketRegime.QUIET] = 0.6
            if abs(momentum) < 0.2:
                scores[MarketRegime.QUIET] += 0.2
            if micro_score < 0.3:
                scores[MarketRegime.QUIET] += 0.2
        
        # BREAKOUT
        if abs(momentum) > 0.7 and trend_strength > 0.5:
            scores[MarketRegime.BREAKOUT] = abs(momentum) * 0.5 + trend_strength * 0.3
            if volatility in [VolatilityLevel.HIGH, VolatilityLevel.EXTREME]:
                scores[MarketRegime.BREAKOUT] += 0.2
        
        # REVERSAL
        # Detecta mudança de direção
        recent_prices = [p['price'] for p in list(self.price_history[symbol])[-20:]]
        if len(recent_prices) >= 20:
            first_half_trend = 1 if recent_prices[10] > recent_prices[0] else -1
            second_half_trend = 1 if recent_prices[-1] > recent_prices[10] else -1
            
            if first_half_trend != second_half_trend and abs(momentum) > 0.5:
                scores[MarketRegime.REVERSAL] = 0.5 + abs(momentum) * 0.3
                if micro_score > 0.6:
                    scores[MarketRegime.REVERSAL] += 0.2
        
        # Determina regime com maior score
        best_regime = max(scores.items(), key=lambda x: x[1])
        regime = best_regime[0]
        confidence = min(best_regime[1], 1.0)
        
        # Ajusta confiança baseado na consistência
        if regime == self.current_regime.get(symbol):
            confidence = min(confidence * 1.1, 1.0)  # Bonus por consistência
        else:
            confidence *= 0.9  # Penalidade por mudança
        
        return regime, confidence
    
    def get_regime_summary(self, symbol: str) -> Dict:
        """Retorna um resumo completo do regime de mercado."""
        return {
            'regime': self.current_regime.get(symbol, MarketRegime.RANGING),
            'confidence': self.regime_confidence.get(symbol, 0.5),
            'metrics': self.metrics.get(symbol, self._create_empty_metrics()),
            'recommendations': self._get_regime_recommendations(symbol)
        }
    
    def _get_regime_recommendations(self, symbol: str) -> List[str]:
        """Retorna recomendações baseadas no regime atual."""
        regime = self.current_regime.get(symbol, MarketRegime.RANGING)
        metrics = self.metrics.get(symbol, {})
        recommendations = []
        
        if regime == MarketRegime.TRENDING_UP:
            recommendations.append("Favorecer sinais de compra em pullbacks")
            recommendations.append("Usar stops mais largos para não sair prematuramente")
            if metrics.get('volatility') == VolatilityLevel.LOW:
                recommendations.append("Considerar aumentar tamanho de posição")
        
        elif regime == MarketRegime.TRENDING_DOWN:
            recommendations.append("Favorecer sinais de venda em rallies")
            recommendations.append("Ser mais agressivo com stops de proteção")
            if metrics.get('liquidity') == LiquidityLevel.THIN:
                recommendations.append("Cuidado com slippage em saídas")
        
        elif regime == MarketRegime.RANGING:
            recommendations.append("Operar reversões nos extremos do range")
            recommendations.append("Usar stops apertados")
            recommendations.append("Evitar trades no meio do range")
        
        elif regime == MarketRegime.VOLATILE:
            recommendations.append("Reduzir tamanho de posição")
            recommendations.append("Aguardar confirmações extras")
            recommendations.append("Evitar stops muito próximos")
        
        elif regime == MarketRegime.QUIET:
            recommendations.append("Mercado sem direção clara")
            recommendations.append("Considerar ficar de fora")
            recommendations.append("Aguardar aumento de atividade")
        
        elif regime == MarketRegime.BREAKOUT:
            recommendations.append("Seguir a direção do breakout")
            recommendations.append("Usar stops técnicos")
            recommendations.append("Considerar adicionar em pullbacks")
        
        elif regime == MarketRegime.REVERSAL:
            recommendations.append("Aguardar confirmação da reversão")
            recommendations.append("Não apressar entrada")
            recommendations.append("Usar gestão de risco rigorosa")
        
        return recommendations
    
    def get_adaptive_parameters(self, symbol: str) -> Dict[str, float]:
        """Retorna parâmetros adaptados ao regime atual."""
        regime = self.current_regime.get(symbol, MarketRegime.RANGING)
        metrics = self.metrics.get(symbol, {})
        
        params = {
            'signal_threshold_multiplier': 1.0,
            'stop_loss_multiplier': 1.0,
            'position_size_multiplier': 1.0,
            'confirmation_requirement': 'NORMAL'
        }
        
        # Ajusta baseado no regime
        if regime == MarketRegime.TRENDING_UP:
            params['signal_threshold_multiplier'] = 0.9  # Mais permissivo
            params['stop_loss_multiplier'] = 1.2  # Stops mais largos
            params['position_size_multiplier'] = 1.1
        
        elif regime == MarketRegime.TRENDING_DOWN:
            params['signal_threshold_multiplier'] = 0.9
            params['stop_loss_multiplier'] = 0.8  # Stops mais apertados
            params['position_size_multiplier'] = 0.9
        
        elif regime == MarketRegime.VOLATILE:
            params['signal_threshold_multiplier'] = 1.3  # Mais restritivo
            params['stop_loss_multiplier'] = 1.5  # Stops bem largos
            params['position_size_multiplier'] = 0.5  # Metade do tamanho
            params['confirmation_requirement'] = 'HIGH'
        
        elif regime == MarketRegime.QUIET:
            params['signal_threshold_multiplier'] = 1.5  # Muito restritivo
            params['position_size_multiplier'] = 0.7
        
        elif regime == MarketRegime.BREAKOUT:
            params['signal_threshold_multiplier'] = 0.8  # Permissivo
            params['stop_loss_multiplier'] = 1.0
            params['position_size_multiplier'] = 1.2
            params['confirmation_requirement'] = 'LOW'
        
        # Ajusta por volatilidade
        if metrics.get('volatility') == VolatilityLevel.EXTREME:
            params['position_size_multiplier'] *= 0.5
            params['stop_loss_multiplier'] *= 1.5
        
        # Ajusta por liquidez
        if metrics.get('liquidity') == LiquidityLevel.THIN:
            params['position_size_multiplier'] *= 0.7
            params['signal_threshold_multiplier'] *= 1.2
        
        return params