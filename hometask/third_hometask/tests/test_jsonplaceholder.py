import requests
import pytest

BASE_URL = "https://jsonplaceholder.typicode.com"

def test_get_posts_list_returns_100_items():
    """GET /posts возвращает 200 и массив ровно из 100 постов, у каждого элемента есть все четыре поля схемы Post."""
    response = requests.get(f"{BASE_URL}/posts", timeout=10)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 100
    for post in body:
        assert set(post.keys()) == {"userId", "id", "title", "body"}
        assert isinstance(post["id"], int)
        assert isinstance(post["title"], str)
        assert isinstance(post["body"], str)

def test_create_post_returns_201_and_echoes_body():
    """POST /posts с телом {"title": "...", "body": "...", "userId": 1} возвращает 201, в ответе есть поле id, а переданные значения title, body и userId возвращаются без изменений."""
    payload = {
        "title": "foo",
        "body": "bar",
        "userId": 1
    }
    response = requests.post(f"{BASE_URL}/posts", json=payload, timeout=10)

    assert response.status_code == 201
    body = response.json()
    assert set(body.keys()) == {"id", "title", "body", "userId"}
    assert isinstance(body["id"], int)
    assert body["title"] == payload["title"]
    assert body["body"] == payload["body"]
    assert body["userId"] == payload["userId"]

def test_get_nonexistent_post_returns_404():
    """GET /posts/999 возвращает 404 — негативная проверка."""
    response = requests.get(f"{BASE_URL}/posts/999", timeout=10)

    assert response.status_code == 404
