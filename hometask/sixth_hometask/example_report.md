# Отчёт оптимизатора автотестов

## Тесты по приоритетам

### HIGH (4)
- `test_get_posts_list_returns_100_items` — качество 94.0, требование: REQ-01
- `test_create_post_returns_201_and_echoes_body` — качество 94.0, требование: REQ-06
- `test_create_post_returns_201_again` — качество 94.0, требование: REQ-06
- `test_get_all_posts_count` — качество 88.0, требование: REQ-01

### MEDIUM (6)
- `test_get_nonexistent_post_returns_404` — качество 94.0, требование: REQ-03
- `test_get_posts_filtered_by_user_id` — качество 94.0, требование: REQ-04
- `test_get_post_comments_returns_5_items` — качество 94.0, требование: REQ-05
- `test_comments_of_first_post` — качество 94.0, требование: REQ-05
- `test_update_post_with_put_returns_200` — качество 88.0, требование: REQ-07
- `test_delete` — качество 76.0, требование: REQ-09

### LOW (0)
Не найдено

### БЕЗ ПРИВЯЗКИ К ТРЕБОВАНИЮ (1)
- `test_1` — качество 30.0, требование: -

## Дублирующие шаги

- `ASSERT set(VAR.keys()) == {'body', 'id', 'title', 'userId'}` — в тестах: test_create_post_returns_201_again, test_create_post_returns_201_and_echoes_body, test_get_posts_list_returns_100_items, test_update_post_with_put_returns_200
- `ASSERT VAR['title'] == VAR['title']` — в тестах: test_create_post_returns_201_again, test_create_post_returns_201_and_echoes_body, test_update_post_with_put_returns_200
- `ASSERT isinstance(VAR['id'], int)` — в тестах: test_create_post_returns_201_again, test_create_post_returns_201_and_echoes_body, test_get_posts_list_returns_100_items
- `GET /posts` — в тестах: test_get_all_posts_count, test_get_posts_filtered_by_user_id, test_get_posts_list_returns_100_items
- `ASSERT VAR['body'] == VAR['body']` — в тестах: test_create_post_returns_201_again, test_create_post_returns_201_and_echoes_body
- `ASSERT VAR['userId'] == VAR['userId']` — в тестах: test_create_post_returns_201_again, test_create_post_returns_201_and_echoes_body
- `ASSERT len(VAR) == 5` — в тестах: test_comments_of_first_post, test_get_post_comments_returns_5_items
- `ASSERT len(VAR.json()) == 100` — в тестах: test_1, test_get_all_posts_count
- `ASSERT set(VAR.keys()) == {'body', 'email', 'id', 'name', 'postId'}` — в тестах: test_comments_of_first_post, test_get_post_comments_returns_5_items
- `GET /posts/{id}/comments` — в тестах: test_comments_of_first_post, test_get_post_comments_returns_5_items
- `POST /posts` — в тестах: test_create_post_returns_201_again, test_create_post_returns_201_and_echoes_body

## Дублирующие/похожие тесты

- **exact** `test_create_post_returns_201_and_echoes_body` <-> `test_create_post_returns_201_again` (score=1.000) — identical step set
- **exact** `test_get_post_comments_returns_5_items` <-> `test_comments_of_first_post` (score=1.000) — identical step set
- **near** `test_get_posts_list_returns_100_items` <-> `test_get_all_posts_count` (score=0.877) — embedding cosine=0.877

## Покрытие требований

Покрыто 7 из 10 (70.0%), взвешенно по приоритетам — 76.2%.

Непокрытые требования:
- `REQ-02` (High) — GET /posts/{id} для существующего поста возвращает 200 и один объект Post
- `REQ-08` (Low) — PATCH /posts/{id} возвращает 200 и объект с применённым изменением
- `REQ-10` (Low) — GET /users возвращает 200 и 10 пользователей
