import json
from transformers import AutoTokenizer

def analyze_alpaca_tokens(json_file):
    # Load tokenizer
    print("Loading Gemma tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained("google/gemma-3-27b-it")
    
    # Load data
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"Loaded {len(data)} entries\n")
    
    # Concatenate all text and count tokens
    all_text = []
    token_counts = []
    
    for entry in data:
        instruction = entry.get('instruction', '')
        input_text = entry.get('input', '')
        output_text = entry.get('output', '')
        
        # Combine all fields for this entry
        entry_text = f"{instruction} {input_text} {output_text}"
        all_text.append(entry_text)
        
        # Count tokens for this entry
        tokens = tokenizer.encode(entry_text, add_special_tokens=False)
        token_counts.append(len(tokens))
    
    # Concatenate ALL text
    concatenated_text = ' '.join(all_text)
    total_tokens = len(tokenizer.encode(concatenated_text, add_special_tokens=False))
    
    # Calculate stats
    avg_tokens = sum(token_counts) / len(token_counts)
    min_tokens = min(token_counts)
    max_tokens = max(token_counts)
    
    # Print results
    print("🔢 TOKEN STATISTICS")
    print("-" * 30)
    print(f"Total entries: {len(data):,}")
    print(f"Total tokens (concatenated): {total_tokens:,}")
    print(f"Average tokens per entry: {avg_tokens:.1f}")
    print(f"Min tokens per entry: {min_tokens}")
    print(f"Max tokens per entry: {max_tokens}")
    print(f"Total characters: {len(concatenated_text):,}")
    print(f"Chars per token: {len(concatenated_text) / total_tokens:.2f}")

if __name__ == "__main__":
    # Replace with your JSON file path
    json_file = "dolphin_reasoner_thai.json"
    
    try:
        analyze_alpaca_tokens(json_file)
    except FileNotFoundError:
        print(f"❌ File '{json_file}' not found!")
    except Exception as e:
        print(f"❌ Error: {e}")
