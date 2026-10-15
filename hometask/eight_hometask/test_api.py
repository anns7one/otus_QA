import requests

def test_generate_valid_request_returns_full_response(generate):
    result = generate("2+2?")
    assert result["model"].startswith("llama3")
    assert result["done"] is True
    assert "response" in result
    assert isinstance(result["response"], str)
    assert len(result["response"]) > 0


