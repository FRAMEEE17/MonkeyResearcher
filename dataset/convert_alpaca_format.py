import json

def convert_to_alpaca_format(input_file, output_file):
    """
    Convert JSON data to Alpaca format
    
    Args:
        input_file (str): Path to input JSON file
        output_file (str): Path to output JSON file
    """
    
    # Read the input JSON file
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    alpaca_data = []
    
    # Process each entry in translated_entries
    for entry in data["translated_entries"]:
        # Extract system message as instruction
        system_message = None
        user_message = None
        
        for message in entry["messages"]:
            if message["role"] == "system":
                system_message = message["content"]
            elif message["role"] == "user":
                user_message = message["content"]
        
        # Create the output by combining reasoning and answer
        # Wrap reasoning in <think> tags
        reasoning = entry.get("reasoning", "")
        answer = entry.get("answer", "")
        
        if reasoning:
            output = f"<think>{reasoning}</think>\n\n{answer}"
        else:
            output = answer
        
        # Create Alpaca format entry
        alpaca_entry = {
            "instruction": system_message if system_message is not None else "",
            "input": user_message if user_message is not None else "",
            "output": output
        }
        
        alpaca_data.append(alpaca_entry)
    
    # Write to output file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(alpaca_data, f, ensure_ascii=False, indent=2)
    
    print(f"Conversion complete! {len(alpaca_data)} entries converted.")
    print(f"Output saved to: {output_file}")

def convert_single_entry(entry):
    """
    Convert a single entry to Alpaca format (useful for testing)
    
    Args:
        entry (dict): Single entry from translated_entries
        
    Returns:
        dict: Alpaca format entry
    """
    # Extract system and user messages
    system_message = None
    user_message = None
    
    for message in entry["messages"]:
        if message["role"] == "system":
            system_message = message["content"]
        elif message["role"] == "user":
            user_message = message["content"]
    
    # Create the output by combining reasoning and answer
    reasoning = entry.get("reasoning", "")
    answer = entry.get("answer", "")
    
    if reasoning:
        output = f"<think>{reasoning}</think>\n\n{answer}"
    else:
        output = answer
    
    return {
        "instruction": system_message if system_message is not None else "",
        "input": user_message if user_message is not None else "",
        "output": output
    }

# Example usage with your provided data
if __name__ == "__main__":
    convert_to_alpaca_format("translated_dataset/translated_data.json", "alpaca_format.json")