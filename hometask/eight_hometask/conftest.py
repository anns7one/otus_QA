import pytest
import requests

BASE_URL = "https://localhost:11438"
MODEL = "llama3"

@pytest.fixture(scope="session")
def base_url():
    return BASE_URL

@pytest.fixture
def generate():
    def _generate(prompt: str, temperature = 0, model= MODEL):
        response = requests.post(
            f"{BASE_URL}/api/generate",
            json = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature
                }
            },
            timeout=60,
        )
        response.raise_for_status()
        return response.json()
    return _generate