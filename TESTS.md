# 1. Создать промпт (если ещё нет):

```
curl -X POST http://127.0.0.1:8765/api/prompts \
  -H 'Content-Type: application/json' \
  -d '{"group_id":1,"title":"test","positive":"a cat","negative":"bad","cfg":2.5}'
```

# 2. Заказать 3 превью (size по умолчанию):

```
curl -X POST http://127.0.0.1:8765/api/prompts/1/order \
  -H 'Content-Type: application/json' \
  -d '{"kind":"preview"}'
 ```
Вернёт job с id, status: pending, file_ids: [1,2,3].

# 3. Воркер забирает работу:

curl http://127.0.0.1:8765/api/jobs/next

# 4. Воркер присылает результат по каждому файлу:

```
curl -X POST http://127.0.0.1:8765/api/jobs/1/result \
  -H 'Content-Type: application/json' \
  -d '{"file_id":1,"status":"done","path":"previews/test_1.png","meta_path":"previews/test_1.png.json","seed":12345}'
```
