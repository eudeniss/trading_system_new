# analyzers/regimes/regime_translator.py
"""
Tradutor de regimes de mercado para português.
Fornece nomes e descrições em português para cada regime detectado.
"""
from typing import Dict
from analyzers.regimes.market_regime_detector import MarketRegime

class RegimeTranslator:
    """Traduz os regimes de mercado para português."""
    
    TRANSLATIONS = {
        MarketRegime.TRENDING_UP: "Tendência de Alta 📈",
        MarketRegime.TRENDING_DOWN: "Tendência de Baixa 📉", 
        MarketRegime.RANGING: "Mercado Lateral 🔄",
        MarketRegime.VOLATILE: "Alta Volatilidade ⚡",
        MarketRegime.QUIET: "Mercado Parado 😴",
        MarketRegime.BREAKOUT: "Rompimento 🚀",
        MarketRegime.REVERSAL: "Reversão 🔀"
    }
    
    DESCRIPTIONS = {
        MarketRegime.TRENDING_UP: "Movimento consistente de alta",
        MarketRegime.TRENDING_DOWN: "Movimento consistente de baixa",
        MarketRegime.RANGING: "Oscilando entre suporte e resistência",
        MarketRegime.VOLATILE: "Movimentos erráticos e amplitude alta",
        MarketRegime.QUIET: "Sem direção clara, baixo volume",
        MarketRegime.BREAKOUT: "Rompendo níveis importantes",
        MarketRegime.REVERSAL: "Mudando de direção (compra→venda ou venda→compra)"
    }
    
    @classmethod
    def translate(cls, regime: MarketRegime) -> str:
        """Retorna o nome traduzido do regime."""
        return cls.TRANSLATIONS.get(regime, str(regime))
    
    @classmethod
    def get_description(cls, regime: MarketRegime) -> str:
        """Retorna a descrição do regime."""
        return cls.DESCRIPTIONS.get(regime, "")
    
    @classmethod
    def get_full_info(cls, regime: MarketRegime) -> Dict[str, str]:
        """Retorna informações completas do regime."""
        return {
            'name': cls.translate(regime),
            'description': cls.get_description(regime),
            'original': regime.value
        }