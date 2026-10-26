import requests

def test_generate_valid_request_returns_full_response(generate):
    result = generate("2+2?")
    assert result["model"].startswith("llama3")
    assert result["done"] is True
    assert "response" in result
    assert isinstance(result["response"], str)
    assert len(result["response"]) > 0

def test_generate_unknown_model_returns_error(base_url):
    response = requests.post(
        f"{base_url}/api/generate",
        json={"model": "not-a-real-model", "prompt": "hi", "stream": False},
        timeout=30,
        )

    assert response.status_code == 404

def test_generate_missing_prompt_returns_empty_response(base_url):
    response = requests.post(
        f"{base_url}/api/generate",
        json={"model": "llama3", "stream": False},
        timeout=30,
    )
    assert response.status_code == 200
    assert response.json()["response"] == ""


def test_generate_missing_model_field_is_rejected(base_url):
    response = requests.post(
        f"{base_url}/api/generate",
        json={"prompt": "hi", "stream": False},
        timeout=30,
    )
    assert response.status_code >= 400

def test_tags_endpoint_lists_pulled_model(base_url):
    response = requests.get(f"{base_url}/api/tags")

    assert response.status_code == 200
    models = [m["name"] for m in response.json()["models"]]
    assert any(name.startswith("llama3") for name in models)


