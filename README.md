# 🚗 Vehicle Detection & Monitoring System

**Система автоматического распознавания и мониторинга автомобилей на основе видео-аналитики**

> Интегрированная платформа для детектирования номерных знаков, отслеживания угнанных автомобилей и управления сетью камер видеонаблюдения.

---

## 📋 Содержание

- [Обзор](#обзор)
- [Архитектура](#архитектура)
- [Требования](#требования)
- [Установка](#установка)
- [Быстрый старт](#быстрый-старт)
- [API документация](#api-документация)
- [Основные компоненты](#основные-компоненты)
- [Структура проекта](#структура-проекта)
- [Конфигурация](#конфигурация)
- [Использование](#использование)

---

## 🎯 Обзор

Система предоставляет полное решение для видео-аналитики с фокусом на распознавание номерных знаков автомобилей:

### Основные возможности

✅ **Детектирование номеров** - Автоматическое распознавание государственных номеров в реальном времени  
✅ **Мониторинг камер** - Управление сетью RTSP-камер видеонаблюдения  
✅ **Система алертов** - Оповещения об угнанных и разыскиваемых автомобилях  
✅ **Управление базой данных** - Каталоги номеров, водителей и машин  
✅ **Запись видео** - Автоматическое сохранение потоков в облачное хранилище  
✅ **Экспорт отчётов** - Выгрузка алертов в CSV/Excel  
✅ **Мультипользовательский доступ** - Ролевая система управления (Admin/Operator)  
✅ **WebSocket стримы** - Real-time обновления через вебсокеты  

---

## 🏗️ Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                       FRONTEND (React + Vite)                   │
│                        Порт: 3030                               │
└────────────────┬────────────────────────────────┬────────────────┘
                 │                                │
         ┌───────▼─────────┐          ┌──────────▼──────────┐
         │   REST API      │          │    WebSocket        │
         │   (FastAPI)     │          │     (Alerts)        │
         │   Порт: 8000    │          │                     │
         └───────┬─────────┘          └──────────┬──────────┘
                 │                                │
         ┌───────▼──────────────────────────────▼──────┐
         │         BACKEND API (FastAPI)              │
         │  • Управление пользователями               │
         │  • CRUD операции с камерами                │
         │  • Управление алертами                     │
         │  • Экспорт отчётов                        │
         │  • Загрузка видео для анализа              │
         └───────┬──────────┬──────────┬──────────────┘
                 │          │          │
    ┌────────────▼──┐  ┌────▼──────┐  └────┬────────┐
    │   PostgreSQL   │  │   Kafka   │      │ MinIO  │
    │   Database     │  │  Broker   │      │ Storage│
    │                │  │           │      │        │
    │ • Users        │  │ • Plates  │      │ Videos │
    │ • Cameras      │  │ • Alerts  │      │Records │
    │ • Detections   │  │ • Jobs    │      │        │
    │ • Vehicles     │  │           │      │        │
    └────────────────┘  └───────────┘      └────────┘
                              ▲
                              │
         ┌────────────────────┴──────────────────────┐
         │                                           │
    ┌────▼────────────────────────┐  ┌─────────────▼──┐
    │   AI SERVICE (Python)       │  │ MediaMTX RTSP  │
    │   Порт: 8001               │  │ Router (8554)  │
    │                             │  │                │
    │ • Детектирование номеров   │  │ • RTSP streams │
    │ • Анализ видеопотоков      │  │ • Recording    │
    │ • Загрузка результатов      │  │ • Distribution │
    │ • YOLO модель              │  │                │
    │ • EasyOCR                   │  │                │
    └────────────────────────────┘  └────────────────┘
```

### Поток данных

1. **Видео ввод** → RTSP камеры подключаются к MediaMTX
2. **Обработка** → AI Service анализирует потоки с помощью YOLO + OCR
3. **Результаты** → Детекции отправляются в Kafka
4. **Потребление** → API Service получает результаты и сохраняет в БД
5. **Оповещение** → Алерты отправляются клиентам через WebSocket
6. **Сохранение** → Видео записываются в MinIO

---

## 💻 Требования

### Система

- **ОС:** Linux, Windows 11 Pro или macOS
- **Docker:** v20.10+
- **Docker Compose:** v1.29+
- **Оперативная память:** 8GB минимум
- **GPU (опционально):** CUDA-совместимая GPU для ускорения YOLO

### ПО

```
Backend API:
  - Python 3.10+
  - FastAPI 0.104+
  - PostgreSQL 14+
  - Kafka (Apache Kafka 3.x)

Frontend:
  - Node.js 18+
  - React 18+
  - Vite 5+

AI Service:
  - YOLOv8
  - EasyOCR
  - OpenCV
  - PyTorch
```

---

## 🚀 Установка

### 1. Клонирование репозитория

```bash
git clone <repository-url>
cd dipLOMKA
```

### 2. Подготовка переменных окружения

Создайте файл `.env` в корневой директории:

```env
# Database
DB_USER=postgres
DB_PASSWORD=your_secure_password
DB_NAME=vehicle_detection
DB_PORTS=5432

# MinIO Storage
MINIO_USER=minioadmin
MINIO_PASSWORD=your_minio_password

# API
API_PORT=8000

# JWT Secret (установите уникальное значение)
SECRET_KEY=your_very_secret_key_here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# AI Service
AI_SERVICE_URL=http://ai-service:8000
KAFKA_BROKER=broker:9092
```

Также создайте `.env` для API сервиса в `backend/API/.env`:

```env
DATABASE_URL=postgresql://postgres:your_secure_password@db:5432/vehicle_detection
JWT_SECRET_KEY=your_very_secret_key_here
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=your_minio_password
MINIO_BUCKET_NAME=videos
KAFKA_BROKER=broker:9092
AI_SERVICE_URL=http://ai-service:8000
```

### 3. Запуск через Docker Compose

```bash
docker-compose up -d
```

Дождитесь запуска всех сервисов (~30-60 секунд):

```bash
docker-compose logs -f
```

---

## ⚡ Быстрый старт

### Доступные сервисы

| Сервис | URL | Порт |
|--------|-----|------|
| **Фронтенд** | http://localhost:3030 | 3030 |
| **API** | http://localhost:8000 | 8000 |
| **AI Service** | http://localhost:8001 | 8001 |
| **Kafka UI** | http://localhost:8060 | 8060 |
| **MinIO Console** | http://localhost:9001 | 9001 |
| **MediaMTX** | rtsp://localhost:8554 | 8554 |

### 1. Вход в систему

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}'
```

**Ответ:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### 2. Добавление камеры

```bash
curl -X POST http://localhost:8000/cameras \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "camera_1",
    "location": "Главная улица, 1",
    "rtsp_url": "rtsp://192.168.1.100:554/stream"
  }'
```

### 3. Загрузка видео для анализа

```bash
curl -X POST http://localhost:8000/video-upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@video.mp4"
```

**Ответ:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "video.mp4",
  "status": "queued",
  "source_name": "upload_550e8400"
}
```

### 4. Проверка статуса обработки

```bash
curl -X GET http://localhost:8000/video-upload/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 5. Просмотр алертов

```bash
curl -X GET http://localhost:8000/alerts \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 📚 API Документация

### Интерактивная документация

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

### Основные эндпоинты

#### Аутентификация

```
POST   /auth/login              Вход в систему
GET    /auth/me                 Информация о текущем пользователе
```

#### Пользователи (Admin only)

```
GET    /users                   Список всех пользователей
POST   /users                   Создание пользователя
DELETE /users/{user_id}         Удаление пользователя
```

#### Камеры

```
GET    /cameras                 Список камер
POST   /cameras                 Добавление камеры
DELETE /cameras/{camera_id}     Удаление камеры
GET    /camera/{name}/stream    MJPEG стрим живой камеры
```

#### Алерты

```
GET    /alerts                  Все алерты
GET    /alerts/wanted           Только штрафники
GET    /alerts/stolen           Только угоны
GET    /alerts/enriched         Обогащённые алерты
GET    /alerts/export           Экспорт в CSV/Excel
```

#### Детекции номеров

```
GET    /detections              История распознаваний
GET    /unknown-plates          Список неизвестных номеров
PUT    /unknown-plates/{id}     Коррекция номера
GET    /unknown-plates/check/{number}  Проверка номера в БД
```

#### Угнанные машины

```
GET    /stolen-vehicles         Список угнанных
GET    /stolen-vehicles/enriched  С полной информацией
POST   /stolen-vehicles         Добавление в список
DELETE /stolen-vehicles/{plate_id}  Удаление из списка
```

#### Видео и записи

```
POST   /video-upload            Загрузка видео
GET    /video-upload            Список задач
GET    /video-upload/{job_id}   Статус задачи
GET    /video-upload/{job_id}/stream  Стрим обработанного видео
GET    /recordings              Список записей
GET    /recordings/download     Скачивание отрезка записи
```

#### WebSocket

```
WS     /ws/alerts               Реальные алерты (websocket)
```

---

## 🔧 Основные компоненты

### Backend API (`backend/API/`)

**Основные модули:**

- `main.py` - Точка входа приложения, маршруты API
- `auth/` - Аутентификация и авторизация
- `models/` - Pydantic модели данных
- `repositories/` - Слой доступа к БД
- `service/` - Бизнес-логика
- `brocker/consumer_kafka.py` - Потребитель Kafka сообщений

**Ключевые зависимости:**
```
FastAPI, Pydantic, PostgreSQL, Kafka, MinIO, JWT
```

### AI Service (`backend/ai-service/`)

**Основные модули:**

- `main.py` - Точка входа, маршруты для обработки видео
- `core/core.py` - Обработка камер и потоков
- `core/file_processor.py` - Обработка загруженных видеофайлов
- `core/config.toml` - Конфигурация моделей
- `broker/producer_kafka.py` - Отправка результатов в Kafka

**ML Модели:**
- **YOLOv8** - Детектирование объектов и номерных знаков
- **EasyOCR** - Распознавание символов на номерах

### Frontend (`frontend/`)

**Stack:** React 18 + Vite + Bootstrap

**Основные страницы:**
- Панель управления (Dashboard)
- Список камер и видеопотоки
- История алертов и детекций
- Управление пользователями
- Параметры и настройки

### База данных

**Основные таблицы:**
- `users` - Пользователи системы
- `cameras` - Камеры видеонаблюдения
- `plates` - Номерные знаки
- `drivers` - Информация о водителях
- `detections` - История распознаваний
- `alerts` - Алерты (штрафники и угоны)
- `unknown_plates` - Неизвестные номера
- `stolen_vehicles` - Угнанные автомобили
- `recordings` - Записи видеопотоков

---

## 📁 Структура проекта

```
dipLOMKA/
├── backend/
│   ├── API/
│   │   ├── main.py                 # Главное приложение
│   │   ├── requirements.txt        # Python зависимости
│   │   ├── DockerFile              # Контейнер API
│   │   ├── auth/                   # Аутентификация
│   │   ├── models/                 # Pydantic модели
│   │   ├── repositories/           # Доступ к БД
│   │   ├── service/                # Бизнес-логика
│   │   ├── brocker/                # Kafka потребитель
│   │   └── .env                    # Переменные окружения
│   │
│   └── ai-service/
│       ├── main.py                 # API AI сервиса
│       ├── Dockerfile              # Контейнер AI
│       ├── core/
│       │   ├── core.py             # Обработка потоков
│       │   ├── file_processor.py   # Обработка видео
│       │   └── config.toml         # Конфиг моделей
│       ├── broker/
│       │   └── producer_kafka.py   # Отправка результатов
│       └── best.pt                 # Обученная YOLO модель
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   ├── pages/                  # Компоненты страниц
│   │   ├── components/             # Переиспользуемые компоненты
│   │   └── styles/                 # CSS стили
│   ├── vite.config.js
│   ├── package.json
│   └── Dockerfile
│
├── db/
│   ├── 02_types_init.sql           # Типы данных PostgreSQL
│   ├── 03_cameras_init.sql         # Таблица камер
│   ├── 04_users_init.sql           # Таблица пользователей
│   └── 10_alert.sql                # Таблица алертов
│
├── router/
│   └── mediamtx.yml                # Конфиг MediaMTX
│
├── store/                          # MinIO хранилище
│
├── docker-compose.yml              # Оркестрация контейнеров
├── .env                            # Переменные окружения
└── README.md                       # Этот файл
```

---

## ⚙️ Конфигурация

### Environment переменные

**Основные параметры:**

```env
# DATABASE
DATABASE_URL=postgresql://user:password@db:5432/dbname
DB_USER=postgres
DB_PASSWORD=password
DB_NAME=vehicle_detection
DB_PORTS=5432

# STORAGE
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=password
MINIO_BUCKET_NAME=videos
MINIO_USER=minioadmin
MINIO_PASSWORD=password

# MESSAGE BROKER
KAFKA_BROKER=broker:9092

# SECURITY
JWT_SECRET_KEY=your_secret_key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# SERVICES
API_PORT=8000
AI_SERVICE_URL=http://ai-service:8000
```

### MediaMTX конфигурация

Файл `router/mediamtx.yml`:

```yaml
# RTSP сервер конфигурация
rtmp:
  enabled: true
  
hls:
  enabled: true
  
paths:
  # Динамические пути создаются автоматически
  all:
    record: true
    recordFormat: fmp4
    recordPartDuration: 300s
```

### YOLO конфигурация

Файл `backend/ai-service/core/config.toml`:

```toml
[detection]
model_path = "best.pt"
confidence_threshold = 0.5
iou_threshold = 0.45

[ocr]
languages = ["en"]
gpu = true
```

---

## 🎮 Использование

### Сценарий 1: Мониторинг RTSP-камер

```bash
# 1. Добавьте камеру
curl -X POST http://localhost:8000/cameras \
  -H "Authorization: Bearer TOKEN" \
  -d '{"name":"camera_1","location":"улица","rtsp_url":"rtsp://..."}'

# 2. Откройте видеострим в браузере
# http://localhost:3030/cameras/camera_1

# 3. Система автоматически:
# - Подключится к RTSP потоку
# - Запустит YOLO анализ
# - Обнаружит номера
# - Отправит алерты при совпадениях
```

### Сценарий 2: Анализ загруженного видео

```bash
# 1. Загрузите видео
curl -X POST http://localhost:8000/video-upload \
  -H "Authorization: Bearer TOKEN" \
  -F "file=@video.mp4"

# Ответ: { "job_id": "uuid", "status": "queued" }

# 2. Проверьте статус
curl http://localhost:8000/video-upload/uuid \
  -H "Authorization: Bearer TOKEN"

# 3. Смотрите результаты в реальном времени
# http://localhost:3030/analysis/uuid

# 4. Результаты появятся в /detections и /alerts
```

### Сценарий 3: Управление разыскиваемыми машинами

```bash
# 1. Добавьте номер в список разыскиваемых
curl -X POST http://localhost:8000/stolen-vehicles \
  -H "Authorization: Bearer TOKEN" \
  -d '{"plate_id":"uuid","description":"угнана 23.07.2026"}'

# 2. При детектировании номера система создаст алерт
# тип: "stolen"

# 3. Просмотрите алерты
curl http://localhost:8000/alerts/stolen \
  -H "Authorization: Bearer TOKEN"

# 4. Удалите из списка когда машина найдена
curl -X DELETE http://localhost:8000/stolen-vehicles/plate_id \
  -H "Authorization: Bearer TOKEN"
```

### Сценарий 4: Экспорт отчётов

```bash
# CSV экспорт
curl -X GET "http://localhost:8000/alerts/export?start_date=2026-07-01&end_date=2026-07-31&format=csv" \
  -H "Authorization: Bearer TOKEN" \
  -o alerts.csv

# Excel экспорт
curl -X GET "http://localhost:8000/alerts/export?start_date=2026-07-01&end_date=2026-07-31&format=xlsx" \
  -H "Authorization: Bearer TOKEN" \
  -o alerts.xlsx
```

### Сценарий 5: WebSocket подписка на алерты

```javascript
// JavaScript
const ws = new WebSocket('ws://localhost:8000/ws/alerts');

ws.onopen = () => {
  console.log('Подключены к алертам');
};

ws.onmessage = (event) => {
  const alert = JSON.parse(event.data);
  console.log('Новый алерт:', alert);
};

ws.onerror = (error) => {
  console.error('Ошибка подключения:', error);
};
```

---

## 🐛 Неполадки и решения

### PostgreSQL не запускается

```bash
# Проверьте логи
docker-compose logs db

# Очистите Volume и пересоздайте
docker-compose down -v
docker-compose up -d db
```

### AI Service не обнаруживает камеры

```bash
# Проверьте связь с MediaMTX
curl http://localhost:8080/v3/config/paths/list

# Перезагрузите AI Service
docker-compose restart ai-service
```

### WebSocket отключается

```bash
# Проверьте логи API
docker-compose logs api

# Убедитесь, что CORS настроен:
# В main.py должно быть:
# allow_origins=["*"]
```

### Kafka не получает сообщения

```bash
# Проверьте брокер
docker-compose logs broker

# Посмотрите топики
docker exec broker kafka-topics --list --bootstrap-server broker:9092

# Проверьте логи producer
docker-compose logs ai-service
```

---

## 📊 Мониторинг и логирование

### Просмотр логов

```bash
# Все сервисы
docker-compose logs -f

# Конкретный сервис
docker-compose logs -f api
docker-compose logs -f ai-service
docker-compose logs -f db

# Последние N строк
docker-compose logs --tail=100 api
```

### Kafka UI

Откройте http://localhost:8060 для визуализации:
- Брокеров
- Топиков
- Потребителей
- Сообщений в реальном времени

### MinIO Console

Откройте http://localhost:9001 для:
- Управления бакетами
- Просмотра загруженных видео
- Скачивания файлов

---

## 🔐 Безопасность

### Аутентификация

Система использует JWT токены:
- **Алгоритм:** HS256
- **Экспирация:** 30 минут (настраивается)
- **Хранение:** HttpOnly cookies

### Авторизация

Ролевая система доступа:
- **Admin** - Полный доступ, управление пользователями и камерами
- **Operator** - Просмотр данных, управление алертами

### Защита данных

- Пароли хешируются bcrypt
- HTTPS рекомендуется для продакшена
- Environment переменные для всех секретов
- SQL injection защита через Pydantic

---

## 📈 Производительность

### Рекомендуемые параметры

```yaml
# docker-compose.yml
services:
  api:
    # Используйте uvicorn workers
    environment:
      WORKERS: "4"
  
  ai-service:
    # GPU ускорение (если доступно)
    environment:
      CUDA_VISIBLE_DEVICES: "0"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

### Масштабирование

```bash
# Запустите несколько API инстансов (за load balancer)
docker-compose up -d --scale api=3

# Добавьте worker потоки для AI
docker-compose up -d ai-service  # Увеличьте CPU cores
```

---

## 📝 Лицензия

Проект создан в рамках дипломной работы.