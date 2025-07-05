import requests
import json
from datasets import load_dataset
from tqdm import tqdm
import re

VLLM_API_URL = "http://localhost:2124/v1/chat/completions"
MODEL_NAME = "MonkeyReasoner"
CONFIGS = ["onet", "ic", "tgat", "tpat1", "a_level"]
OUTPUT_FILE = "reasoning_sft_merged.json"
SYSTEM_PROMPT = """
คุณคือผู้ช่วยเหลือในการตอบคำถามแบบปรนัยภาษาไทย
โปรดอ่านคำถามและตัวเลือกอย่างรอบคอบ แล้วให้คำตอบที่ถูกต้องที่สุด
คำตอบควรอยู่ในรูปแบบของตัวอักษร A, B, C, D หรือ E เท่านั้น กรุณาให้คำตอบสุดท้ายในรูปแบบ <SOLUTION>...</SOLUTION>
ยกตัวอย่างเช่น
คำถาม: "กำหนดให้ p เป็นจำนวนจริงโดยที่ p,1,p+3,... เป็นลำดับเลขคณิต\r\nผลบวก 10 พจน์แรกของอนุกรมที่ได้จากลำดับเลขคณิตนี้ เท่ากับเท่าใด
A. 0.5
B. 1.5
C. 12.5
D. 62.5
E. 67.5
คำตอบ: "<think>\nเนื่องจาก p, 1, p+3 เป็นลำดับเลขคณิต แสดงว่าผลต่างร่วม (d) มีค่าคงที่\nดังนั้น 1 - p = (p+3) - 1\n1 - p = p + 2\n2p = -1\np = -1/2\n\nดังนั้น ลำดับเลขคณิตคือ -1/2, 1, 3/2, ...\nผลต่างร่วม d = 1 - (-1/2) = 3/2\n\nผลบวก n พจน์แรกของลำดับเลขคณิต คือ Sn = n/2 * [2a + (n-1)d]\nเมื่อ a คือพจน์แรก และ d คือผลต่างร่วม\n\nในที่นี้ a = -1/2, d = 3/2, n = 10\nS10 = 10/2 * [2*(-1/2) + (10-1)*(3/2)]\nS10 = 5 * [-1 + 9*(3/2)]\nS10 = 5 * [-1 + 27/2]\nS10 = 5 * [-2/2 + 27/2]\nS10 = 5 * [25/2]\nS10 = 125/2\nS10 = 62.5\n</think>\n\n<SOLUTION>D</SOLUTION>"
"""

def format_prompt(question, choices):
    prompt = f"คำถาม: {question}\n"
    
    for label, choice in choices:
        prompt += f"{label}. {choice}\n"
    prompt += "คำตอบ: "
    return prompt

def extract_solution(text):
    """
    Extract content inside <SOLUTION>...</SOLUTION>
    """
    match = re.search(r"<SOLUTION>\s*([\s\S]*?)\s*</SOLUTION>", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

def extract_first_choice_letter(solution):
    """
    Get the first valid uppercase choice letter (A–E) from the solution
    """
    match = re.match(r"[A-E]", solution.strip().upper())
    return match.group(0) if match else None

def is_correct(predicted_output, answer_key):
    """
    Return True if the predicted letter matches the correct answer
    """
    solution = extract_solution(predicted_output)
    if solution:
        pred_letter = extract_first_choice_letter(solution)
        return pred_letter == answer_key.upper()
    return False

all_results = {}
glb_correct = 0
glb_total = 0
for config in CONFIGS:
    print(f"Evaluating config: {config}")
    dataset = load_dataset("scb10x/thai_exam", name=config)
    data = dataset['test']
    
    correct = 0
    total = 0
    results = []
    
    
    for item in tqdm(data):
        question = item['question']
        
        choices = []
        for label in ['A', 'B', 'C', 'D', 'E']:
            choice_text = item.get(label.lower(), "").strip()
            if choice_text:
                choices.append((label, choice_text))
            if not choices:
                continue
            
        ans_key = item['answer'].upper()
        
        valid_ans_key = any(label == ans_key for label, _ in choices)
        if not valid_ans_key:
            continue
        prompt = format_prompt(question, choices)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
        
        payload = {
            "model": MODEL_NAME,
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0.0,
        }
        
        try:
            response = requests.post(VLLM_API_URL, json=payload)
            response.raise_for_status()
            completion = response.json()
            generated_text = completion['choices'][0]['message']['content']
            
            if is_correct(generated_text, ans_key):
                correct += 1
            total += 1
            
            results.append({
                "question": question,
                "choices": {label: text for label, text in choices},
                "corret_answer": ans_key,
                "model_ans": generated_text,
                "is_correct": is_correct(generated_text, ans_key)
            })
        except Exception as e:
            print(f"Error processing question: {e}")
            continue
    glb_correct += correct
    glb_total += total       
    accuracy = correct / total if total > 0 else 0
    print(f"Accuracy for {config}: {accuracy:.2%}\n")
    all_results[config] = {
        "accuracy": accuracy,
        "results": results
    }
print(f"Total Correct: {glb_correct}")
print(f"Total Questions: {glb_total}")
accuracy = glb_correct / glb_total if glb_total > 0 else 0
print(f"Accuracy: {accuracy:.2%}\n")    
# Save results to JSON file
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(all_results, f, ensure_ascii=False, indent=4)

print(f"Results saved to {OUTPUT_FILE}")