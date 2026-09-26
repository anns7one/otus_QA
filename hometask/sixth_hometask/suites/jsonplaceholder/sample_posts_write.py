import requests

BASE_URL = "https://jsonplaceholder.typicode.com"


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


def test_create_post_returns_201_again():
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


def test_update_post_with_put_returns_200():
    """PUT /posts/1 с полным телом возвращает 200 и обновлённый объект с переданными значениями."""
    payload = {"id": 1, "title": "foo", "body": "bar", "userId": 1}
    response = requests.put(f"{BASE_URL}/posts/1", json=payload, timeout=10)

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"id", "title", "body", "userId"}
    assert body["title"] == payload["title"]


def test_delete():
    r = requests.delete(BASE_URL + "/posts/1")
    assert r.status_code == 200
