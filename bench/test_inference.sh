curl http://localhost:2124/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "MonkeyReasoner",
    "messages": [
      {"role": "system", "content": "คุณคือผู้ช่วยภาษาไทยที่มีความสามารถในการให้เหตุผลและคำนวณเลขอย่างแม่นยำ"},
      {"role": "user", "content": "ตอบคำถามแบบอธิบายวิธีคิด จงหาค่าของ 15 * 23"}
    ],
    "max_tokens": 256,
    "temperature": 0
  }'
