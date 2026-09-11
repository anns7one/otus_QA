"""Минимальный UI для ручного red-team тестирования агента."""
import json
import random
import requests
import streamlit as st

st.set_page_config(page_title="LLM Security Demo", layout="centered")
st.title("QA Assistant — red-team UI")

target = st.radio("Агент:", ["vulnerable (:8000)", "secure (:8001)"])
base_url = "http://localhost:8000" if "vulnerable" in target else "http://localhost:8001"

if "history" not in st.session_state:
    st.session_state.history = []

message = st.text_area("Payload / сообщение", height=100)

LOADING_MESSAGES = [
    "🕵️ Проверяем, не отравлено ли окно контекста...",
    "🧪 Скармливаем payload модели, ждём реакции...",
    "🦜 Уточняем, не заговорила ли модель по-пиратски...",
    "🔓 Пробуем убедить модель, что можно всё...",
    "🕳️ Ищем дыру в системном промпте...",
    "🎭 Проверяем, купится ли модель на роль DAN...",
]

if st.button("Отправить") and message.strip():
    with st.spinner(random.choice(LOADING_MESSAGES)):
        try:
            resp = requests.post(f"{base_url}/chat", json={"message": message}, timeout=60)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            data = {"reply": f"Ошибка запроса: {e}", "tool_calls": None}
    st.session_state.history.append({"target": target, "payload": message, "response": data})

for item in reversed(st.session_state.history):
    st.markdown(f"**[{item['target']}]** `{item['payload']}`")
    st.code(json.dumps(item["response"], ensure_ascii=False, indent=2), language="json")
    st.divider()
