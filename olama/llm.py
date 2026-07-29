import ollama

response = ollama.chat(
model="llama3.2",
messages=[
{"role": "user", "content": "Generate category.json example for allure report"}
]
)

resp = response['message']['content']

print(resp)