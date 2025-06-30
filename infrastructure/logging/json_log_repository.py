# infrastructure/logging/json_log_repository.py (CORRIGIDO)
import json
import logging
from pathlib import Path
from datetime import datetime
from collections import deque
import threading
import time
from typing import Any

from domain.entities.signal import Signal
from application.interfaces.signal_repository import ISignalRepository

logger = logging.getLogger(__name__)

class JsonLogRepository(ISignalRepository):
    """
    Implementação de ISignalRepository que salva logs em formato JSON Lines (.jsonl)
    de forma assíncrona, otimizada e segura para ambientes com múltiplas threads.
    """
    
    def __init__(self, log_dir='logs', flush_interval=5):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # --- INÍCIO DA CORREÇÃO: Buffers e Locks ---
        # Buffers para armazenar logs em memória antes de escrever no disco.
        self.buffers = {
            'signals': deque(),
            'arbitrage': deque(),
            'tape_reading': deque(),
            'system': deque()
        }
        # Locks para garantir a segurança dos buffers em ambiente com múltiplas threads.
        self.locks = {name: threading.Lock() for name in self.buffers.keys()}
        # --- FIM DA CORREÇÃO ---
        
        self.flush_interval = flush_interval
        
        self.running = True
        self.writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self.writer_thread.start()

    def _convert_to_serializable(self, obj: Any) -> Any:
        """Converte objetos complexos para formato serializável (sem alterações)."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif hasattr(obj, 'dict'):  # Pydantic models
            return self._convert_to_serializable(obj.dict())
        elif hasattr(obj, 'value'):  # Enums
            return obj.value
        elif isinstance(obj, dict):
            return {k: self._convert_to_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_to_serializable(item) for item in obj]
        elif isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        else:
            return str(obj)

    def save(self, signal: Signal):
        """Salva um sinal no buffer de forma segura."""
        try:
            log_entry = self._convert_to_serializable(signal.dict())
            
            # --- INÍCIO DA CORREÇÃO: Uso de Lock ---
            with self.locks['signals']:
                self.buffers['signals'].append(log_entry)
            # --- FIM DA CORREÇÃO ---
            
        except Exception as e:
            logger.error(f"Erro ao preparar sinal para log: {e}", exc_info=True)

    def save_arbitrage_check(self, arbitrage_data: dict):
        """Salva dados de arbitragem no buffer de forma segura."""
        try:
            serializable_data = self._convert_to_serializable(arbitrage_data)
            serializable_data['timestamp'] = datetime.now().isoformat()

            # --- INÍCIO DA CORREÇÃO: Uso de Lock ---
            with self.locks['arbitrage']:
                self.buffers['arbitrage'].append(serializable_data)
            # --- FIM DA CORREÇÃO ---
        except Exception as e:
            logger.error(f"Erro ao salvar arbitrage_check: {e}", exc_info=True)

    def save_tape_reading_pattern(self, tape_data: dict):
        """Salva padrões de tape reading no buffer de forma segura."""
        try:
            serializable_data = self._convert_to_serializable(tape_data)
            serializable_data['timestamp'] = datetime.now().isoformat()

            # --- INÍCIO DA CORREÇÃO: Uso de Lock ---
            with self.locks['tape_reading']:
                self.buffers['tape_reading'].append(serializable_data)
            # --- FIM DA CORREÇÃO ---
        except Exception as e:
            logger.error(f"Erro ao salvar tape_reading_pattern: {e}", exc_info=True)

    def _writer_loop(self):
        """Loop de escrita em background."""
        while self.running:
            time.sleep(self.flush_interval)
            self.flush()

    def flush(self):
        """Move os logs dos buffers para os arquivos de log."""
        for log_type, buffer in self.buffers.items():
            if not buffer:
                continue
            
            # --- INÍCIO DA CORREÇÃO: Drenagem segura do buffer ---
            items_to_write = []
            with self.locks[log_type]:
                # Copia todas as mensagens do buffer de uma vez e o limpa.
                # Isso minimiza o tempo que o lock fica ativo.
                items_to_write.extend(buffer)
                buffer.clear()
            # --- FIM DA CORREÇÃO ---

            if items_to_write:
                self._write_batch_append(log_type, items_to_write)
            
    # --- INÍCIO DA CORREÇÃO: Novo método de escrita otimizado ---
    def _write_batch_append(self, log_type: str, batch: list):
        """Escreve um lote de logs em um arquivo usando o modo 'append' (anexar)."""
        if not batch:
            return

        # Usamos a extensão .jsonl para indicar o formato JSON Lines
        file_path = self.log_dir / f"{log_type}.jsonl"
        
        try:
            # O modo 'a' (append) anexa texto ao final do arquivo, o que é muito eficiente.
            with open(file_path, 'a', encoding='utf-8') as f:
                for item in batch:
                    # Escreve cada item como uma string JSON em sua própria linha.
                    json.dump(item, f, ensure_ascii=False)
                    f.write('\n')
            
            logger.debug(f"Batch de {len(batch)} items escritos para {file_path}")
            
        except Exception as e:
            logger.error(f"Erro ao escrever batch de logs para {log_type}: {e}", exc_info=True)
    # --- FIM DA CORREÇÃO ---

    def close(self):
        """Finaliza o repositório de forma segura, garantindo que todos os logs sejam salvos."""
        logger.info("Finalizando o repositório de logs JSON...")
        
        # --- INÍCIO DA CORREÇÃO: Lógica de shutdown robusta ---
        self.running = False
        
        # Espera a thread de escrita terminar seu último ciclo.
        if self.writer_thread.is_alive():
            self.writer_thread.join(timeout=self.flush_interval + 1)
        
        # Faz um último flush para garantir que nada ficou para trás nos buffers.
        logger.info("Realizando flush final dos logs...")
        self.flush()
        # --- FIM DA CORREÇÃO ---
        
        logger.info("Repositório de logs JSON finalizado com sucesso.")