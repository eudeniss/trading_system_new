# analyzers/patterns/defensive_filter.py
from typing import Dict, Tuple, Optional
from domain.entities.signal import Signal
from domain.entities.book import OrderBook
import logging

logger = logging.getLogger(__name__)

class DefensiveSignalFilter:
    """
    Filtra sinais baseado APENAS no que podemos VER no book.
    NÃO tentamos adivinhar quem está operando.
    """
    
    def __init__(self):
        self.manipulation_patterns = {
            'LAYERING': self._check_layering,
            'SPOOFING': self._check_spoofing,
            # REMOVIDO WASH_TRADE - impossível detectar sem saber quem opera!
        }
    
    def is_signal_safe(self, signal: Signal, book: Optional[OrderBook] = None, 
                      recent_trades: Optional[list] = None) -> Tuple[bool, Dict]:
        """Verifica se um sinal é seguro baseado APENAS no que vemos no BOOK."""
        risk_info = {
            'safe': True,
            'risks': [],
            'confidence': 1.0,
            'action_required': None,
            'details': []
        }
        
        # Verifica apenas manipulações VISÍVEIS NO BOOK
        if book:
            # LAYERING - podemos VER as ordens uniformes
            layering_result = self._check_layering(book)
            if layering_result['detected']:
                risk_info['risks'].append('LAYERING')
                risk_info['confidence'] *= 0.5
                risk_info['details'].append(layering_result)
            
            # SPOOFING - podemos VER o desbalanceamento extremo
            spoofing_result = self._check_spoofing(book)
            if spoofing_result['detected']:
                risk_info['risks'].append('SPOOFING')
                risk_info['confidence'] *= 0.7
                risk_info['details'].append(spoofing_result)
        
        risk_info['safe'] = len(risk_info['risks']) == 0
        
        # Define ação recomendada baseada no que VEMOS
        if not risk_info['safe']:
            risk_info['action_required'] = self._determine_action(risk_info)
            logger.warning(f"Manipulação VISÍVEL no book: {risk_info['risks']}")
        
        return risk_info['safe'], risk_info
    
    def _check_layering(self, book: OrderBook) -> Dict:
        """
        Detecta LAYERING - múltiplas ordens com volumes MUITO similares.
        Isso É VISÍVEL no book e É suspeito.
        """
        result = {
            'detected': False,
            'type': 'LAYERING',
            'side': None,
            'description': None
        }
        
        # Parâmetros mais rigorosos para evitar falsos positivos
        MIN_LEVELS = 4  # Precisa de pelo menos 4 níveis
        MIN_VOLUME = 80  # Volume mínimo relevante
        MAX_DEVIATION = 0.05  # Máximo 5% de desvio entre ordens
        
        # Verifica BIDS (compra)
        if len(book.bids) >= MIN_LEVELS:
            bid_volumes = [level.volume for level in book.bids[:6]]
            
            # Só analisa se TODOS os volumes são significativos
            if all(vol >= MIN_VOLUME for vol in bid_volumes[:MIN_LEVELS]):
                avg_vol = sum(bid_volumes[:MIN_LEVELS]) / MIN_LEVELS
                
                # Verifica se TODOS os níveis são MUITO próximos da média
                all_similar = all(
                    abs(vol - avg_vol) / avg_vol <= MAX_DEVIATION 
                    for vol in bid_volumes[:MIN_LEVELS]
                )
                
                if all_similar:
                    result['detected'] = True
                    result['side'] = 'BID'
                    result['description'] = (
                        f"BOOK SUSPEITO (Compra): {MIN_LEVELS}+ ordens "
                        f"IDÊNTICAS de ~{int(avg_vol)} contratos"
                    )
                    return result
        
        # Verifica ASKS (venda)
        if len(book.asks) >= MIN_LEVELS:
            ask_volumes = [level.volume for level in book.asks[:6]]
            
            if all(vol >= MIN_VOLUME for vol in ask_volumes[:MIN_LEVELS]):
                avg_vol = sum(ask_volumes[:MIN_LEVELS]) / MIN_LEVELS
                
                all_similar = all(
                    abs(vol - avg_vol) / avg_vol <= MAX_DEVIATION 
                    for vol in ask_volumes[:MIN_LEVELS]
                )
                
                if all_similar:
                    result['detected'] = True
                    result['side'] = 'ASK'
                    result['description'] = (
                        f"BOOK SUSPEITO (Venda): {MIN_LEVELS}+ ordens "
                        f"IDÊNTICAS de ~{int(avg_vol)} contratos"
                    )
                    return result
        
        return result
    
    def _check_spoofing(self, book: OrderBook) -> Dict:
        """
        Detecta SPOOFING - desbalanceamento EXTREMO no book.
        Isso É VISÍVEL e pode indicar ordens falsas.
        """
        result = {
            'detected': False,
            'type': 'SPOOFING',
            'side': None,
            'description': None
        }
        
        if not book.bids or not book.asks:
            return result
        
        # Soma volume dos primeiros níveis
        LEVELS_TO_CHECK = 5
        bid_volume = sum(level.volume for level in book.bids[:LEVELS_TO_CHECK])
        ask_volume = sum(level.volume for level in book.asks[:LEVELS_TO_CHECK])
        
        if bid_volume == 0 or ask_volume == 0:
            return result
        
        # Calcula proporção
        if bid_volume > ask_volume:
            ratio = bid_volume / ask_volume
            heavier_side = 'BID'
        else:
            ratio = ask_volume / bid_volume
            heavier_side = 'ASK'
        
        # Só marca como spoofing se MUITO desbalanceado
        SPOOFING_THRESHOLD = 8.0  # 8x mais volume de um lado
        
        if ratio >= SPOOFING_THRESHOLD:
            result['detected'] = True
            result['side'] = heavier_side
            
            if heavier_side == 'BID':
                result['description'] = (
                    f"BOOK ANORMAL: Compra {ratio:.1f}x maior que Venda - "
                    f"possíveis ordens FALSAS"
                )
            else:
                result['description'] = (
                    f"BOOK ANORMAL: Venda {ratio:.1f}x maior que Compra - "
                    f"possíveis ordens FALSAS"
                )
        
        return result
    
    def _determine_action(self, risk_info: Dict) -> str:
        """Determina ação baseada no que VEMOS no book."""
        risks = risk_info.get('risks', [])
        details = risk_info.get('details', [])
        
        # Ações baseadas em LAYERING
        if 'LAYERING' in risks:
            for detail in details:
                if detail.get('type') == 'LAYERING':
                    if detail.get('side') == 'BID':
                        return "⚠️ CUIDADO ao COMPRAR! Book com ordens suspeitas na compra"
                    elif detail.get('side') == 'ASK':
                        return "⚠️ CUIDADO ao VENDER! Book com ordens suspeitas na venda"
        
        # Ações baseadas em SPOOFING
        if 'SPOOFING' in risks:
            for detail in details:
                if detail.get('type') == 'SPOOFING':
                    if detail.get('side') == 'BID':
                        return "⚠️ BOOK PESADO na COMPRA! Possível manipulação"
                    elif detail.get('side') == 'ASK':
                        return "⚠️ BOOK PESADO na VENDA! Possível manipulação"
        
        return "⚠️ BOOK ANORMAL! Opere com extrema cautela"
    
    def get_book_analysis_explanation(self) -> str:
        """Explica o que o sistema analisa."""
        return """
🔍 ANÁLISE DO BOOK - O que VEMOS e o que significa:

1️⃣ ORDENS IDÊNTICAS (Layering)
   • O que vemos: 4+ ordens com volumes MUITO similares (ex: 100-100-100-100)
   • Por que é suspeito: Ordens naturais têm tamanhos variados
   • Ação: CUIDADO! Podem sumir quando o preço se aproximar

2️⃣ BOOK DESBALANCEADO (Spoofing)
   • O que vemos: Um lado com 8x+ mais volume que o outro
   • Por que é suspeito: Desequilíbrio extremo não é natural
   • Ação: AGUARDE! Book pode mudar rapidamente

❌ O que NÃO tentamos detectar:
   • Wash trades (impossível saber se é a mesma pessoa)
   • Quem está operando (não temos essa informação)
   • Intenções dos traders (apenas vemos as ordens)

✅ Focamos apenas no que É VISÍVEL e ANORMAL no book!
"""