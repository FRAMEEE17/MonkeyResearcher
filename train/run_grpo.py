from datasets import load_dataset, Dataset
from trl import GRPOConfig, GRPOTrainer
import re
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import json
from pythainlp.util import isthai

reasoning_start = "<think>"
reasoning_end   = "</think>"
solution_start = "<answer>"
solution_end = "</answer>"

system_prompt = \
f"""You are given a problem.
Think about the problem and provide your working out, using the same language as the problem provided.
Place it between {reasoning_start} and {reasoning_end}.
Then, provide your answer between {solution_start} and {solution_end}."""

def extract_hash_answer(text: str) -> str | None:
    if "####" not in text:
        return None
    return text.split("####")[1].strip()

def get_dataset_gpteacher(split = "train") -> Dataset:
    data = load_dataset('Thaweewat/gpteacher-20k-th')[split]
    data = data.map(lambda x: {
        'prompt': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': x['instruction'] + "\n" + x['input']},
        ],
        'answer': extract_hash_answer(x["answer"])
    })
    return data

def get_dataset_json(json_path: str) -> Dataset:
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    # Format into Hugging Face-compatible dictionary
    formatted_data = {
        'prompt': [],
        'answer': [],
    }   
    for item in data:
        prompt = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': item['translated_question']}
        ]
        formatted_data['prompt'].append(prompt)
        formatted_data['answer'].append(extract_hash_answer(item['original_answer']))

    return Dataset.from_dict(formatted_data)

dataset = get_dataset_json("gsm8k_thai_translations.json")

match_format = re.compile(
    rf"^[\s]{{0,}}"\
    rf"{reasoning_start}.+?{reasoning_end}.*?"\
    rf"{solution_start}(.+?){solution_end}"\
    rf"[\s]{{0,}}$",
    flags = re.MULTILINE | re.DOTALL
)

def extract_xml_answer(text: str) -> str:
    answer = text.split("<answer>")[-1]
    answer = answer.split("</answer>")[0]
    return answer.strip()

def correctness_reward_func(prompts, completions, answer, **kwargs) -> list[float]:
    responses = [completion[0]['content'] for completion in completions]
    q = prompts[0][-1]['content']
    extracted_responses = [extract_xml_answer(r) for r in responses]
    print('-'*20, f"Question:\n{q}", f"\nAnswer:\n{answer[0]}", f"\nResponse:\n{responses[0]}", f"\nExtracted:\n{extracted_responses[0]}")
    return [2.0 if r == a else 0.0 for r, a in zip(extracted_responses, answer)]

def int_reward_func(completions, **kwargs) -> list[float]:
    responses = [completion[0]['content'] for completion in completions]
    extracted_responses = [extract_xml_answer(r) for r in responses]
    return [0.5 if r.isdigit() else 0.0 for r in extracted_responses]

def strict_format_reward_func(completions, **kwargs) -> list[float]:
    """Reward function that checks if the completion has a specific format."""
    pattern = r"^<think>\n.*?\n</think>\n<answer>\n.*?\n</answer>\n$"
    responses = [completion[0]["content"] for completion in completions]
    matches = [re.match(pattern, r) for r in responses]
    return [0.5 if match else 0.0 for match in matches]

def soft_format_reward_func(completions, **kwargs) -> list[float]:
    """Reward function that checks if the completion has a specific format."""
    pattern = r"<think>.*?</think>\s*<answer>.*?</answer>"
    responses = [completion[0]["content"] for completion in completions]
    matches = [re.match(pattern, r) for r in responses]
    return [0.5 if match else 0.0 for match in matches]

def count_xml(text) -> float:
    count = 0.0
    if text.count("<think>") == 1:
        count += 0.125
    if text.count("</think>") == 1:
        count += 0.125
    if text.count("<answer>") == 1:
        count += 0.125
        count -= len(text.split("\n</answer>\n")[-1])*0.001
    if text.count("</answer>") == 1:
        count += 0.125
        count -= (len(text.split("\n</answer>")[-1]) - 1)*0.001
    return count

def xmlcount_reward_func(completions, **kwargs) -> list[float]:
    contents = [completion[0]["content"] for completion in completions]
    return [count_xml(c) for c in contents]

def thai_language_ratio(text: str) -> float:
    thai_chars = sum(1 for ch in text if isthai(ch))
    return thai_chars / max(len(text), 1)

def thai_consistency_reward_func(completions, **kwargs) -> list[float]:
    contents = [completion[0]["content"] for completion in completions]
    return [min(1.0, thai_language_ratio(c) / 0.9) for c in contents]

def is_allowed_char(ch):
    """Allow Thai, English letters, digits, punctuation, and whitespace."""
    codepoint = ord(ch)
    # Thai Unicode range
    if 0x0E00 <= codepoint <= 0x0E7F:
        return True
    # Basic Latin (English letters, digits, punctuation)
    if 0x0020 <= codepoint <= 0x007E:
        return True
    # Common whitespace and control characters
    if ch in '\n\r\t':
        return True
    return False

def thai_english_only_ratio(text: str) -> float:
    allowed = sum(1 for ch in text if is_allowed_char(ch))
    return allowed / max(len(text), 1)

def thai_english_consistency_reward_func(completions, **kwargs) -> list[float]:
    contents = [completion[0]["content"] for completion in completions]
    return [min(1.0, thai_english_only_ratio(c)) for c in contents]

# Configuration
model_path = "/home/siamai/llmtunLaMA-Factory/MonkeyReasonerFinal"

base_model = AutoModelForCausalLM.from_pretrained(
    model_path,
    attn_implementation="eager", 
    torch_dtype=torch.bfloat16,
)

# Load tokenizer separately if you need it for preprocessing
# tokenizer = AutoTokenizer.from_pretrained(model_path)
# if tokenizer.pad_token is None:
#     tokenizer.pad_token = tokenizer.eos_token

# Training configuration
training_args = GRPOConfig(output_dir="GRPOMonkey",
                           logging_steps=2,
                           learning_rate = 5e-6,
                           adam_beta1 = 0.9,
                           adam_beta2 = 0.99,
                           weight_decay = 0.1,
                           warmup_ratio = 0.1,
                           lr_scheduler_type = "cosine",
                           optim = "paged_adamw_8bit",
                           max_prompt_length = 256,
                           max_completion_length = 2048,
                           use_vllm=True,
                           per_device_train_batch_size = 2,
                           gradient_accumulation_steps = 8,
                           num_generations = 2,
                           num_train_epochs=2,
                           save_steps = 100,
                           gradient_checkpointing=True,
                           torch_empty_cache_steps=1,
                           bf16=True,
                           report_to="none")

# Initialize trainer - Let it load the model from path
trainer = GRPOTrainer(
    model=base_model,  # Pass the actual path to the model directory
    reward_funcs=[
        xmlcount_reward_func,
        soft_format_reward_func,
        strict_format_reward_func,
        correctness_reward_func,
        int_reward_func,
        thai_consistency_reward_func,
        thai_english_consistency_reward_func,
    ],
    args=training_args,
    train_dataset=dataset,
)

# Start training
print("Starting training...")
trainer.train()
trainer.save_model("GRPOMonkey")
