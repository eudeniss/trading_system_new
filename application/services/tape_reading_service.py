# application/services/tape_reading_service.py - VERSÃO OTIMIZADA
from typing import List, Dict
import logging

from domain.entities.trade import Trade
from domain.entities.signal import Signal
from domain.entities.book import OrderBook
from domain.repositories.trade_cache import ITradeCache
from analyzers.patterns import (
    AbsorptionDetector, IcebergDetector, MomentumAnalyzer,
    PressureDetector, VolumeSpikeDetector
)
from analyzers.patterns.defensive_filter import DefensiveSignalFilter
from analyzers.statistics.cvd_calculator import CvdCalculator
from analyzers.formatters.signal_formatter import SignalFormatter
from application.interfaces.system_event_bus import ISystemEventBus
from config import settings

logger = logging.getLogger(__name__)


class TapeReadingService:
    """Versão otimizada - apenas detecção de padrões essenciais."""
    
    def __init__(self, event_bus: ISystemEventBus, trade_cache: ITradeCache):
        self.event_bus = event_bus
        self.trade_cache = trade_cache
        self.config = settings.TAPE_READING_CONFIG
        
        # Books atuais
        self.current_books = {'WDO': None, 'DOL': None}
        
        # Detectores unificados
        self.detectors = self._create_detectors()
        
        # CVD e formatadores
        self.cvd_calculators = {
            'WDO': CvdCalculator(),
            'DOL': CvdCalculator()
        }
        self.formatter = SignalFormatter()
        self.defensive_filter = DefensiveSignalFilter()
        
        logger.info("TapeReadingService otimizado inicializado")
    
    def _create_detectors(self) -> Dict[str, any]:
        """Cria detectores usando configuração centralizada."""
        cfg = self.config
        return {
            'absorption': AbsorptionDetector(
                concentration_threshold=cfg.get('concentration_threshold', 0.4),
                min_volume_threshold=cfg.get('absorption_threshold', 282)
            ),
            'iceberg': IcebergDetector(
                repetitions=cfg.get('iceberg_repetitions', 4),
                min_volume=cfg.get('iceberg_min_volume', 59)
            ),
            'momentum': MomentumAnalyzer(
                divergence_roc_threshold=cfg.get('divergence_threshold', 209),
                extreme_roc_threshold=cfg.get('extreme_threshold', 250)
            ),
            'pressure': PressureDetector(
                threshold=cfg.get('pressure_threshold', 0.75)
            ),
            'volume_spike': VolumeSpikeDetector(
                spike_multiplier=cfg.get('spike_multiplier', 3.0)
            )
        }
    
    def update_book(self, symbol: str, book: OrderBook):
        """Atualiza o book atual."""
        self.current_books[symbol] = book
    
    def process_new_trades(self, trades: List[Trade]) -> List[Signal]:
        """Processa trades e retorna sinais detectados."""
        signals = []
        
        # Agrupa por símbolo
        by_symbol = {}
        for trade in trades:
            if trade.symbol in ['WDO', 'DOL']:
                by_symbol.setdefault(trade.symbol, []).append(trade)
                self.cvd_calculators[trade.symbol].update_cumulative(trade)
        
        # Processa cada símbolo
        for symbol, symbol_trades in by_symbol.items():
            self.trade_cache.add_trades(symbol, symbol_trades)
            
            # Detecta padrões
            for signal in self._detect_patterns(symbol):
                # Filtra manipulação
                book = self.current_books.get(symbol)
                recent = self.trade_cache.get_recent_trades(symbol, 50)
                
                is_safe, risk_info = self.defensive_filter.is_signal_safe(signal, book, recent)
                
                if is_safe:
                    signals.append(signal)
                else:
                    self.event_bus.publish('MANIPULATION_DETECTED', {
                        'signal': signal, 
                        'risk_info': risk_info, 
                        'symbol': symbol
                    })
        
        return signals
    
    def _detect_patterns(self, symbol: str) -> List[Signal]:
        """Detecta padrões de forma otimizada."""
        # Cache de trades
        trades_100 = self.trade_cache.get_recent_trades(symbol, 100)
        trades_50 = trades_100[-50:] if len(trades_100) > 50 else trades_100
        trades_20 = trades_50[-20:] if len(trades_50) > 20 else trades_50
        
        if not trades_50:
            return []
        
        signals = []
        
        # Detecta cada padrão
        patterns = [
            ('absorption', trades_100),
            ('pressure', trades_20),
            ('volume_spike', trades_50),
        ]
        
        for detector_name, trades_subset in patterns:
            result = self.detectors[detector_name].detect(trades_subset)
            if result:
                signals.append(self.formatter.format(result, symbol))
        
        # Momentum com CVD
        cvd_roc = self.cvd_calculators[symbol].update_and_get_roc(trades_50, 15)
        momentum = self.detectors['momentum'].detect_divergence(trades_50, cvd_roc)
        if momentum:
            signals.append(self.formatter.format(momentum, symbol))
        
        # Iceberg (por trade)
        if trades_50:
            last_trade = trades_50[-1]
            iceberg = self.detectors['iceberg'].detect(last_trade, trades_50)
            if iceberg:
                signals.append(self.formatter.format(iceberg, symbol))
        
        return signals
    
    def get_market_summary(self, symbol: str) -> Dict:
        """Retorna resumo básico do mercado."""
        cvd_calc = self.cvd_calculators[symbol]
        recent = self.trade_cache.get_recent_trades(symbol, 50)
        
        if not recent:
            return {
                "symbol": symbol, 
                "cvd": 0, 
                "cvd_roc": 0.0, 
                "cvd_total": 0,
                "cache_size": 0
            }
        
        return {
            "symbol": symbol,
            "cvd": cvd_calc.calculate_cvd_for_trades(recent),
            "cvd_roc": cvd_calc.update_and_get_roc(recent, 15),
            "cvd_total": cvd_calc.get_cumulative_total(symbol),
            "cache_size": self.trade_cache.get_size(symbol)
        }