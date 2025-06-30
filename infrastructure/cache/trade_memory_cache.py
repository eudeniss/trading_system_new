# infrastructure/cache/trade_memory_cache.py
from collections import deque
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import threading
import logging

from domain.entities.trade import Trade
from domain.repositories.trade_cache import ITradeCache

logger = logging.getLogger(__name__)

class TradeMemoryCache(ITradeCache):
    """
    Implementação em memória do cache de trades.
    Thread-safe e otimizada para performance.
    """
    
    def __init__(self, max_size: int = 10000):
        """
        Args:
            max_size: Tamanho máximo do cache por símbolo
        """
        self.max_size = max_size
        self.cache: Dict[str, deque] = {}
        self.lock = threading.RLock()
        
        # Estatísticas
        self.stats = {
            'hits': 0,
            'misses': 0,
            'additions': 0,
            'evictions': 0
        }
        
        # Metadados
        self.metadata: Dict[str, Dict] = {}
        
        logger.info(f"TradeMemoryCache inicializado com max_size={max_size}")
    
    def add_trade(self, symbol: str, trade: Trade) -> None:
        """Adiciona um trade ao cache com thread safety."""
        with self.lock:
            if symbol not in self.cache:
                self.cache[symbol] = deque(maxlen=self.max_size)
                self.metadata[symbol] = {
                    'created_at': datetime.now(),
                    'last_update': datetime.now(),
                    'total_added': 0
                }
            
            # Verifica se vai haver eviction
            if len(self.cache[symbol]) == self.max_size:
                self.stats['evictions'] += 1
            
            self.cache[symbol].append(trade)
            self.stats['additions'] += 1
            
            # Atualiza metadados
            self.metadata[symbol]['last_update'] = datetime.now()
            self.metadata[symbol]['total_added'] += 1
    
    def add_trades(self, symbol: str, trades: List[Trade]) -> None:
        """Adiciona múltiplos trades de forma eficiente."""
        if not trades:
            return
            
        with self.lock:
            if symbol not in self.cache:
                self.cache[symbol] = deque(maxlen=self.max_size)
                self.metadata[symbol] = {
                    'created_at': datetime.now(),
                    'last_update': datetime.now(),
                    'total_added': 0
                }
            
            # Calcula quantos serão removidos por eviction
            current_size = len(self.cache[symbol])
            new_trades_count = len(trades)
            if current_size + new_trades_count > self.max_size:
                evictions = min(current_size, current_size + new_trades_count - self.max_size)
                self.stats['evictions'] += evictions
            
            # Adiciona todos de uma vez
            self.cache[symbol].extend(trades)
            self.stats['additions'] += new_trades_count
            
            # Atualiza metadados
            self.metadata[symbol]['last_update'] = datetime.now()
            self.metadata[symbol]['total_added'] += new_trades_count
    
    def get_recent_trades(self, symbol: str, count: int) -> List[Trade]:
        """Retorna últimos N trades de forma eficiente."""
        with self.lock:
            if symbol not in self.cache:
                self.stats['misses'] += 1
                return []
            
            self.stats['hits'] += 1
            
            # Otimização: se pedir todos ou mais, retorna lista completa
            cache_size = len(self.cache[symbol])
            if count >= cache_size:
                return list(self.cache[symbol])
            
            # Senão, retorna apenas o slice necessário
            return list(self.cache[symbol])[-count:]
    
    def get_all_trades(self, symbol: str) -> List[Trade]:
        """Retorna todos os trades em cache para um símbolo."""
        with self.lock:
            if symbol not in self.cache:
                self.stats['misses'] += 1
                return []
            
            self.stats['hits'] += 1
            return list(self.cache[symbol])
    
    def get_trades_by_time_window(self, symbol: str, seconds: int) -> List[Trade]:
        """Retorna trades dos últimos N segundos."""
        with self.lock:
            if symbol not in self.cache:
                self.stats['misses'] += 1
                return []
            
            self.stats['hits'] += 1
            
            cutoff_time = datetime.now() - timedelta(seconds=seconds)
            
            # Otimização: percorre de trás pra frente (mais recentes primeiro)
            result = []
            for trade in reversed(self.cache[symbol]):
                if trade.timestamp > cutoff_time:
                    result.append(trade)
                else:
                    break  # Trades mais antigos, pode parar
            
            # Retorna na ordem cronológica correta
            return list(reversed(result))
    
    def clear(self, symbol: Optional[str] = None) -> None:
        """Limpa o cache (todos os símbolos ou apenas um)."""
        with self.lock:
            if symbol:
                if symbol in self.cache:
                    trades_removed = len(self.cache[symbol])
                    del self.cache[symbol]
                    del self.metadata[symbol]
                    logger.info(f"Cache limpo para {symbol}: {trades_removed} trades removidos")
            else:
                total_removed = sum(len(trades) for trades in self.cache.values())
                self.cache.clear()
                self.metadata.clear()
                logger.info(f"Cache completamente limpo: {total_removed} trades removidos")
    
    def get_size(self, symbol: str) -> int:
        """Retorna quantidade de trades em cache para um símbolo."""
        with self.lock:
            return len(self.cache.get(symbol, []))
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas detalhadas do cache."""
        with self.lock:
            total_trades = sum(len(trades) for trades in self.cache.values())
            
            # Calcula taxa de hit
            total_requests = self.stats['hits'] + self.stats['misses']
            hit_rate = (self.stats['hits'] / total_requests * 100) if total_requests > 0 else 0
            
            # Info por símbolo
            symbols_info = {}
            for symbol, trades in self.cache.items():
                meta = self.metadata.get(symbol, {})
                symbols_info[symbol] = {
                    'count': len(trades),
                    'is_full': len(trades) == self.max_size,
                    'oldest_trade': trades[0].timestamp.isoformat() if trades else None,
                    'newest_trade': trades[-1].timestamp.isoformat() if trades else None,
                    'total_added': meta.get('total_added', 0),
                    'last_update': meta.get('last_update', datetime.now()).isoformat()
                }
            
            return {
                'basic_stats': {
                    'hits': self.stats['hits'],
                    'misses': self.stats['misses'],
                    'additions': self.stats['additions'],
                    'evictions': self.stats['evictions'],
                    'hit_rate': f"{hit_rate:.1f}%"
                },
                'cache_info': {
                    'total_trades': total_trades,
                    'max_size_per_symbol': self.max_size,
                    'symbols_cached': list(self.cache.keys()),
                    'memory_estimate_mb': (total_trades * 500) / (1024 * 1024)  # ~500 bytes por trade
                },
                'symbols': symbols_info
            }
    
    def get_memory_usage(self) -> Dict[str, float]:
        """Estima uso de memória do cache."""
        with self.lock:
            # Estimativa baseada em ~500 bytes por trade
            bytes_per_trade = 500
            
            usage = {}
            for symbol, trades in self.cache.items():
                usage[symbol] = (len(trades) * bytes_per_trade) / (1024 * 1024)  # MB
            
            usage['total_mb'] = sum(usage.values())
            return usage