import asyncio
import aiohttp
import json
import time
import os
from typing import List, Dict, Any, Optional
from datasets import load_dataset
from dataclasses import dataclass
from pathlib import Path
import logging

# Server Configuration
VLLM_SERVER_URL = "http://localhost:8000/v1/chat/completions"
MODEL_NAME = "google/gemma-3-27b-it"

# File Paths
OUTPUT_DIR = "data"
CHECKPOINT_FILE = "tl_chkp.json"
TRANSLATED_FILE = "tl_data.json"  # Changed to .json for structured format
INCREMENTAL_FILE = "tl_increment.jsonl"  # Backup incremental file
LOG_FILE = "tl.log"

# Processing Limits
INITIAL_LIMIT = None  # Process only first 100 entries for testing (set to None for full dataset)
MAX_CONCURRENT_REQUESTS = 64  # Number of concurrent translation requests
BATCH_SIZE = 32  # Number of entries to process in each batch

# Model Parameters
TEMPERATURE = 0.1  # Lower temperature for more consistent translations
MAX_TOKENS = 6555  # Maximum tokens for translation output
RETRY_COUNT = 3  # Number of retry attempts for failed requests

# Connection Settings
HTTP_TIMEOUT = 120  # Timeout in seconds for HTTP requests
TCP_CONNECTOR_LIMIT = 100  # Total connection pool size
TCP_CONNECTOR_LIMIT_PER_HOST = 50  # Connection limit per host

SYSTEM_PROMPT = """
คุณเป็นนักแปลมืออาชีพที่เชี่ยวชาญในการแปลเนื้อหา งานของคุณคือแปลโจทย์ปัญหาทางคณิตศาสตร์จากภาษาอังกฤษเป็นภาษาไทยอย่างแม่นยำ
**หลักการสำคัญ:**
1. แปลเฉพาะเนื้อหาที่ให้มาเท่านั้น ห้ามเพิ่มเติมหรือตัดทอนใดๆ
2. รักษาสูตรทางคณิตศาสตร์, สมการ, และสัญลักษณ์ทางคณิตศาสตร์ไว้เหมือนเดิมทุกตัว
3. รักษาตัวเลข, ชื่อตัวแปร, และสัญลักษณ์พิเศษไว้เหมือนเดิม
4. แปลภาษาไทยให้เป็นธรรมชาติและเข้าใจง่าย แต่คงความหมายเดิมไว้ครบถ้วน
5. ห้ามเพิ่มคำอธิบาย คำแนะนำ หรือความคิดเห็นส่วนตัว
6. ห้ามตอบคำถามหรือให้คำแนะนำใดๆ เกี่ยวกับโจทย์
แปลข้อความต่อไปนี้จากภาษาอังกฤษเป็นภาษาไทย:"""

# =============================================================================

@dataclass
class TranslationProgress:
    total_items: int
    completed_items: int
    failed_items: List[int]
    start_time: float
    last_checkpoint: float

class ThaiTranslator:
    def __init__(self, server_url: str):
        self.server_url = server_url
        self.max_concurrent = MAX_CONCURRENT_REQUESTS
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        self.session = None
        self.translated_entries = []  # Store all translated entries for structured output
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(LOG_FILE),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Create output directory
        Path(OUTPUT_DIR).mkdir(exist_ok=True)

    async def __aenter__(self):
        connector = aiohttp.TCPConnector(
            limit=TCP_CONNECTOR_LIMIT, 
            limit_per_host=TCP_CONNECTOR_LIMIT_PER_HOST
        )
        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT)
        self.session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def translate_text(self, text: str) -> Optional[str]:
        """Translate a single text using the vLLM server"""
        async with self.semaphore:
            for attempt in range(RETRY_COUNT):
                try:
                    payload = {
                        "model": MODEL_NAME,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": text}
                        ],
                        "temperature": TEMPERATURE,
                        "max_tokens": MAX_TOKENS,
                        "stream": False
                    }
                    
                    async with self.session.post(self.server_url, json=payload) as response:
                        if response.status == 200:
                            result = await response.json()
                            translated = result["choices"][0]["message"]["content"].strip()
                            return translated
                        else:
                            self.logger.warning(f"HTTP {response.status} on attempt {attempt + 1}")
                            
                except Exception as e:
                    self.logger.warning(f"Translation attempt {attempt + 1} failed: {str(e)}")
                    if attempt < RETRY_COUNT - 1:
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    
            return None

    def translate_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Translate all messages in a conversation"""
        translated_messages = []
        for msg in messages:
            translated_msg = msg.copy()
            # Only translate the content, keep role unchanged
            translated_msg["content"] = msg["content"]  # Will be translated later
            translated_messages.append(translated_msg)
        return translated_messages

    async def translate_entry(self, entry: Dict[str, Any], index: int) -> Optional[Dict[str, Any]]:
        """Translate a single dataset entry"""
        try:
            translated_entry = entry.copy()
            
            # Translate messages
            texts_to_translate = []
            message_indices = []
            
            for i, msg in enumerate(entry["messages"]):
                texts_to_translate.append(msg["content"])
                message_indices.append(i)
            
            # Add reasoning and answer to translation queue
            texts_to_translate.append(entry["reasoning"])
            texts_to_translate.append(entry["answer"])
            
            # Translate all texts concurrently
            translation_tasks = [self.translate_text(text) for text in texts_to_translate]
            translations = await asyncio.gather(*translation_tasks, return_exceptions=True)
            
            # Check for failures
            for i, translation in enumerate(translations):
                if isinstance(translation, Exception) or translation is None:
                    self.logger.error(f"Failed to translate entry {index}, text {i}")
                    return None
            
            # Apply translations to messages
            translated_entry["messages"] = []
            for i, msg in enumerate(entry["messages"]):
                translated_msg = msg.copy()
                translated_msg["content"] = translations[message_indices.index(i)]
                translated_entry["messages"].append(translated_msg)
            
            # Apply translations to reasoning and answer
            translated_entry["reasoning"] = translations[-2]
            translated_entry["answer"] = translations[-1]
            
            # Add metadata
            translated_entry["translation_metadata"] = {
                "original_language": "en",
                "target_language": "th",
                "translation_timestamp": time.time(),
                "original_index": index
            }
            
            return translated_entry
            
        except Exception as e:
            self.logger.error(f"Error processing entry {index}: {str(e)}")
            return None

    def save_checkpoint(self, progress: TranslationProgress):
        """Save translation progress"""
        checkpoint_data = {
            "total_items": progress.total_items,
            "completed_items": progress.completed_items,
            "failed_items": progress.failed_items,
            "start_time": progress.start_time,
            "last_checkpoint": time.time()
        }
        
        checkpoint_path = Path(OUTPUT_DIR) / CHECKPOINT_FILE
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(checkpoint_data, f, indent=2)
        
        self.logger.info(f"Checkpoint saved: {progress.completed_items}/{progress.total_items} completed")

    def load_checkpoint(self) -> Optional[TranslationProgress]:
        """Load previous translation progress"""
        checkpoint_path = Path(OUTPUT_DIR) / CHECKPOINT_FILE
        if checkpoint_path.exists():
            try:
                with open(checkpoint_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return TranslationProgress(**data)
            except Exception as e:
                self.logger.warning(f"Could not load checkpoint: {str(e)}")
        return None

    def save_translated_entry(self, entry: Dict[str, Any]):
        """Add translated entry to memory and save incremental backup"""
        # Add to memory for final structured output
        self.translated_entries.append(entry)
        
        # Also save incremental backup (JSONL format for safety)
        incremental_path = Path(OUTPUT_DIR) / INCREMENTAL_FILE
        with open(incremental_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def save_structured_json(self):
        """Save all translated entries as structured JSON"""
        output_data = {
            "metadata": {
                "total_entries": len(self.translated_entries),
                "translation_timestamp": time.time(),
                "source_language": "en",
                "target_language": "th",
                "model_used": MODEL_NAME,
                "translation_parameters": {
                    "temperature": TEMPERATURE,
                    "max_tokens": MAX_TOKENS,
                    "max_concurrent_requests": MAX_CONCURRENT_REQUESTS,
                    "batch_size": BATCH_SIZE
                }
            },
            "translated_entries": self.translated_entries
        }
        
        output_path = Path(OUTPUT_DIR) / TRANSLATED_FILE
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"Structured JSON saved: {len(self.translated_entries)} entries")

    def load_existing_translations(self) -> List[Dict[str, Any]]:
        """Load existing translations from incremental file if resuming"""
        incremental_path = Path(OUTPUT_DIR) / INCREMENTAL_FILE
        existing_entries = []
        
        if incremental_path.exists():
            try:
                with open(incremental_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            entry = json.loads(line)
                            existing_entries.append(entry)
                self.logger.info(f"Loaded {len(existing_entries)} existing translations")
            except Exception as e:
                self.logger.warning(f"Could not load existing translations: {str(e)}")
        
        return existing_entries

    async def translate_dataset(self, dataset):
        """Main translation function"""
        # Apply initial limit for testing
        dataset_size = len(dataset) if INITIAL_LIMIT is None else min(len(dataset), INITIAL_LIMIT)
        dataset = dataset.select(range(dataset_size))
        
        self.logger.info(f"Starting translation of {dataset_size} entries")
        
        # Load previous progress and existing translations
        progress = self.load_checkpoint()
        if progress and progress.total_items == dataset_size:
            start_idx = progress.completed_items
            # Load existing translations into memory
            self.translated_entries = self.load_existing_translations()
            self.logger.info(f"Resuming from entry {start_idx}")
        else:
            start_idx = 0
            self.translated_entries = []
            progress = TranslationProgress(
                total_items=dataset_size,
                completed_items=0,
                failed_items=[],
                start_time=time.time(),
                last_checkpoint=time.time()
            )
        
        # Process in batches for better memory management
        
        for batch_start in range(start_idx, dataset_size, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, dataset_size)
            batch_entries = dataset.select(range(batch_start, batch_end))
            
            # Translate batch
            translation_tasks = [
                self.translate_entry(entry, batch_start + i) 
                for i, entry in enumerate(batch_entries)
            ]
            
            batch_results = await asyncio.gather(*translation_tasks, return_exceptions=True)
            
            # Save results and update progress
            for i, result in enumerate(batch_results):
                entry_idx = batch_start + i
                
                if isinstance(result, Exception) or result is None:
                    progress.failed_items.append(entry_idx)
                    self.logger.error(f"Failed to process entry {entry_idx}")
                else:
                    self.save_translated_entry(result)
                    progress.completed_items += 1
            
            # Save checkpoint and structured JSON every batch
            self.save_checkpoint(progress)
            self.save_structured_json()  # Update structured JSON after each batch
            
            # Log progress
            elapsed = time.time() - progress.start_time
            rate = progress.completed_items / elapsed if elapsed > 0 else 0
            eta = (progress.total_items - progress.completed_items) / rate if rate > 0 else 0
            
            self.logger.info(
                f"Batch {batch_start//BATCH_SIZE + 1} completed. "
                f"Progress: {progress.completed_items}/{progress.total_items} "
                f"({progress.completed_items/progress.total_items*100:.1f}%) "
                f"Rate: {rate:.2f} entries/sec, ETA: {eta/60:.1f} min"
            )
        
        # Save final structured JSON
        self.save_structured_json()
        
        # Final summary
        success_rate = (progress.completed_items / progress.total_items) * 100
        total_time = time.time() - progress.start_time
        
        self.logger.info(f"Translation completed!")
        self.logger.info(f"Success rate: {success_rate:.1f}%")
        self.logger.info(f"Total time: {total_time/60:.1f} minutes")
        self.logger.info(f"Failed entries: {len(progress.failed_items)}")
        
        if progress.failed_items:
            self.logger.info(f"Failed entry indices: {progress.failed_items}")
        
        self.logger.info(f"Structured JSON output: {OUTPUT_DIR}/{TRANSLATED_FILE}")
        self.logger.info(f"Incremental backup: {OUTPUT_DIR}/{INCREMENTAL_FILE}")

async def main():
    """Main execution function"""
    print("Loading dataset...")
    dataset = load_dataset("cognitivecomputations/dolphin-r1", split="train", name="reasoning-deepseek")
    print(f"Dataset loaded: {len(dataset)} entries")
    
    print(f"Configuration:")
    print(f"  Model: {MODEL_NAME}")
    print(f"  Max concurrent requests: {MAX_CONCURRENT_REQUESTS}")
    print(f"  Batch size: {BATCH_SIZE}")
    print(f"  Initial limit: {INITIAL_LIMIT}")
    print(f"  Temperature: {TEMPERATURE}")
    print(f"  Max tokens: {MAX_TOKENS}")
    
    async with ThaiTranslator(VLLM_SERVER_URL) as translator:
        await translator.translate_dataset(dataset)
    
    print(f"\nTranslation complete!")
    print(f"📄 Main output (structured JSON): {OUTPUT_DIR}/{TRANSLATED_FILE}")
    print(f"💾 Incremental backup (JSONL): {OUTPUT_DIR}/{INCREMENTAL_FILE}")
    print(f"📊 Logs: {LOG_FILE}")

if __name__ == "__main__":
    asyncio.run(main())