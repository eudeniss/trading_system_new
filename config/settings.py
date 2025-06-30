# config/settings.py
"""Carregador de configurações do YAML."""
import yaml
from pathlib import Path

# Carrega configurações do YAML
config_path = Path(__file__).parent / 'config.yaml'
if not config_path.exists():
    raise FileNotFoundError(f"Arquivo {config_path} não encontrado!")

with open(config_path, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# Acesso fácil às seções de configuração
EXCEL_CONFIG = config.get('excel', {})
WDO_CONFIG = config.get('wdo', {})
DOL_CONFIG = config.get('dol', {})
ARBITRAGE_CONFIG = config.get('arbitrage', {})
TAPE_READING_CONFIG = config.get('tape_reading', {})
DISPLAY_CONFIG = config.get('display', {})
SYSTEM_CONFIG = config.get('system', {})
RISK_MANAGEMENT_CONFIG = config.get('risk_management', {})

# NOVO: Configuração de timeouts dos setups
SETUP_TIMEOUTS_CONFIG = config.get('setup_timeouts', {})