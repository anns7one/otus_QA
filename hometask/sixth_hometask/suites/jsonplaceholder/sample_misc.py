import requests

BASE_URL = "https://jsonplaceholder.typicode.com"


def test_1():
    r = requests.get(BASE_URL + "/albums")
    assert r.status_code == 200
    assert len(r.json()) == 100
    assert r.json()[0]["id"] == 1
    assert r.json()[0]["userId"] == 1
    assert r.json()[99]["id"] == 100
    assert r.json()[50]["userId"] == 6
