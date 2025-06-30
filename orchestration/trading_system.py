import time
import logging
import threading
import asyncio
from typing import Dict, Optional
from rich.console import Console
import gc

from application.interfaces.market_data_provider import IMarketDataProvider
from application.interfaces.system_event_bus import ISystemEventBus
from presentation.display.monitor_app import TextualMonitorDisplay
from config import settings
from orchestration.event_handlers import OrchestrationHandlers

# Configuração do logger para este módulo
logger = logging.getLogger(__name__)

class TradingSystem:
    """
    Classe principal que orquestra todo o sistema de trading.
    Versão adaptada para usar Textual em vez de Rich.Live.
    """

    def __init__(
        self,
        console: Console,
        market_provider: IMarketDataProvider,
        event_bus: ISystemEventBus,
        display: TextualMonitorDisplay,  # Mudança: agora espera TextualMonitorDisplay
        handlers: OrchestrationHandlers,
        operation_phases: Optional[Dict] = None
    ):
        self.console = console
        self.market_provider = market_provider
        self.event_bus = event_bus
        self.display = display
        self.handlers = handlers
        self.operation_phases = operation_phases or {}
        
        self.running = False
        self.current_phase = "INITIALIZATION"
        self.phase_start_time = None
        
        self.risk_manager = self.operation_phases.get('risk_management')
        self.handlers.subscribe_to_events()
        
        # Novos atributos para Textual
        self.textual_thread = None
        self.textual_loop = None

    def start(self):
        """Inicia o sistema de trading e seu loop principal."""
        logger.info("--- Sistema de Trading v7.0 iniciado ---")
        
        if not self.market_provider.connect():
            logger.critical("Não foi possível conectar à fonte de dados. Encerrando.")
            self.console.print("[bold red]Falha ao conectar à fonte de dados.[/bold red]")
            return

        self.running = True
        
        try:
            self._run_normal_operation()
        except KeyboardInterrupt:
            logger.warning("Sinal de interrupção (Ctrl+C) recebido. Encerrando o sistema.")
            self.console.print("\n[yellow]Interrupção pelo usuário. Encerrando...[/yellow]")
        except Exception as e:
            # Captura de segurança para qualquer erro crítico fora do loop principal
            logger.critical(f"Erro crítico irrecuperável no sistema: {e}", exc_info=True)
        finally:
            self._shutdown()

    def _run_normal_operation(self):
        """Executa a fase de operação normal do sistema."""
        self.current_phase = "NORMAL"
        self.phase_start_time = time.time()
        
        logger.info("Sistema entrou na fase de operação normal.")
        self.console.print("\n[green]▶️  Sistema em operação normal[/green]")
        self.console.print("[dim]Pressione Ctrl+C para encerrar[/dim]\n")
        
        update_interval = settings.SYSTEM_CONFIG.get('update_interval', 0.1)
        self.display.update_system_phase("NORMAL")

        # Inicia Textual em thread separada
        def run_textual():
            self.textual_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.textual_loop)
            self.textual_loop.run_until_complete(self.display.start())
        
        self.textual_thread = threading.Thread(target=run_textual, daemon=True)
        self.textual_thread.start()
        
        # Aguarda Textual iniciar
        time.sleep(2)
        
        # Loop principal (sem Live)
        loop_count = 0
        maintenance_interval = 600
        
        while self.running:
            try:
                start_time = time.perf_counter()
                
                market_data = self.market_provider.get_market_data()
                
                if market_data:
                    self.event_bus.publish("MARKET_DATA_UPDATED", market_data)

                    analysis_data = {
                        'arbitrage_stats': self.handlers.arbitrage_service.get_spread_statistics(),
                        'tape_summaries': {
                            'WDO': self.handlers.tape_reading_service.get_market_summary('WDO'),
                            'DOL': self.handlers.tape_reading_service.get_market_summary('DOL')
                        },
                        'risk_status': self.handlers.risk_management_service.get_risk_status() if self.risk_manager else None
                    }
                    
                    # Atualiza o display Textual
                    self.display.update(market_data, analysis_data)
                
                loop_count += 1
                if loop_count % maintenance_interval == 0:
                    self._perform_maintenance()
                
                if loop_count % 3600 == 0:
                    self._check_daily_reset()

                loop_duration = time.perf_counter() - start_time
                sleep_time = max(0, update_interval - loop_duration)
                time.sleep(sleep_time)
                
            except KeyboardInterrupt:
                # Se Ctrl+C for pressionado, interrompe o loop para iniciar o shutdown.
                raise
            except Exception as e:
                # ESTE É O BLOCO DE CAPTURA CORRIGIDO E MAIS IMPORTANTE
                logger.error(f"Erro inesperado no loop principal: {e}", exc_info=True)
                self.console.print(f"[bold red]ERRO DETECTADO: {e}. Detalhes completos salvos em 'logs/system.log'[/bold red]")
                
                # Força a escrita imediata nos arquivos de log para garantir que não se perca
                for handler in logging.getLogger().handlers:
                    handler.flush()
                    
                time.sleep(1) # Pausa por 1 segundo para evitar spam de erros

    def _perform_maintenance(self):
        """Realiza tarefas de manutenção periódica."""
        logger.debug("Executando ciclo de manutenção periódica...")
        gc.collect()
        self.event_bus.publish("MAINTENANCE_CYCLE", {'timestamp': time.time()})

    def _check_daily_reset(self):
        """Verifica e executa o reset de métricas diárias."""
        from datetime import datetime, time as dt_time
        now = datetime.now()
        
        # Define o horário de reset (ex: 18:00)
        reset_time = dt_time(18, 0)
        
        if now.time() >= reset_time and (not hasattr(self, '_last_daily_reset') or self._last_daily_reset.date() < now.date()):
            logger.info("Executando reset diário de métricas...")
            
            if self.risk_manager:
                self.risk_manager.reset_daily_metrics()
            
            self.event_bus.publish("DAILY_RESET", {'timestamp': now})
            self._last_daily_reset = now

    def stop(self):
        """Inicia a parada ordenada do sistema."""
        if self.running:
            logger.info("Sinal de parada recebido. Iniciando encerramento...")
            self.running = False
            self.current_phase = "STOPPING"

    def _shutdown(self):
        """Procedimento final de shutdown do sistema."""
        self.current_phase = "SHUTDOWN"
        logger.info("--- Iniciando procedimento de shutdown ---")
        
        try:
            # Para o display Textual primeiro
            if hasattr(self, 'display') and hasattr(self.display, 'stop'):
                logger.info("Parando interface Textual...")
                self.display.stop()
                
                # Aguarda thread do Textual terminar
                if self.textual_thread and self.textual_thread.is_alive():
                    self.textual_thread.join(timeout=2)
            
            # Fecha conexão com provider
            self.market_provider.close()
            
            # Emite evento de shutdown
            self.event_bus.publish("SYSTEM_SHUTDOWN", {'timestamp': time.time(), 'reason': 'normal'})
            
            # Aguarda um momento para processamento final de eventos de log
            time.sleep(1)
            
            # Flush final para garantir que todos os logs foram escritos
            for handler in logging.getLogger().handlers:
                handler.flush()
            
            self.console.print("[bold green]Sistema finalizado com sucesso.[/bold green]")
        except Exception as e:
            logger.error(f"Erro durante o shutdown: {e}", exc_info=True)
            self.console.print(f"[bold red]Erro durante o shutdown: {e}[/bold red]")