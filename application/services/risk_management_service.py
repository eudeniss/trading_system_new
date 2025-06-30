# application/services/risk_management_service.py - VERSÃO CORRIGIDA
from typing import Dict, List, Tuple
from datetime import datetime, timedelta
from collections import deque
from enum import Enum
import logging

from domain.entities.signal import Signal, SignalLevel, SignalSource
from application.interfaces.system_event_bus import ISystemEventBus

logger = logging.getLogger(__name__)

class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class SignalQuality(str, Enum):
    POOR = "POOR"
    FAIR = "FAIR"
    GOOD = "GOOD"
    EXCELLENT = "EXCELLENT"

class RiskManagementService:
    """
    Serviço de gerenciamento de risco SEM PERSISTÊNCIA.
    Versão corrigida com cálculo dinâmico de risk level.
    """
    
    def __init__(self, event_bus: ISystemEventBus, state_manager=None, config: Dict = None):
        self.event_bus = event_bus
        # Ignora state_manager mesmo se passado
        self.config = config or {}
        
        # Configurações padrão
        self.max_signals_per_minute = self.config.get('max_signals_per_minute', 10)
        self.max_signals_per_hour = self.config.get('max_signals_per_hour', 100)
        self.max_confluence_per_hour = self.config.get('max_confluence_per_hour', 20)
        self.signal_quality_threshold = self.config.get('signal_quality_threshold', 0.4)
        
        # Circuit breakers
        self.consecutive_losses_limit = self.config.get('consecutive_losses_limit', 5)
        self.max_drawdown_percent = self.config.get('max_drawdown_percent', 2.0)
        self.emergency_stop_loss = self.config.get('emergency_stop_loss', 1000.0)
        
        # Tracking de sinais
        self.signal_history = deque(maxlen=1000)
        self.signal_timestamps = {
            'all': deque(maxlen=500),
            'confluence': deque(maxlen=100),
            'arbitrage': deque(maxlen=200),
            'tape_reading': deque(maxlen=300)
        }
        
        # Métricas de performance - SEMPRE COMEÇAM DO ZERO!
        self.performance_metrics = {
            'total_signals': 0,
            'signals_approved': 0,
            'signals_rejected': 0,
            'consecutive_losses': 0,
            'daily_pnl': 0.0,
            'peak_pnl': 0.0,
            'current_drawdown': 0.0,
            'risk_level': RiskLevel.LOW
        }
        
        # Estado de circuit breakers
        self.circuit_breakers = {
            'frequency': False,
            'quality': False,
            'drawdown': False,
            'consecutive_losses': False,
            'emergency': False
        }
        
        # Cache de análise de qualidade
        self.quality_cache = {}
        self.last_quality_check = datetime.now()
        
        # Subscrever a eventos
        self._subscribe_to_events()
        
        logger.info("RiskManagementService inicializado SEM persistência")
    
    def _subscribe_to_events(self):
        """Subscreve aos eventos relevantes."""
        self.event_bus.subscribe("SIGNAL_GENERATED", self._handle_signal_generated)
        self.event_bus.subscribe("TRADE_EXECUTED", self._handle_trade_executed)
        self.event_bus.subscribe("TRADE_CLOSED", self._handle_trade_closed)
        self.event_bus.subscribe("MARKET_DATA_UPDATED", self._handle_market_update)
    
    def _calculate_current_risk_level(self) -> RiskLevel:
        """
        NOVO MÉTODO: Calcula o nível de risco atual baseado nas métricas e circuit breakers.
        Este método deve ser chamado sempre que precisar do risk level atual.
        """
        # Verifica circuit breakers primeiro (mais crítico)
        if self.circuit_breakers['emergency']:
            return RiskLevel.CRITICAL
        
        if self.circuit_breakers['consecutive_losses'] or self.circuit_breakers['drawdown']:
            return RiskLevel.CRITICAL
        
        # Verifica métricas
        metrics = self.performance_metrics
        
        # Baseado em consecutive losses
        if metrics['consecutive_losses'] >= self.consecutive_losses_limit:
            return RiskLevel.CRITICAL
        elif metrics['consecutive_losses'] >= self.consecutive_losses_limit * 0.6:
            return RiskLevel.HIGH
        elif metrics['consecutive_losses'] >= self.consecutive_losses_limit * 0.3:
            return RiskLevel.MEDIUM
        
        # Baseado em drawdown
        if metrics['current_drawdown'] >= self.max_drawdown_percent:
            return RiskLevel.CRITICAL
        elif metrics['current_drawdown'] >= self.max_drawdown_percent * 0.7:
            return RiskLevel.HIGH
        elif metrics['current_drawdown'] >= self.max_drawdown_percent * 0.4:
            return RiskLevel.MEDIUM
        
        # Baseado em PnL diário
        if metrics['daily_pnl'] <= -self.emergency_stop_loss:
            return RiskLevel.CRITICAL
        elif metrics['daily_pnl'] <= -self.emergency_stop_loss * 0.5:
            return RiskLevel.HIGH
        elif metrics['daily_pnl'] <= -self.emergency_stop_loss * 0.2:
            return RiskLevel.MEDIUM
        
        return RiskLevel.LOW
    
    def evaluate_signal(self, signal: Signal) -> Tuple[bool, Dict]:
        """
        Avalia se um sinal deve ser aprovado baseado em critérios de risco.
        
        Returns:
            (approved, risk_assessment)
        """
        assessment = {
            'approved': False,
            'risk_level': RiskLevel.LOW,
            'quality': SignalQuality.POOR,
            'reasons': [],
            'recommendations': [],
            'timestamp': datetime.now()
        }
        
        # 1. Verifica circuit breakers
        cb_check = self._check_circuit_breakers()
        if not cb_check['all_clear']:
            assessment['approved'] = False
            assessment['risk_level'] = RiskLevel.CRITICAL
            assessment['reasons'].extend(cb_check['triggered'])
            return False, assessment
        
        # 2. Verifica frequência de sinais
        freq_check = self._check_signal_frequency(signal)
        if not freq_check['within_limits']:
            assessment['approved'] = False
            assessment['risk_level'] = RiskLevel.HIGH
            assessment['reasons'].append(f"Limite de frequência excedido: {freq_check['reason']}")
            return False, assessment
        
        # 3. Avalia qualidade do sinal
        quality = self._evaluate_signal_quality(signal)
        assessment['quality'] = quality['rating']
        
        if quality['score'] < self.signal_quality_threshold:
            assessment['approved'] = False
            assessment['risk_level'] = RiskLevel.MEDIUM
            assessment['reasons'].append(f"Qualidade insuficiente: {quality['score']:.2f}")
            assessment['recommendations'] = quality['improvements']
            return False, assessment
        
        # 4. Avalia risco contextual
        context_risk = self._evaluate_contextual_risk(signal)
        assessment['risk_level'] = context_risk['level']
        
        if context_risk['level'] in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            assessment['approved'] = False
            assessment['reasons'].append(f"Risco contextual alto: {context_risk['reason']}")
            return False, assessment
        
        # 5. Sinal aprovado
        assessment['approved'] = True
        assessment['recommendations'] = self._get_risk_recommendations(signal, quality, context_risk)
        
        # Registra aprovação
        self._record_signal_approval(signal, assessment)
        
        return True, assessment
    
    def _check_circuit_breakers(self) -> Dict:
        """Verifica estado dos circuit breakers."""
        result = {
            'all_clear': True,
            'triggered': []
        }
        
        # Verifica cada circuit breaker
        if self.circuit_breakers['emergency']:
            result['all_clear'] = False
            result['triggered'].append("Circuit breaker de emergência ativado")
        
        if self.circuit_breakers['consecutive_losses']:
            result['all_clear'] = False
            result['triggered'].append(f"Limite de perdas consecutivas ({self.consecutive_losses_limit}) atingido")
        
        if self.circuit_breakers['drawdown']:
            result['all_clear'] = False
            result['triggered'].append(f"Drawdown máximo ({self.max_drawdown_percent}%) excedido")
        
        if self.circuit_breakers['frequency']:
            result['all_clear'] = False
            result['triggered'].append("Frequência de sinais muito alta")
        
        if self.circuit_breakers['quality']:
            result['all_clear'] = False
            result['triggered'].append("Qualidade média dos sinais muito baixa")
        
        return result
    
    def _check_signal_frequency(self, signal: Signal) -> Dict:
        """Verifica limites de frequência de sinais."""
        now = datetime.now()
        signal.source.value
        
        # Conta sinais no último minuto
        one_minute_ago = now - timedelta(minutes=1)
        signals_last_minute = sum(1 for ts in self.signal_timestamps['all'] if ts > one_minute_ago)
        
        if signals_last_minute >= self.max_signals_per_minute:
            return {
                'within_limits': False,
                'reason': f"{signals_last_minute} sinais no último minuto (máx: {self.max_signals_per_minute})"
            }
        
        # Conta sinais na última hora
        one_hour_ago = now - timedelta(hours=1)
        signals_last_hour = sum(1 for ts in self.signal_timestamps['all'] if ts > one_hour_ago)
        
        if signals_last_hour >= self.max_signals_per_hour:
            return {
                'within_limits': False,
                'reason': f"{signals_last_hour} sinais na última hora (máx: {self.max_signals_per_hour})"
            }
        
        # Verifica limite específico para confluência
        if signal.source == SignalSource.CONFLUENCE:
            confluence_last_hour = sum(1 for ts in self.signal_timestamps['confluence'] if ts > one_hour_ago)
            if confluence_last_hour >= self.max_confluence_per_hour:
                return {
                    'within_limits': False,
                    'reason': f"{confluence_last_hour} sinais de confluência na última hora (máx: {self.max_confluence_per_hour})"
                }
        
        return {'within_limits': True, 'reason': 'OK'}
    
    def _evaluate_signal_quality(self, signal: Signal) -> Dict:
        """
        Avalia a qualidade de um sinal baseado em múltiplos critérios.
        """
        score = 0.0
        max_score = 0.0
        criteria = []
        improvements = []
        
        # 1. Fonte do sinal (peso 1.5)
        max_score += 1.5
        if signal.source == SignalSource.CONFLUENCE:
            score += 1.5
            criteria.append("Fonte: Confluência (+1.5)")
        elif signal.source == SignalSource.ARBITRAGE:
            score += 1.2
            criteria.append("Fonte: Arbitragem (+1.2)")
        elif signal.source == SignalSource.TAPE_READING:
            score += 0.8
            criteria.append("Fonte: Tape Reading (+0.8)")
        else:
            score += 0.4
            criteria.append("Fonte: Outro (+0.4)")
            improvements.append("Sinais de confluência têm maior confiabilidade")
        
        # 2. Nível de alerta (peso 0.8)
        max_score += 0.8
        if signal.level == SignalLevel.ALERT:
            score += 0.8
            criteria.append("Nível: Alert (+0.8)")
        elif signal.level == SignalLevel.WARNING:
            score += 0.5
            criteria.append("Nível: Warning (+0.5)")
        else:
            score += 0.2
            criteria.append("Nível: Info (+0.2)")
        
        # 3. Detalhes do sinal (peso 1.5)
        max_score += 1.5
        details = signal.details
        
        # Verifica profit/spread
        if 'profit_reais' in details or 'profit' in details:
            profit = details.get('profit_reais', details.get('profit', 0))
            if profit >= 50:
                score += 0.8
                criteria.append(f"Lucro alto: R${profit:.2f} (+0.8)")
            elif profit >= 20:
                score += 0.5
                criteria.append(f"Lucro médio: R${profit:.2f} (+0.5)")
            else:
                score += 0.2
                criteria.append(f"Lucro baixo: R${profit:.2f} (+0.2)")
                improvements.append("Busque oportunidades com maior potencial de lucro")
        
        # Verifica confirmações
        if 'confirmations' in details:
            num_confirmations = len(details.get('confirmations', []))
            if num_confirmations >= 3:
                score += 0.7
                criteria.append(f"{num_confirmations} confirmações (+0.7)")
            elif num_confirmations >= 2:
                score += 0.5
                criteria.append(f"{num_confirmations} confirmações (+0.5)")
            else:
                score += 0.2
                improvements.append("Aguarde mais confirmações para maior segurança")
        
        # 4. Padrão específico (peso 0.8)
        max_score += 0.8
        pattern = details.get('original_pattern', '')
        high_quality_patterns = ['ESCORA_DETECTADA', 'DIVERGENCIA_ALTA', 'DIVERGENCIA_BAIXA', 'ICEBERG']
        
        if pattern in high_quality_patterns:
            score += 0.8
            criteria.append(f"Padrão forte: {pattern} (+0.8)")
        elif pattern:
            score += 0.4
            criteria.append(f"Padrão: {pattern} (+0.4)")
        
        # Calcula score normalizado
        normalized_score = score / max_score if max_score > 0 else 0
        
        # Determina rating
        if normalized_score >= 0.8:
            rating = SignalQuality.EXCELLENT
        elif normalized_score >= 0.6:
            rating = SignalQuality.GOOD
        elif normalized_score >= 0.4:
            rating = SignalQuality.FAIR
        else:
            rating = SignalQuality.POOR
        
        return {
            'score': normalized_score,
            'rating': rating,
            'criteria': criteria,
            'improvements': improvements
        }
    
    def _evaluate_contextual_risk(self, signal: Signal) -> Dict:
        """Avalia risco baseado no contexto atual do mercado."""
        risk_factors = []
        risk_score = 0
        
        # CORREÇÃO: Usa o risk level ATUAL
        current_risk_level = self._calculate_current_risk_level()
        
        # Se já estamos em risco alto, aumenta o score base
        if current_risk_level == RiskLevel.CRITICAL:
            risk_score += 3
            risk_factors.append("Sistema em risco crítico")
        elif current_risk_level == RiskLevel.HIGH:
            risk_score += 2
            risk_factors.append("Sistema em risco alto")
        elif current_risk_level == RiskLevel.MEDIUM:
            risk_score += 1
            risk_factors.append("Sistema em risco médio")
        
        # 1. Verifica drawdown atual
        if self.performance_metrics['current_drawdown'] > self.max_drawdown_percent * 0.7:
            risk_score += 2
            risk_factors.append("Próximo do drawdown máximo")
        
        # 2. Verifica perdas consecutivas
        if self.performance_metrics['consecutive_losses'] >= self.consecutive_losses_limit * 0.7:
            risk_score += 2
            risk_factors.append("Muitas perdas consecutivas recentes")
        
        # 3. Verifica horário (evita horários de baixa liquidez)
        current_hour = datetime.now().hour
        if current_hour < 10 or current_hour > 16:
            risk_score += 1
            risk_factors.append("Horário de menor liquidez")
        
        # 4. Verifica volatilidade implícita do sinal
        if 'cvd_roc' in signal.details and abs(signal.details['cvd_roc']) > 150:
            risk_score += 1
            risk_factors.append("Volatilidade extrema detectada")
        
        # Determina nível de risco
        if risk_score >= 4:
            level = RiskLevel.CRITICAL
        elif risk_score >= 3:
            level = RiskLevel.HIGH
        elif risk_score >= 2:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW
        
        return {
            'level': level,
            'score': risk_score,
            'factors': risk_factors,
            'reason': '; '.join(risk_factors) if risk_factors else 'Risco normal'
        }
    
    def _get_risk_recommendations(self, signal: Signal, quality: Dict, context: Dict) -> List[str]:
        """Gera recomendações de gerenciamento de risco - SIMPLIFICADO."""
        recommendations = []
        
        # Apenas UMA recomendação principal baseada na qualidade
        if quality['rating'] == SignalQuality.EXCELLENT:
            recommendations.append("✅ Sinal de alta qualidade")
        elif quality['rating'] == SignalQuality.GOOD:
            recommendations.append("⚡ Sinal bom")
        
        # Não adiciona mais recomendações automáticas para evitar spam
        
        return recommendations
    
    def _record_signal_approval(self, signal: Signal, assessment: Dict):
        """Registra aprovação de sinal e atualiza métricas."""
        self.performance_metrics['total_signals'] += 1
        self.performance_metrics['signals_approved'] += 1
        
        # Adiciona timestamp
        now = datetime.now()
        self.signal_timestamps['all'].append(now)
        
        source_key = signal.source.value.lower()
        if source_key in self.signal_timestamps:
            self.signal_timestamps[source_key].append(now)
        
        # Adiciona ao histórico
        self.signal_history.append({
            'signal': signal,
            'assessment': assessment,
            'timestamp': now
        })
        
        # Emite evento de aprovação
        self.event_bus.publish("SIGNAL_APPROVED", {
            'signal': signal,
            'assessment': assessment
        })
    
    def _handle_signal_generated(self, signal: Signal):
        """Handler para sinais gerados - avalia automaticamente."""
        approved, assessment = self.evaluate_signal(signal)
        
        if not approved:
            self.performance_metrics['signals_rejected'] += 1
            logger.info(f"Sinal rejeitado: {assessment['reasons']}")
            
            # Emite evento de rejeição
            self.event_bus.publish("SIGNAL_REJECTED", {
                'signal': signal,
                'assessment': assessment
            })
    
    def _handle_trade_executed(self, trade_data: Dict):
        """Handler para trades executados."""
        # Reset consecutive losses se for um trade
        if self.performance_metrics['consecutive_losses'] > 0:
            logger.info("Trade executado - resetando contador de perdas consecutivas")
    
    def _handle_trade_closed(self, trade_result: Dict):
        """Handler para trades fechados - atualiza métricas."""
        pnl = trade_result.get('pnl', 0)
        
        # Atualiza PnL diário
        self.performance_metrics['daily_pnl'] += pnl
        
        # Atualiza peak e drawdown
        if self.performance_metrics['daily_pnl'] > self.performance_metrics['peak_pnl']:
            self.performance_metrics['peak_pnl'] = self.performance_metrics['daily_pnl']
        
        drawdown = self.performance_metrics['peak_pnl'] - self.performance_metrics['daily_pnl']
        drawdown_pct = (drawdown / self.performance_metrics['peak_pnl'] * 100) if self.performance_metrics['peak_pnl'] > 0 else 0
        self.performance_metrics['current_drawdown'] = drawdown_pct
        
        # Atualiza consecutive losses
        if pnl < 0:
            self.performance_metrics['consecutive_losses'] += 1
        else:
            self.performance_metrics['consecutive_losses'] = 0
        
        # Verifica circuit breakers
        self._update_circuit_breakers()
    
    def _handle_market_update(self, market_data: Dict):
        """Handler para atualizações de mercado - pode ajustar parâmetros."""
    
    def _update_circuit_breakers(self):
        """Atualiza estado dos circuit breakers."""
        # Consecutive losses
        self.circuit_breakers['consecutive_losses'] = (
            self.performance_metrics['consecutive_losses'] >= self.consecutive_losses_limit
        )
        
        # Drawdown
        self.circuit_breakers['drawdown'] = (
            self.performance_metrics['current_drawdown'] >= self.max_drawdown_percent
        )
        
        # Emergency stop
        self.circuit_breakers['emergency'] = (
            self.performance_metrics['daily_pnl'] <= -self.emergency_stop_loss
        )
        
        # Log se algum circuit breaker foi acionado
        for breaker, active in self.circuit_breakers.items():
            if active:
                logger.warning(f"Circuit breaker acionado: {breaker}")
    
    def get_risk_status(self) -> Dict:
        """Retorna status atual do gerenciamento de risco - CORRIGIDO."""
        # CORREÇÃO: Calcula risk level ATUAL
        current_risk_level = self._calculate_current_risk_level()
        
        # Atualiza no dicionário para consistência
        self.performance_metrics['risk_level'] = current_risk_level
        
        # Calcula taxa de aprovação
        total = self.performance_metrics['total_signals']
        approval_rate = (self.performance_metrics['signals_approved'] / total * 100) if total > 0 else 0
        
        return {
            'risk_level': current_risk_level,  # USA O CALCULADO!
            'circuit_breakers': self.circuit_breakers.copy(),
            'metrics': {
                'total_signals': total,
                'approval_rate': f"{approval_rate:.1f}%",
                'consecutive_losses': self.performance_metrics['consecutive_losses'],
                'daily_pnl': f"R${self.performance_metrics['daily_pnl']:.2f}",
                'current_drawdown': f"{self.performance_metrics['current_drawdown']:.1f}%"
            },
            'active_breakers': [k for k, v in self.circuit_breakers.items() if v]
        }
    
    def reset_daily_metrics(self):
        """Reset métricas diárias."""
        logger.info("Resetando métricas diárias de risco")
        
        self.performance_metrics['daily_pnl'] = 0.0
        self.performance_metrics['peak_pnl'] = 0.0
        self.performance_metrics['current_drawdown'] = 0.0
        
        # Reset alguns circuit breakers
        self.circuit_breakers['emergency'] = False
        
        # Limpa timestamps antigos
        cutoff = datetime.now() - timedelta(hours=24)
        for key in self.signal_timestamps:
            self.signal_timestamps[key] = deque(
                (ts for ts in self.signal_timestamps[key] if ts > cutoff),
                maxlen=self.signal_timestamps[key].maxlen
            )
    
    def manual_override(self, breaker: str, active: bool, reason: str = ""):
        """Permite override manual de circuit breakers."""
        if breaker in self.circuit_breakers:
            old_state = self.circuit_breakers[breaker]
            self.circuit_breakers[breaker] = active
            
            logger.warning(f"Override manual: {breaker} {'ativado' if active else 'desativado'} (era: {old_state}). Razão: {reason}")
            
            self.event_bus.publish("RISK_OVERRIDE", {
                'breaker': breaker,
                'old_state': old_state,
                'new_state': active,
                'reason': reason,
                'timestamp': datetime.now()
            })
    
    def simulate_loss_for_testing(self, amount: float = 50):
        """
        MÉTODO DE TESTE: Simula uma perda para testar mudança de risk level.
        NÃO USE EM PRODUÇÃO!
        """
        logger.warning(f"TESTE: Simulando perda de R${amount}")
        self._handle_trade_closed({'pnl': -amount})
        
    def get_detailed_status(self) -> Dict:
        """Retorna status detalhado para debug."""
        current_risk = self._calculate_current_risk_level()
        
        return {
            'current_risk_level': current_risk.value,
            'performance_metrics': self.performance_metrics.copy(),
            'circuit_breakers': self.circuit_breakers.copy(),
            'thresholds': {
                'consecutive_losses_limit': self.consecutive_losses_limit,
                'max_drawdown_percent': self.max_drawdown_percent,
                'emergency_stop_loss': self.emergency_stop_loss
            },
            'signal_stats': {
                'total': self.performance_metrics['total_signals'],
                'approved': self.performance_metrics['signals_approved'],
                'rejected': self.performance_metrics['signals_rejected']
            }
        }