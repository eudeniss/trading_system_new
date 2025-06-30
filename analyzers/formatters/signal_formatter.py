# analyzers/formatters/signal_formatter.py
"""
Formatador simplificado de sinais.
Versão refatorada - Sprint 2.
"""

from typing import Dict
from domain.entities.signal import Signal, SignalSource, SignalLevel


class SignalFormatter:
    """
    Formata os dicionários brutos dos detectores em entidades Signal.
    Versão simplificada sem formatações complexas.
    """

    # Mapeamento de padrões para emojis
    PATTERN_EMOJIS = {
        "ESCORA_DETECTADA": "🛡️",
        "PACE_ANOMALY": "⚡",
        "DIVERGENCIA_BAIXA": "📉",
        "DIVERGENCIA_ALTA": "📈",
        "MOMENTUM_EXTREMO": "🚀",
        "ICEBERG": "🧊",
        "PRESSAO_COMPRA": "💹",
        "PRESSAO_VENDA": "💥",
        "VOLUME_SPIKE": "📊"
    }

    # Mapeamento de padrões para níveis
    PATTERN_LEVELS = {
        # Alta prioridade
        "ESCORA_DETECTADA": SignalLevel.ALERT,
        "DIVERGENCIA_BAIXA": SignalLevel.ALERT,
        "DIVERGENCIA_ALTA": SignalLevel.ALERT,
        "MOMENTUM_EXTREMO": SignalLevel.ALERT,
        "ICEBERG": SignalLevel.ALERT,
        "PRESSAO_COMPRA": SignalLevel.ALERT,
        "PRESSAO_VENDA": SignalLevel.ALERT,
        # Média prioridade
        "PACE_ANOMALY": SignalLevel.WARNING,
        "VOLUME_SPIKE": SignalLevel.WARNING
    }

    def format(self, raw_signal: Dict, symbol: str) -> Signal:
        """
        Converte um dicionário de sinal em uma entidade Signal estruturada.
        Versão simplificada.
        """
        pattern = raw_signal.get("pattern", "UNKNOWN")
        
        # Cria mensagem simplificada
        message = self._create_simple_message(pattern, symbol, raw_signal)
        
        # Determina nível baseado no padrão
        level = self.PATTERN_LEVELS.get(pattern, SignalLevel.INFO)

        # Adiciona o padrão original aos detalhes
        raw_signal['original_pattern'] = pattern

        return Signal(
            source=SignalSource.TAPE_READING,
            level=level,
            message=message,
            details={"symbol": symbol, **raw_signal}
        )

    def _create_simple_message(self, pattern: str, symbol: str, details: Dict) -> str:
        """
        Cria uma mensagem simples e clara para o sinal.
        Formato: [EMOJI] [AÇÃO] | [DESCRIÇÃO] [SYMBOL] [DETALHES-CHAVE]
        """
        emoji = self.PATTERN_EMOJIS.get(pattern, "📌")
        
        if pattern == "ESCORA_DETECTADA":
            direction = details.get('direction', 'COMPRA')
            level = details.get('level', 0.0)
            volume = details.get('volume', 0)
            return f"{emoji} {direction} | Absorção {symbol} @ {level:.2f} (Vol: {volume})"
        
        elif pattern == "DIVERGENCIA_ALTA":
            roc = details.get('cvd_roc', 0.0)
            return f"{emoji} COMPRA | Divergência Alta {symbol} (ROC: {roc:+.0f}%)"
            
        elif pattern == "DIVERGENCIA_BAIXA":
            roc = details.get('cvd_roc', 0.0)
            return f"{emoji} VENDA | Divergência Baixa {symbol} (ROC: {roc:+.0f}%)"
            
        elif pattern == "MOMENTUM_EXTREMO":
            direction = details.get('direction', 'NEUTRO')
            roc = details.get('cvd_roc', 0.0)
            return f"{emoji} {direction} | Momentum Extremo {symbol} (CVD: {roc:+.0f}%)"
            
        elif pattern == "ICEBERG":
            price = details.get('price', 0.0)
            reps = details.get('repetitions', 0)
            return f"{emoji} ICEBERG | Travamento {symbol} @ {price:.2f} ({reps}x)"
        
        elif pattern == "PRESSAO_COMPRA":
            ratio = details.get('ratio', 0.0) * 100
            return f"{emoji} COMPRA | Pressão {symbol} ({ratio:.0f}%)"
        
        elif pattern == "PRESSAO_VENDA":
            ratio = details.get('ratio', 0.0) * 100
            return f"{emoji} VENDA | Pressão {symbol} ({ratio:.0f}%)"
        
        elif pattern == "VOLUME_SPIKE":
            mult = details.get('multiplier', 0.0)
            direction = details.get('direction', 'NEUTRO')
            return f"{emoji} {direction} | Volume Spike {symbol} ({mult:.1f}x)"
            
        elif pattern == "PACE_ANOMALY":
            direction = details.get('direction', 'NEUTRO')
            pace = details.get('pace', 0.0)
            return f"{emoji} {direction} | Pace Anormal {symbol} ({pace:.0f} t/s)"

        # Padrão genérico
        return f"{emoji} {pattern} | Sinal {symbol}"