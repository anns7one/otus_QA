import requests

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


def test_get_all_posts_count():
    """Список постов содержит 100 элементов."""
    response = requests.get(f"{BASE_URL}/posts", timeout=10)

    assert response.status_code == 200
    assert len(response.json()) == 100


def test_get_nonexistent_post_returns_404():
    """GET /posts/999 возвращает 404 — негативная проверка."""
    response = requests.get(f"{BASE_URL}/posts/999", timeout=10)

    assert response.status_code == 404


def test_get_posts_filtered_by_user_id():
    """GET /posts?userId=1 возвращает 200 и ровно 10 постов, все принадлежат пользователю 1."""
    response = requests.get(f"{BASE_URL}/posts", params={"userId": 1}, timeout=10)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 10
    assert all(post["userId"] == 1 for post in body)


def test_get_post_comments_returns_5_items():
    """GET /posts/1/comments returns 200 and exactly 5 comments, each with the Comment schema fields."""
    response = requests.get(f"{BASE_URL}/posts/1/comments", timeout=10)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 5
    for comment in body:
        assert set(comment.keys()) == {"postId", "id", "name", "email", "body"}


def test_comments_of_first_post():
    """Комментарии к первому посту: 200 и пять комментариев со схемой Comment."""
    response = requests.get(f"{BASE_URL}/posts/1/comments", timeout=10)

    assert response.status_code == 200
    comments = response.json()
    assert len(comments) == 5
    for item in comments:
        assert set(item.keys()) == {"postId", "id", "name", "email", "body"}
