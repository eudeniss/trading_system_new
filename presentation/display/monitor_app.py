# presentation/display/monitor_app.py
"""
Sistema de Display usando Textual - Layout Otimizado
"""

from textual.app import App, ComposeResult
from textual.containers import Container, ScrollableContainer
from textual.widgets import Header, Footer, Label
from textual.binding import Binding
from textual.css.query import NoMatches

from collections import deque
from typing import Dict, Any, Optional

from domain.entities.market_data import MarketData
from domain.entities.signal import Signal, SignalLevel, SignalSource


class TradingMonitorApp(App):
    """Aplicação Textual principal - Layout Otimizado"""
    
    CSS = """
    Screen {
        background: $surface;
    }
    
    /* Header simples no topo */
    #header-container {
        height: 3;
        background: $panel;
        border: solid $primary;
        content-align: center middle;
    }
    
    /* Container principal - layout vertical */
    #main-container {
        layout: vertical;
    }
    
    /* Área de sinais táticos expandida - 50% da tela */
    #signals-area {
        height: 50%;
        border: solid $success;
        padding: 1;
        margin: 1;
    }
    
    /* Área de sinais estratégicos - 25% da tela */
    #strategic-signals-area {
        height: 25%;
        border: solid $accent;
        padding: 1;
        margin: 1;
    }
    
    /* Linha inferior com arbitragem e tape - 25% da tela */
    #bottom-panels-row {
        height: 25%;
        layout: horizontal;
        margin: 1;
    }
    
    /* Painéis inferiores menores */
    .bottom-panel {
        width: 1fr;
        border: solid $primary;
        padding: 1;
        margin: 0 1;
        overflow: hidden;
    }
    
    .panel-title {
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }
    
    #signals-list {
        height: 1fr;
        overflow-y: auto;
    }
    
    #strategic-signals-container {
        height: 1fr;
        overflow-y: auto;
    }
    
    .signal-item {
        margin-bottom: 0;  /* Reduzido para caber mais sinais */
    }
    
    .strategic-signal-card {
        border: solid $primary;
        margin-bottom: 1;
        padding: 0 1;  /* Padding reduzido */
    }
    
    .confidence-bar {
        height: 1;
    }
    
    .timer-warning {
        color: $warning;
    }
    
    .timer-critical {
        color: $error;
    }
    
    .dim {
        color: $text-disabled;
    }
    
    /* Conteúdo compacto nos painéis inferiores */
    #arbitrage-content, #tape-content {
        padding: 0;  /* Removido font-size inválido, usando padding menor */
    }
    """
    
    BINDINGS = [
        Binding("q", "quit", "Sair"),
        Binding("c", "clear_signals", "Limpar Sinais"),
        Binding("r", "refresh", "Atualizar"),
    ]
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.signals: deque[Signal] = deque(maxlen=100)
        self.strategic_signals: Dict[str, Any] = {}
        self.market_context = {
            'cvd_total': {'WDO': 0, 'DOL': 0},
            'momentum': {'WDO': 'NEUTRO', 'DOL': 'NEUTRO'},
            'pressure': {'WDO': 'EQUILIBRADO ⚖️', 'DOL': 'EQUILIBRADO ⚖️'},  # Atualizado
            'signals_today': 0,
            'risk_status': None
        }
    
    def compose(self) -> ComposeResult:
        """Cria o layout otimizado."""
        yield Header()
        
        # Header customizado simples
        with Container(id="header-container"):
            yield Label("", id="header-info")
        
        # Container principal
        with Container(id="main-container"):
            
            # Área de sinais táticos expandida (50% da tela)
            with Container(id="signals-area"):
                yield Label("📡 SINAIS ATIVOS", classes="panel-title")
                yield ScrollableContainer(Container(id="signals-list"))
            
            # Área de sinais estratégicos reduzida (25% da tela)
            with Container(id="strategic-signals-area"):
                yield Label("🎯 SINAIS ESTRATÉGICOS", classes="panel-title")
                yield ScrollableContainer(Container(id="strategic-signals-container"))
            
            # Linha inferior com arbitragem e tape (25% da tela)
            with Container(id="bottom-panels-row"):
                # Painel Arbitragem
                with Container(classes="bottom-panel", id="arbitrage-panel"):
                    yield Label("📊 ARBITRAGEM", classes="panel-title")
                    yield Container(id="arbitrage-content")
                
                # Painel Tape Reading
                with Container(classes="bottom-panel", id="tape-panel"):
                    yield Label("📈 TAPE READING", classes="panel-title")
                    yield Container(id="tape-content")
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Quando a aplicação é montada."""
        self.title = "Trading Monitor v7.0"
        self.sub_title = "Sistema sem persistência"
        self.update_header()
    
    def update_header(self):
        """Atualiza o header com informações resumidas."""
        cvd_wdo = self.market_context['cvd_total']['WDO']
        cvd_dol = self.market_context['cvd_total']['DOL']
        
        # Formato com bullet points (•) separando as seções
        header_text = (
            f"CVD: WDO [{'green' if cvd_wdo > 0 else 'red'}]{cvd_wdo:+d}[/] | "
            f"DOL [{'green' if cvd_dol > 0 else 'red'}]{cvd_dol:+d}[/]  •  "  # Bullet aqui
            f"Pressão: {self.market_context['pressure']['WDO']} | {self.market_context['pressure']['DOL']}  •  "  # Bullet aqui
            f"Sinais: {self.market_context['signals_today']}"
        )
        
        try:
            self.query_one("#header-info").update(header_text)
        except NoMatches:
            pass
    
    def update_display(self, market_data: MarketData, analysis_data: Dict[str, Any]):
        """Atualiza todos os painéis com novos dados."""
        # Atualiza contexto
        self._update_context(analysis_data)
        
        # Atualiza header
        self.update_header()
        
        # Atualiza painéis inferiores
        self._update_arbitrage_panel(analysis_data.get('arbitrage_stats'))
        self._update_tape_panel(analysis_data.get('tape_summaries', {}))
    
    def _update_arbitrage_panel(self, arb_stats: Optional[Dict]):
        """Atualiza painel de arbitragem - versão compacta."""
        content = self.query_one("#arbitrage-content")
        content.remove_children()
        
        if arb_stats:
            spread = arb_stats.get('current', 0.0)
            mean = arb_stats.get('mean', 0.0)
            std = arb_stats.get('std', 0.0)
            z_score = (spread - mean) / std if std > 0 else 0
            profit_reais = spread * 10
            
            color = "green" if profit_reais > 15 else "yellow" if profit_reais > 0 else "red"
            
            # Versão mais compacta
            content.mount(Label(f"[{color}]Spread: {spread:.2f} pts (R$ {profit_reais:.0f})[/{color}]"))
            
            z_color = "red" if abs(z_score) > 2 else "yellow" if abs(z_score) > 1 else "white"
            content.mount(Label(f"[{z_color}]Z-Score: {z_score:+.2f}[/{z_color}]"))
            
            # Barra visual compacta
            bar = self._create_z_score_bar(z_score)
            content.mount(Label(f"[dim]{bar}[/dim]"))
            
            # Estatísticas resumidas em uma linha
            content.mount(Label(f"[dim]μ:{mean:.1f} σ:{std:.1f} [{arb_stats.get('min', 0):.0f},{arb_stats.get('max', 0):.0f}][/dim]"))
        else:
            content.mount(Label("[dim]Aguardando dados...[/dim]"))
    
    def _update_tape_panel(self, tape_summaries: Dict):
        """Atualiza painel de tape reading - versão compacta."""
        content = self.query_one("#tape-content")
        content.remove_children()
        
        # Mostra os dois símbolos em formato mais compacto
        for symbol in ['WDO', 'DOL']:
            summary = tape_summaries.get(symbol, {})
            if summary:
                cvd = summary.get('cvd', 0)
                cvd_roc = summary.get('cvd_roc', 0)
                cvd_total = summary.get('cvd_total', 0)
                
                cvd_color = "green" if cvd > 0 else "red" if cvd < 0 else "white"
                roc_color = "yellow" if abs(cvd_roc) > 50 else "dim white"
                
                # Tudo em uma linha por símbolo
                line = (
                    f"[bold white]{symbol}:[/bold white] "
                    f"[{cvd_color}]CVD:{cvd:+d}[/{cvd_color}] "
                    f"[{roc_color}]({cvd_roc:+.0f}%)[/{roc_color}] "
                    f"[dim]Total:{cvd_total:+,}[/dim]"
                )
                content.mount(Label(line))
                
                # POC se disponível
                poc = summary.get('poc')
                if poc:
                    content.mount(Label(f"  [cyan]POC: {poc:.2f}[/cyan]"))
    
    def add_signal(self, signal: Signal):
        """Adiciona um novo sinal."""
        self.signals.appendleft(signal)
        self.market_context['signals_today'] += 1
        self._refresh_signals()
        self.update_header()
    
    def add_strategic_signal(self, strategic_signal: Dict[str, Any]):
        """Adiciona ou atualiza um sinal estratégico."""
        signal_id = strategic_signal.get('id')
        if signal_id:
            self.strategic_signals[signal_id] = strategic_signal
            self._refresh_strategic_signals()
    
    def remove_strategic_signal(self, signal_id: str):
        """Remove um sinal estratégico."""
        if signal_id in self.strategic_signals:
            del self.strategic_signals[signal_id]
            self._refresh_strategic_signals()
    
    def _refresh_strategic_signals(self):
        """Atualiza a exibição dos sinais estratégicos."""
        container = self.query_one("#strategic-signals-container")
        container.remove_children()
        
        if not self.strategic_signals:
            container.mount(Label("[dim]Nenhum sinal estratégico ativo[/dim]"))
            return
        
        # Ordena por confiança (maior primeiro)
        sorted_signals = sorted(
            self.strategic_signals.values(),
            key=lambda x: x.get('confidence', 0),
            reverse=True
        )
        
        # Mostra apenas 5 sinais com visual mais compacto
        for signal in sorted_signals[:5]:
            card = self._create_compact_strategic_card(signal)
            container.mount(card)
    
    def _create_compact_strategic_card(self, signal: Dict[str, Any]) -> Container:
        """Cria um card compacto para sinal estratégico."""
        card = Container(classes="strategic-signal-card")
        
        # Determina cores baseado na direção
        direction = signal.get('direction', 'COMPRA')
        direction_color = "green" if direction == "COMPRA" else "red"
        
        # Setup e confiança
        setup_type = signal.get('setup', 'UNKNOWN')
        confidence = signal.get('confidence', 0)
        confidence_pct = int(confidence * 100)
        
        # Linha 1: Setup + Direção + Confiança
        line1 = (
            f"[bold white]{setup_type}[/bold white] "
            f"[{direction_color}]{direction}[/{direction_color}] "
            f"[{self._get_confidence_color(confidence)}][{confidence_pct}%][/{self._get_confidence_color(confidence)}]"
        )
        card.mount(Label(line1))
        
        # Linha 2: Preços compactos
        entry = signal.get('entry', 0)
        stop = signal.get('stop', 0)
        targets = signal.get('targets', [])
        t1 = targets[0] if targets else 0
        
        line2 = f"E:{entry:.2f} S:[red]{stop:.2f}[/red] T1:[green]{t1:.2f}[/green]"
        card.mount(Label(line2))
        
        # Linha 3: Timer e confluência
        time_remaining = signal.get('time_remaining', '0:00')
        time_parts = time_remaining.split(':')
        minutes = int(time_parts[0]) if time_parts else 0
        timer_color = "white" if minutes >= 2 else "yellow" if minutes >= 1 else "red"
        
        conflict = signal.get('conflict', 'NO_CONFLICT')
        confluence_emoji = "✓" if conflict == "NO_CONFLICT" else "⚠️"
        
        line3 = f"[{timer_color}]⏱️ {time_remaining}[/{timer_color}] | DOL/WDO {confluence_emoji}"
        card.mount(Label(line3))
        
        return card
    
    def _get_confidence_color(self, confidence: float) -> str:
        """Retorna cor baseada no nível de confiança."""
        if confidence >= 0.8:
            return "green"
        elif confidence >= 0.6:
            return "yellow"
        else:
            return "orange1"
    
    def _refresh_signals(self):
        """Atualiza a lista de sinais."""
        container = self.query_one("#signals-list")
        container.remove_children()
        
        color_map = {
            SignalLevel.INFO: 'blue',
            SignalLevel.WARNING: 'yellow',
            SignalLevel.ALERT: 'red'
        }
        
        source_emoji = {
            SignalSource.ARBITRAGE: '💹',
            SignalSource.TAPE_READING: '📊',
            SignalSource.CONFLUENCE: '🔥',
            SignalSource.SYSTEM: '⚙️',
            SignalSource.MANIPULATION: '🚨',
            SignalSource.STRATEGIC: '🎯',
            SignalSource.DIVERGENCE_WARNING: '⚠️'
        }
        
        # Mostra até 20 sinais
        for signal in list(self.signals)[:20]:
            level_color = color_map.get(signal.level, 'white')
            emoji = source_emoji.get(signal.source, '📌')
            
            signal_text = (
                f"[cyan]{signal.timestamp.strftime('%H:%M:%S')}[/cyan] "
                f"{emoji} [{level_color}]{signal.message}[/{level_color}]"
            )
            
            container.mount(Label(signal_text, classes="signal-item"))
    
    def _update_context(self, context_data: Dict[str, Any]):
        """Atualiza o contexto de mercado."""
        if 'tape_summaries' in context_data:
            for symbol in ['WDO', 'DOL']:
                summary = context_data['tape_summaries'].get(symbol, {})
                self.market_context['cvd_total'][symbol] = summary.get('cvd_total', 0)
                self.market_context['momentum'][symbol] = self._determine_momentum(summary)
                self.market_context['pressure'][symbol] = self._determine_pressure(summary)
        
        if 'risk_status' in context_data:
            self.market_context['risk_status'] = context_data.get('risk_status')
    
    def _determine_momentum(self, summary: Dict) -> str:
        """Determina o momentum baseado no CVD ROC."""
        cvd_roc = summary.get('cvd_roc', 0)
        if cvd_roc > 50: return "📈"
        if cvd_roc < -50: return "📉"
        return "➡️"
    
    def _determine_pressure(self, summary: Dict) -> str:
        """Determina a pressão dominante com texto completo."""
        cvd = summary.get('cvd', 0)
        if cvd > 100: return "COMPRA FORTE 🟢"
        if cvd < -100: return "VENDA FORTE 🔴"
        if cvd > 50: return "COMPRA 🟢"
        if cvd < -50: return "VENDA 🔴"
        return "EQUILIBRADO ⚖️"
    
    def _create_z_score_bar(self, z_score: float) -> str:
        """Cria uma barra visual para o Z-Score."""
        bar_length = 15  # Reduzido
        center = bar_length // 2
        z_clamped = max(-3.0, min(3.0, z_score))
        position = int(center + (z_clamped / 3.0) * (center - 1))
        position = max(0, min(bar_length - 1, position))
        
        bar = ['━'] * bar_length
        bar[center] = '┃'
        bar[position] = '█'
        bar[0] = '['
        bar[-1] = ']'
        
        return "".join(bar)
    
    def action_clear_signals(self) -> None:
        """Limpa todos os sinais."""
        self.signals.clear()
        self._refresh_signals()
    
    def action_refresh(self) -> None:
        """Força uma atualização."""


class TextualMonitorDisplay:
    """
    Wrapper para integrar o Textual App com o sistema existente.
    """
    
    def __init__(self, console=None):
        self.app = TradingMonitorApp()
        self.running = False
    
    async def start(self):
        """Inicia a aplicação Textual."""
        self.running = True
        await self.app.run_async()
    
    def stop(self):
        """Para a aplicação."""
        self.running = False
        if self.app.is_running:
            self.app.exit()
    
    def update(self, market_data: MarketData, analysis_data: Dict[str, Any]):
        """Atualiza o display com novos dados."""
        if self.app.is_running:
            self.app.call_from_thread(
                self.app.update_display,
                market_data,
                analysis_data
            )
    
    def add_signal(self, signal: Signal):
        """Adiciona um novo sinal."""
        if self.app.is_running:
            self.app.call_from_thread(self.app.add_signal, signal)
    
    def add_strategic_signal(self, strategic_signal: Dict[str, Any]):
        """Adiciona ou atualiza um sinal estratégico."""
        if self.app.is_running:
            self.app.call_from_thread(self.app.add_strategic_signal, strategic_signal)
    
    def remove_strategic_signal(self, signal_id: str):
        """Remove um sinal estratégico."""
        if self.app.is_running:
            self.app.call_from_thread(self.app.remove_strategic_signal, signal_id)
    
    def update_system_phase(self, phase: str):
        """Atualiza a fase do sistema."""
        if self.app.is_running:
            self.app.sub_title = f"Fase: {phase}"