# main.py
import logging
import sys
from pathlib import Path
from rich.console import Console
from rich.logging import RichHandler
import signal
import time
from typing import Dict, Any

# --- CONFIGURAÇÃO DE LOGGING ---
log_dir = Path('logs')
log_dir.mkdir(exist_ok=True)

console = Console()

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.handlers.clear()

file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler = logging.FileHandler(log_dir / "system.log", mode='w', encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(file_formatter)

rich_handler = RichHandler(
    console=console,
    level=logging.WARNING,
    show_time=False,
    markup=True,
    rich_tracebacks=True
)

root_logger.addHandler(file_handler)
root_logger.addHandler(rich_handler)

def handle_uncaught_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.critical("EXCEÇÃO NÃO TRATADA", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_uncaught_exception

# Imports do sistema
from infrastructure.data_sources.excel_market_provider import ExcelMarketProvider
from infrastructure.logging.json_log_repository import JsonLogRepository
from infrastructure.event_bus.local_event_bus import LocalEventBus
from infrastructure.cache.trade_memory_cache import TradeMemoryCache
from infrastructure.setup_detector_registry import create_default_registry
from application.services.arbitrage_service import ArbitrageService
from application.services.tape_reading_service import TapeReadingService
from application.services.risk_management_service import RiskManagementService
from application.services.setup_lifecycle_manager import SetupLifecycleManager
from application.services.strategic_signal_service import StrategicSignalService
from application.services.position_manager import PositionManager
from analyzers.regimes.market_regime_detector import MarketRegimeDetector
from presentation.display.monitor_app import TextualMonitorDisplay
from orchestration.trading_system import TradingSystem
from orchestration.event_handlers import OrchestrationHandlers
from config import settings

logger = logging.getLogger(__name__)

class TradingSystemV7:
    """Classe principal que gerencia todos os componentes do sistema v7.1 - SPRINT 5 COMPLETO"""
    
    def __init__(self):
        self.console = console
        self.running = False
        self.components: Dict[str, Any] = {}
        self.operation_phase = "INITIALIZATION"
        
    def initialize_infrastructure(self) -> bool:
        """Fase 1: Inicializa componentes de infraestrutura."""
        try:
            self.console.print("[yellow]🔧 Inicializando infraestrutura...[/yellow]")
            
            # Event Bus
            self.event_bus = LocalEventBus()
            self.components['event_bus'] = self.event_bus
            
            # Cache Centralizado de Trades
            buffer_size = settings.TAPE_READING_CONFIG.get('buffer_size', 10000)
            self.trade_cache = TradeMemoryCache(max_size=buffer_size)
            self.components['trade_cache'] = self.trade_cache
            self.console.print(f"[green]✓ Cache centralizado criado (max: {buffer_size} trades/símbolo)[/green]")
            
            # Market Provider
            self.market_provider = ExcelMarketProvider()
            if not self.market_provider.connect():
                raise Exception("Falha ao conectar com Excel")
            self.components['market_provider'] = self.market_provider
            
            # Signal Repository
            log_dir_config = settings.SYSTEM_CONFIG.get('log_dir', 'logs')
            self.signal_repo = JsonLogRepository(log_dir=log_dir_config)
            self.components['signal_repo'] = self.signal_repo
            
            # Setup Detector Registry
            self.setup_registry = create_default_registry()
            self.components['setup_registry'] = self.setup_registry
            self.console.print("[green]✓ Registry de detectores criado[/green]")
            
            self.console.print("[green]✓ Infraestrutura inicializada[/green]")
            return True
            
        except Exception as e:
            logger.critical(f"Erro ao inicializar infraestrutura: {e}", exc_info=True)
            self.console.print(f"[red]✗ Erro na infraestrutura: {e}[/red]")
            return False
    
    def initialize_services(self) -> bool:
        """Fase 2: Inicializa serviços de aplicação."""
        try:
            self.console.print("[yellow]📊 Inicializando serviços...[/yellow]")
            
            # Arbitrage Service
            self.arbitrage_service = ArbitrageService()
            self.components['arbitrage_service'] = self.arbitrage_service
            
            # TapeReading Service COM CACHE
            self.tape_reading_service = TapeReadingService(
                event_bus=self.event_bus,
                trade_cache=self.trade_cache
            )
            self.components['tape_reading_service'] = self.tape_reading_service
                        
            # Risk Management Service
            settings.SYSTEM_CONFIG.get('risk_management', {})
            self.risk_management_service = RiskManagementService(
                event_bus=self.event_bus,
                state_manager=None,  # SEM STATE!
                config=settings.RISK_MANAGEMENT_CONFIG
            )
            self.components['risk_management_service'] = self.risk_management_service
            
            # Market Regime Detector
            self.market_regime_detector = MarketRegimeDetector()
            self.components['market_regime_detector'] = self.market_regime_detector
            
            # Lifecycle Manager para sinais estratégicos com configuração de timeouts
            setup_timeouts_config = settings.SYSTEM_CONFIG.get('setup_timeouts', None)
            self.lifecycle_manager = SetupLifecycleManager(
                self.event_bus,
                config={'setup_timeouts': setup_timeouts_config} if setup_timeouts_config else None
            )
            self.components['lifecycle_manager'] = self.lifecycle_manager
            self.lifecycle_manager.start()
            self.console.print("[green]✓ Lifecycle Manager iniciado com timeouts configurados[/green]")
            
            # Strategic Signal Service
            self.strategic_signal_service = StrategicSignalService(
                event_bus=self.event_bus,
                lifecycle_manager=self.lifecycle_manager,
                regime_detector=self.market_regime_detector
            )
            self.components['strategic_signal_service'] = self.strategic_signal_service
            self.console.print("[green]✓ Serviço de sinais estratégicos criado[/green]")

            # Position Manager
            position_config = {
                'max_positions': 3,
                'default_size': 1,
                'auto_manage': True,
                'trailing_stop_enabled': False
            }
            self.position_manager = PositionManager(
                event_bus=self.event_bus,
                config=position_config
            )
            self.components['position_manager'] = self.position_manager
            self.console.print("[green]✓ Position Manager criado[/green]")
            
            self.console.print("[green]✓ Serviços inicializados[/green]")
            return True
            
        except Exception as e:
            logger.critical(f"Erro ao inicializar serviços: {e}", exc_info=True)
            self.console.print(f"[red]✗ Erro nos serviços: {e}[/red]")
            return False
    
    def initialize_presentation(self) -> bool:
        """Fase 3: Inicializa camada de apresentação."""
        try:
            self.console.print("[yellow]🖥️  Inicializando interface...[/yellow]")
            
            self.display = TextualMonitorDisplay()
            self.components['display'] = self.display
            
            self.console.print("[green]✓ Interface inicializada (Layout v3.0 corrigido)[/green]")
            return True
            
        except Exception as e:
            logger.critical(f"Erro ao inicializar apresentação: {e}", exc_info=True)
            self.console.print(f"[red]✗ Erro na interface: {e}[/red]")
            return False
    
    def initialize_orchestration(self) -> bool:
        """Fase 4: Inicializa orquestração e handlers."""
        try:
            self.console.print("[yellow]🎭 Inicializando orquestração...[/yellow]")
            
            # Cria handlers com todos os serviços necessários
            self.handlers = OrchestrationHandlers(
                event_bus=self.event_bus, 
                signal_repo=self.signal_repo, 
                display=self.display,
                arbitrage_service=self.arbitrage_service, 
                tape_reading_service=self.tape_reading_service,
                strategic_signal_service=self.strategic_signal_service,
                risk_management_service=self.risk_management_service,
                market_regime_detector=self.market_regime_detector,
                position_manager=self.position_manager,
                state_manager=None  # SEM STATE!
            )
            
            # Cria sistema de trading principal
            self.trading_system = TradingSystem(
                console=self.console, 
                market_provider=self.market_provider, 
                event_bus=self.event_bus,
                display=self.display, 
                handlers=self.handlers,
                operation_phases={'risk_management': self.risk_management_service}
            )
            self.components['trading_system'] = self.trading_system
            
            self.console.print("[green]✓ Orquestração inicializada[/green]")
            self.console.print("[green]✓ Detectores de setup registrados com event_bus[/green]")
            return True
            
        except Exception as e:
            logger.critical(f"Erro ao inicializar orquestração: {e}", exc_info=True)
            self.console.print(f"[red]✗ Erro na orquestração: {e}[/red]")
            return False
    
    def phase_initialization(self) -> bool:
        """FASE 1: Inicialização do sistema."""
        self.console.print("\n[bold cyan]🚀 SISTEMA DE TRADING v7.1 - SPRINT 5 COMPLETO[/bold cyan]")
        self.console.print("[dim]Zero Persistence + Strategic Signals + Layout Corrigido[/dim]\n")
        
        if not self.initialize_infrastructure(): return False
        if not self.initialize_services(): return False
        if not self.initialize_presentation(): return False
        if not self.initialize_orchestration(): return False
        
        self.operation_phase = "NORMAL"
        return True
    
    def phase_normal_operation(self):
        """FASE 2: Operação normal do sistema."""
        try:
            self.console.print("\n[green]▶️  Sistema operacional com todos os componentes[/green]")
            self.console.print("[dim]Layout: Sinais Ativos em cima, Estratégicos embaixo[/dim]")
            self.console.print("[dim]Pressione Ctrl+C para encerrar[/dim]\n")
            
            # Log estatísticas do cache periodicamente
            self._start_cache_monitoring()
            
            # Log estatísticas dos detectores
            self._start_detector_monitoring()
            
            self.operation_phase = "NORMAL"
            
            if self.trading_system:
                self.trading_system.start()
        finally:
            self.operation_phase = "CLOSING"
    
    def _start_cache_monitoring(self):
        """Inicia monitoramento periódico do cache."""
        def log_cache_stats():
            while self.running:
                time.sleep(60)  # A cada minuto
                if hasattr(self, 'trade_cache'):
                    stats = self.trade_cache.get_stats()
                    basic = stats.get('basic_stats', {})
                    logger.info(
                        f"Cache Stats - Hits: {basic.get('hits', 0)}, "
                        f"Hit Rate: {basic.get('hit_rate', '0%')}, "
                        f"Total Trades: {stats.get('cache_info', {}).get('total_trades', 0)}"
                    )
        
        import threading
        monitor_thread = threading.Thread(target=log_cache_stats, daemon=True)
        monitor_thread.start()
    
    def _start_detector_monitoring(self):
        """Inicia monitoramento dos detectores de setup."""
        def log_detector_stats():
            while self.running:
                time.sleep(300)  # A cada 5 minutos
                if hasattr(self, 'strategic_signal_service'):
                    stats = self.strategic_signal_service.get_statistics()
                    logger.info(
                        f"Setup Detector Stats - "
                        f"Criados: {stats.get('signals_created', 0)}, "
                        f"Filtrados: {stats.get('signals_filtered', 0)}, "
                        f"Confluência OK: {stats.get('confluence_matches', 0)}, "
                        f"Conflitos: {stats.get('confluence_conflicts', 0)}"
                    )
                
                if hasattr(self, 'lifecycle_manager'):
                    lifecycle_stats = self.lifecycle_manager.get_statistics()
                    logger.info(
                        f"Lifecycle Stats - "
                        f"Ativos: {lifecycle_stats.get('active_signals', 0)}, "
                        f"Executados: {lifecycle_stats['historical_stats'].get('total_executed', 0)}, "
                        f"Expirados: {lifecycle_stats['historical_stats'].get('total_expired', 0)}"
                    )
        
        import threading
        monitor_thread = threading.Thread(target=log_detector_stats, daemon=True)
        monitor_thread.start()
    
    def phase_closing(self):
        """FASE 3: Encerramento ordenado do sistema."""
        self.console.print("\n[yellow]🔒 Encerrando sistema v7.1...[/yellow]")

        # Log estatísticas de posições
        if hasattr(self, 'position_manager') and self.position_manager:
            pos_stats = self.position_manager.get_statistics()
            daily_summary = self.position_manager.get_daily_summary()
            
            self.console.print("\n[cyan]💼 Estatísticas de Posições:[/cyan]")
            self.console.print(f"  • Total abertas: {pos_stats['total_opened']}")
            self.console.print(f"  • Total fechadas: {pos_stats['total_closed']}")
            self.console.print(f"  • Win rate: {pos_stats['win_rate']}")
            self.console.print(f"  • P&L total: R${pos_stats['total_pnl']:+.2f}")
            self.console.print(f"  • P&L hoje: R${daily_summary['pnl_today']:+.2f}")
            
            # Fecha posições abertas
            if pos_stats['open_positions'] > 0:
                self.console.print(f"[yellow]Fechando {pos_stats['open_positions']} posições abertas...[/yellow]")
                self.position_manager.close_all_positions("SYSTEM_SHUTDOWN")
        
        # Para o lifecycle manager primeiro
        if hasattr(self, 'lifecycle_manager') and self.lifecycle_manager:
            self.lifecycle_manager.stop()
            self.console.print("[green]✓ Lifecycle manager parado[/green]")
        
        # Log estatísticas finais dos detectores
        if hasattr(self, 'strategic_signal_service'):
            stats = self.strategic_signal_service.get_statistics()
            self.console.print("\n[cyan]🎯 Estatísticas dos Sinais Estratégicos:[/cyan]")
            self.console.print(f"   • Sinais criados: {stats.get('signals_created', 0)}")
            self.console.print(f"   • Sinais filtrados: {stats.get('signals_filtered', 0)}")
            self.console.print(f"   • Confluências perfeitas: {stats.get('confluence_matches', 0)}")
            self.console.print(f"   • Conflitos DOL/WDO: {stats.get('confluence_conflicts', 0)}")
            self.console.print(f"   • Sinais ativos ao fechar: {stats.get('active_signals', 0)}")
        
        # Log estatísticas do lifecycle
        if hasattr(self, 'lifecycle_manager'):
            lifecycle_stats = self.lifecycle_manager.get_statistics()
            hist = lifecycle_stats.get('historical_stats', {})
            self.console.print("\n[cyan]📈 Estatísticas do Ciclo de Vida:[/cyan]")
            self.console.print(f"   • Total criados: {hist.get('total_created', 0)}")
            self.console.print(f"   • Executados: {hist.get('total_executed', 0)}")
            self.console.print(f"   • Expirados: {hist.get('total_expired', 0)}")
            self.console.print(f"   • Stopados: {hist.get('total_stopped', 0)}")
            self.console.print(f"   • Alvos atingidos: {hist.get('total_targets_hit', 0)}")
        
        # Log estatísticas finais do cache
        if hasattr(self, 'trade_cache'):
            stats = self.trade_cache.get_stats()
            self.console.print("\n[cyan]📊 Estatísticas finais do cache:[/cyan]")
            
            basic = stats.get('basic_stats', {})
            self.console.print(f"   • Total de requisições: {basic.get('hits', 0) + basic.get('misses', 0)}")
            self.console.print(f"   • Taxa de acerto: {basic.get('hit_rate', '0%')}")
            self.console.print(f"   • Trades em cache: {stats.get('cache_info', {}).get('total_trades', 0)}")
            self.console.print(f"   • Evictions: {basic.get('evictions', 0)}")
        
        # Para o sistema de trading
        if hasattr(self, 'trading_system') and self.trading_system:
            self.trading_system.stop()

        # Fecha repositório de sinais
        if hasattr(self, 'signal_repo') and self.signal_repo:
            self.signal_repo.close()

        # Fecha conexão com market provider
        if hasattr(self, 'market_provider') and self.market_provider:
            self.market_provider.close()

        self.console.print("\n[green]✓ Sistema v7.1 encerrado com sucesso[/green]")
    
    def run(self):
        """Executa o sistema completo através das fases operacionais."""
        self.running = True
        
        def signal_handler(sig, frame):
            if self.running:
                self.console.print("\n[yellow]⏹️  Interrupção detectada, encerrando...[/yellow]")
                self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            if self.phase_initialization():
                self.phase_normal_operation()
            else:
                self.console.print("[bold red]❌ Falha na inicialização do sistema.[/bold red]")
        
        except Exception as e:
            logger.critical(f"Erro fatal no sistema: {e}", exc_info=True)
            self.console.print(f"[bold red]💥 Erro fatal: {e}[/bold red]")
        
        finally:
            self.phase_closing()

def print_banner(console: Console):
    """Exibe o banner do sistema."""
    banner = """
    ╔═══════════════════════════════════════════════════════════╗
    ║           TRADING SYSTEM v7.1 - SPRINT 5 COMPLETO         ║
    ║                                                           ║
    ║   📊 Zero Persistence + Centralized Trade Cache           ║
    ║   🎯 Strategic Signals + Setup Detectors                  ║
    ║   🔍 Risk Management + Market Regime Analysis             ║
    ║   📐 Layout Corrigido + Menu de Pressão                   ║
    ║                                                           ║
    ║   Interface:                                              ║
    ║   • Header com pressão DOL/WDO em tempo real              ║
    ║   • Sinais Ativos no topo (conforme template)             ║
    ║   • Sinais Estratégicos embaixo                           ║
    ║                                                           ║
    ║   Detectores Ativos:                                      ║
    ║   • Reversão Lenta (Absorção + CVD)                       ║
    ║   • Reversão Violenta (Spike + Momentum)                  ║
    ║   • Ignição de Breakout (Momentum + Pressão)              ║
    ║   • Rejeição de Pullback (Tendência + Confirmação)        ║
    ║   • Divergências (Preço vs Indicadores)                   ║
    ╚═══════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="bold cyan")

def verify_prerequisites(console: Console) -> bool:
    """Verifica pré-requisitos do sistema."""
    try:
        # Verifica configuração
        config_path = Path('config/config.yaml')
        if not config_path.exists():
            console.print(f"[bold red]❌ Arquivo de configuração não encontrado: {config_path}[/bold red]")
            return False
        
        excel_file = settings.EXCEL_CONFIG.get('file')
        if not excel_file:
            console.print("[bold red]❌ Caminho do Excel não configurado[/bold red]")
            return False
        
        # Info sobre cache
        buffer_size = settings.TAPE_READING_CONFIG.get('buffer_size', 10000)
        console.print(f"[green]✓ Cache configurado para {buffer_size:,} trades por símbolo[/green]")
        
        # Info sobre detectores
        console.print("[green]✓ 5 tipos de setup estratégico configurados[/green]")
        console.print("[green]✓ Sistema de filtros de contexto ativo[/green]")
        console.print("[green]✓ Confluência DOL/WDO habilitada[/green]")
        console.print("[green]✓ Layout corrigido conforme template v3.0[/green]")
        
        console.print("[yellow]📌 Sistema opera sem persistência - dados perdidos ao fechar[/yellow]")
        
        # Verifica diretório logs
        log_dir = Path('logs')
        if not log_dir.exists():
            console.print(f"[yellow]📁 Diretório logs será criado em: {log_dir.absolute()}[/yellow]")
        
        return True
        
    except Exception as e:
        console.print(f"[bold red]❌ Erro ao verificar pré-requisitos: {e}[/bold red]")
        return False

def main():
    """Ponto de entrada do sistema."""
    try:
        print_banner(console)
        
        if not verify_prerequisites(console):
            console.print("\n[yellow]Verifique a configuração e tente novamente.[/yellow]")
            return
        
        system = TradingSystemV7()
        system.run()
        
    except KeyboardInterrupt:
        console.print("\n[bold]Sistema finalizado pelo usuário.[/bold]")
    except Exception as e:
        logger.critical(f"Erro fatal não capturado no main: {e}", exc_info=True)
        console.print(f"[bold red]💥 Erro fatal. Verifique 'system.log'[/bold red]")
    finally:
        logging.shutdown()
        console.print("\n[bold]Aplicação finalizada.[/bold]")

if __name__ == "__main__":
    main()