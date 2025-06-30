# domain/entities/strategic_signal.py
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, Optional, List

class SetupType(str, Enum):
    """Tipos de setup estratégico."""
    REVERSAL_SLOW = "REVERSAL_SLOW"           # Reversão Lenta (absorção + inversão CVD)
    REVERSAL_VIOLENT = "REVERSAL_VIOLENT"     # Reversão Violenta (spike + momentum)
    BREAKOUT_IGNITION = "BREAKOUT_IGNITION"   # Ignição de Breakout
    PULLBACK_REJECTION = "PULLBACK_REJECTION" # Rejeição de Pullback
    DIVERGENCE_SETUP = "DIVERGENCE_SETUP"     # Setup de Divergência

class SignalState(str, Enum):
    """Estados do ciclo de vida do sinal."""
    PENDING = "PENDING"       # Aguardando confirmação
    ACTIVE = "ACTIVE"        # Ativo e operável
    EXECUTED = "EXECUTED"    # Executado (entrada realizada)
    EXPIRED = "EXPIRED"      # Expirado sem execução
    STOPPED = "STOPPED"      # Stopado
    TARGET_HIT = "TARGET_HIT" # Alvo atingido

class ConflictStatus(str, Enum):
    """Status de conflito entre DOL/WDO."""
    NO_CONFLICT = "NO_CONFLICT"          # Sem conflito
    MINOR_CONFLICT = "MINOR_CONFLICT"    # Conflito menor (aceitável)
    MAJOR_CONFLICT = "MAJOR_CONFLICT"    # Conflito maior (evitar)

class EntryType(str, Enum):
    """Tipo de entrada no trade."""
    MARKET = "MARKET"               # Entrada a mercado
    LIMIT = "LIMIT"                 # Entrada limitada
    STOP = "STOP"                   # Entrada stop
    ADAPTIVE = "ADAPTIVE"           # Entrada adaptativa

class StrategicSignal(BaseModel):
    """Representa um sinal estratégico de alta qualidade."""
    
    # Identificação
    id: str = Field(description="ID único do sinal")
    timestamp: datetime = Field(default_factory=datetime.now)
    symbol: str = Field(description="Símbolo principal (WDO ou DOL)")
    
    # Setup
    setup_type: SetupType
    direction: str = Field(description="COMPRA ou VENDA")
    state: SignalState = Field(default=SignalState.PENDING)
    
    # Preços
    entry_price: float = Field(gt=0, description="Preço de entrada calculado")
    entry_type: EntryType = Field(default=EntryType.LIMIT)
    stop_loss: float = Field(gt=0, description="Stop loss")
    targets: List[float] = Field(description="Lista de alvos (T1, T2, etc)")
    
    # Métricas
    confidence: float = Field(ge=0, le=1, description="Confiança do sinal (0-1)")
    risk_reward: float = Field(gt=0, description="Relação risco/retorno")
    
    # Confluência
    conflict_status: ConflictStatus = Field(default=ConflictStatus.NO_CONFLICT)
    confluence_factors: List[str] = Field(default_factory=list, description="Fatores de confluência")
    
    # Timing
    expiration_time: datetime = Field(description="Quando o sinal expira")
    time_to_expiry_seconds: int = Field(default=300, description="Segundos até expirar")
    
    # Detalhes do setup
    setup_details: Dict[str, Any] = Field(default_factory=dict)
    
    # Tracking
    created_by: str = Field(default="SYSTEM", description="Detector que criou o sinal")
    execution_price: Optional[float] = Field(default=None, description="Preço real de execução")
    execution_time: Optional[datetime] = Field(default=None)
    exit_price: Optional[float] = Field(default=None)
    exit_time: Optional[datetime] = Field(default=None)
    pnl: Optional[float] = Field(default=None, description="P&L realizado")
    
    class Config:
        frozen = False  # Permite mutação para atualizar estado
    
    def is_active(self) -> bool:
        """Verifica se o sinal está ativo e operável."""
        return self.state == SignalState.ACTIVE and datetime.now() < self.expiration_time
    
    def is_expired(self) -> bool:
        """Verifica se o sinal expirou."""
        return datetime.now() >= self.expiration_time
    
    def time_remaining(self) -> timedelta:
        """Retorna o tempo restante até expiração."""
        return max(self.expiration_time - datetime.now(), timedelta(0))
    
    def time_remaining_formatted(self) -> str:
        """Retorna o tempo restante formatado (MM:SS)."""
        remaining = self.time_remaining()
        minutes = int(remaining.total_seconds() // 60)
        seconds = int(remaining.total_seconds() % 60)
        return f"{minutes}:{seconds:02d}"
    
    def update_state(self, new_state: SignalState, **kwargs):
        """Atualiza o estado do sinal e campos relacionados."""
        self.state = new_state
        
        if new_state == SignalState.EXECUTED and 'execution_price' in kwargs:
            self.execution_price = kwargs['execution_price']
            self.execution_time = datetime.now()
        
        elif new_state in [SignalState.STOPPED, SignalState.TARGET_HIT] and 'exit_price' in kwargs:
            self.exit_price = kwargs['exit_price']
            self.exit_time = datetime.now()
            
            # Calcula P&L se possível
            if self.execution_price:
                if self.direction == "COMPRA":
                    self.pnl = (self.exit_price - self.execution_price) * 10  # Point value
                else:
                    self.pnl = (self.execution_price - self.exit_price) * 10
    
    def get_risk_points(self) -> float:
        """Calcula o risco em pontos."""
        if self.direction == "COMPRA":
            return self.entry_price - self.stop_loss
        else:
            return self.stop_loss - self.entry_price
    
    def get_reward_points(self, target_index: int = 0) -> float:
        """Calcula o retorno em pontos para um alvo específico."""
        if not self.targets or target_index >= len(self.targets):
            return 0
        
        target = self.targets[target_index]
        if self.direction == "COMPRA":
            return target - self.entry_price
        else:
            return self.entry_price - target
    
    def to_display_dict(self) -> Dict[str, Any]:
        """Retorna dicionário formatado para display."""
        return {
            'id': self.id,
            'setup': self.setup_type.value,
            'direction': self.direction,
            'entry': self.entry_price,
            'stop': self.stop_loss,
            'targets': self.targets,
            'confidence': self.confidence,
            'risk_reward': self.risk_reward,
            'time_remaining': self.time_remaining_formatted(),
            'state': self.state.value,
            'confluence': len(self.confluence_factors),
            'confluence_factors': self.confluence_factors,
            'conflict': self.conflict_status.value
        }