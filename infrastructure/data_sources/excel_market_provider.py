# infrastructure/data_sources/excel_market_provider.py
import xlwings as xw
from datetime import datetime
import logging
from typing import Optional, List, Dict
from pathlib import Path

from domain.entities.trade import Trade, TradeSide
from domain.entities.book import OrderBook, BookLevel
from domain.entities.market_data import MarketData, MarketSymbolData
from application.interfaces.market_data_provider import IMarketDataProvider
from config import settings

logger = logging.getLogger(__name__)

class ExcelMarketProvider(IMarketDataProvider):
    """Implementação de IMarketDataProvider que lê dados de um arquivo Excel."""
    def __init__(self):
        self.wb: Optional[xw.Book] = None
        self.sheet: Optional[xw.Sheet] = None
        self.connected = False
        self.config = {
            'WDO': {'trades': settings.WDO_CONFIG.get('trades', {}), 'book': settings.WDO_CONFIG.get('book', {})},
            'DOL': {'trades': settings.DOL_CONFIG.get('trades', {}), 'book': settings.DOL_CONFIG.get('book', {})}
        }
        # Debug mode - set to True to log raw data
        self.debug_mode = False
        self.debug_counter = 0

    def connect(self) -> bool:
        try:
            file_path = settings.EXCEL_CONFIG.get('file')
            sheet_name = settings.EXCEL_CONFIG.get('sheet')
            if not file_path or not sheet_name:
                logger.error("Caminho do arquivo ou nome da planilha não definidos em config.yaml")
                return False
            file_name = Path(file_path).name
            try:
                self.wb = xw.Book(file_name)
                logger.info(f"Conectado à instância EXISTENTE de '{file_name}'")
            except Exception:
                logger.warning(f"Não foi possível conectar a uma instância aberta de '{file_name}'. Tentando abrir pelo caminho...")
                self.wb = xw.Book(file_path)
                logger.info(f"Arquivo '{file_path}' aberto com sucesso.")
            self.sheet = self.wb.sheets[sheet_name]
            self.connected = True
            return True
        except Exception as e:
            logger.error(f"Falha CRÍTICA ao conectar ao Excel: {e}", exc_info=True)
            if "Cannot open two workbooks" in str(e) or "Filter Keys" in str(e):
                logger.error("DICA: Este erro pode ocorrer se houver múltiplas instâncias do Excel abertas ou um conflito. Feche TODAS as janelas do Excel, abra a planilha manualmente e execute o script novamente.")
            return False

    def get_market_data(self) -> Optional[MarketData]:
        if not self.connected:
            return None
        timestamp = datetime.now()
        market_data_map: Dict[str, MarketSymbolData] = {}
        for symbol in ['WDO', 'DOL']:
            trades = self._read_trades(symbol)
            book = self._read_book(symbol)
            last_price = self._calculate_mid_price(book)
            total_volume = sum(t.volume for t in trades)
            market_data_map[symbol] = MarketSymbolData(
                trades=trades,
                book=book,
                last_price=last_price,
                total_volume=total_volume
            )
        return MarketData(timestamp=timestamp, data=market_data_map)

    def _read_trades(self, symbol: str) -> List[Trade]:
        if not self.sheet:
            return []
        try:
            trade_config = self.config[symbol]['trades']
            column_map = trade_config['columns'] 
            data = self.sheet.range(trade_config['range']).value
            
            # Debug: log first few rows of data
            if self.debug_mode and self.debug_counter < 3:
                logger.debug(f"Raw trade data for {symbol} (first 5 rows):")
                for i, row in enumerate(data[:5]):
                    logger.debug(f"Row {i}: {row}")
                self.debug_counter += 1
            
            trades = []
            now = datetime.now()
            
            for idx, row in enumerate(data):
                if row is None or row[0] is None:
                    continue
                
                try:
                    # Valida e converte os valores
                    price = float(row[column_map['price']])
                    volume = int(row[column_map['volume']])
                    
                    # Só adiciona se preço E volume forem maiores que zero
                    if price > 0 and volume > 0:
                        time_str = str(row[column_map['time']])
                        if '.' not in time_str:
                            time_str = f"{time_str}.{idx:03d}"
                        
                        trades.append(Trade(
                            symbol=symbol,
                            time_str=time_str,
                            side=self._normalize_side(row[column_map['side']]),
                            price=price,
                            volume=volume,
                            timestamp=now
                        ))
                except (ValueError, TypeError) as e:
                    # Log apenas em debug mode para evitar spam
                    if self.debug_mode:
                        logger.debug(f"Ignorando linha {idx} com dados inválidos: {row} - Erro: {e}")
                    continue
                    
            return trades
        except Exception as e:
            logger.error(f"Erro ao ler trades de {symbol}: {e}", exc_info=True)
            return []

    def _read_book(self, symbol: str) -> OrderBook:
        if not self.sheet:
            return OrderBook()
        try:
            book_config = self.config[symbol]['book']
            bid_data = self.sheet.range(book_config['bid_range']).value
            
            # Debug: log first few rows of bid data
            if self.debug_mode and self.debug_counter < 6:
                logger.debug(f"Raw bid data for {symbol} (first 3 rows):")
                for i, row in enumerate(bid_data[:3]):
                    logger.debug(f"Bid row {i}: {row}")
            
            # Filtrar e validar dados de bid
            bids = []
            for r in bid_data:
                if r[3] is not None:
                    try:
                        price = float(r[3])
                        volume = int(r[2] or 0)
                        # Só adiciona se o preço for maior que 0
                        if price > 0:
                            bids.append(BookLevel(price=price, volume=volume))
                    except (ValueError, TypeError):
                        # Ignora valores que não podem ser convertidos
                        continue
            
            ask_data = self.sheet.range(book_config['ask_range']).value
            
            # Debug: log first few rows of ask data
            if self.debug_mode and self.debug_counter < 6:
                logger.debug(f"Raw ask data for {symbol} (first 3 rows):")
                for i, row in enumerate(ask_data[:3]):
                    logger.debug(f"Ask row {i}: {row}")
                self.debug_counter += 1
            
            # Filtrar e validar dados de ask
            asks = []
            for r in ask_data:
                if r[0] is not None:
                    try:
                        price = float(r[0])
                        volume = int(r[1] or 0)
                        # Só adiciona se o preço for maior que 0
                        if price > 0:
                            asks.append(BookLevel(price=price, volume=volume))
                    except (ValueError, TypeError):
                        # Ignora valores que não podem ser convertidos
                        continue
            
            return OrderBook(bids=bids, asks=asks)
        except Exception as e:
            logger.error(f"Erro ao ler book de {symbol}: {e}", exc_info=True)
            return OrderBook()

    def _normalize_side(self, side_str: str) -> TradeSide:
        if not side_str:
            return TradeSide.UNKNOWN
        side_upper = str(side_str).upper()
        if 'COMPRADOR' in side_upper or 'COMPRA' in side_upper:
            return TradeSide.BUY
        elif 'VENDEDOR' in side_upper or 'VENDA' in side_upper:
            return TradeSide.SELL
        return TradeSide.UNKNOWN
        
    def _calculate_mid_price(self, book: OrderBook) -> float:
        if book.best_bid > 0 and book.best_ask > 0:
            return (book.best_bid + book.best_ask) / 2
        return 0.0

    def close(self):
        self.connected = False
        self.wb = None
        self.sheet = None
        logger.info("Conexão com Excel fechada")
    
    def enable_debug(self, enabled: bool = True):
        """Ativa ou desativa o modo debug para log de dados brutos."""
        self.debug_mode = enabled
        self.debug_counter = 0
        if enabled:
            logger.info("Modo debug ativado no ExcelMarketProvider")
        else:
            logger.info("Modo debug desativado no ExcelMarketProvider")