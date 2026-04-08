import os
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

import cv2
import threading
import queue
import time
import math
import base64
from io import BytesIO
import numpy as np
import csv
import re
from ultralytics import YOLO
from flask import Flask, render_template, Response, jsonify, request
from paddleocr import PaddleOCR

app = Flask(__name__)
model = YOLO("ai-model/best.pt")

OCR_DEBUG = False
OCR_WORKERS = 1
# Порог по уверенности, ниже которого пробуем fallback предобработку
OCR_CONF_THRESHOLD = 0.45
# Порог яркости (mean) для применения CLAHE/доп. предобработки
OCR_BRIGHTNESS_LOW = 40
OCR_BRIGHTNESS_HIGH = 220

print("[INIT] Загружаю PaddleOCR...")
reader = PaddleOCR(
    lang='en',
    text_detection_model_name='PP-OCRv5_mobile_det',
    text_recognition_model_name='en_PP-OCRv5_mobile_rec',
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    enable_mkldnn=False,
    cpu_threads=2,
)
print("[INIT] PaddleOCR загружен успешно!")
video_path = "videos/Satpaeva38_3_1_20260120100000_20260120101500.dav"

# Видео и параметры
cap = cv2.VideoCapture(video_path)
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS)

# Состояние
current_frame_num = 0
is_playing = False
seek_to = None
frame_queue = queue.Queue(maxsize=2)

# Очередь для сохранения вырезанных номеров (и OCR задач)
crop_queue = queue.Queue(maxsize=50)  # увеличенный размер, чтобы не блокировать видео
plates_dir = os.path.join(os.path.dirname(__file__), 'plates')
os.makedirs(plates_dir, exist_ok=True)

# ROI: нижняя часть кадра (доля высоты для сохранения)
ROI_RATIO = 0.15  # нижние 15% кадра считаются зоной, где сохраняем номер

# CSV для OCR результатов
ocr_csv_path = os.path.join(os.path.dirname(__file__), 'ocr_results.csv')
csv_lock = threading.Lock()  # Для потокобезопасной записи в CSV
if not os.path.exists(ocr_csv_path):
    with open(ocr_csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # Добавляем колонку confidence для оценки качества
        writer.writerow(['id', 'timestamp', 'ocr_text', 'confidence'])

# Список распознанных машин
detected_plates = []  # [{id, frame, photo1_b64, photo2_b64}]
detected_lock = threading.Lock()

lock = threading.Lock()

# Сохраняем какие track_id уже обработали

# Простое отслеживание
tracks = {}  # track_id -> {last_box, last_seen, prev_center, saved, ocr_history}
next_track_id = 1
INACTIVE_FRAMES = 40

from collections import Counter

def preprocess_plate(img):
    """Улучшенная предобработка для надежного OCR"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Денойзинг (убирает шумы видео)
    gray = cv2.bilateralFilter(gray, 9, 75, 75)
    
    # Масштабируем в 3 раза (для мелких номеров)
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    
    # CLAHE — адаптивный контраст (критич для видео низкого качества!)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    
    # Легкое размытие для сглаживания
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    
    # Адаптивная пороговизация (уже работает хорошо)
    thresh = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11,
        2
    )
    
    # Морфологические операции — очищает артефакты
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=1)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
    
    return thresh

def validate_plate(text):
    """Валидирует распознанный номер"""
    text = re.sub(r'[^A-Z0-9]', '', text)
    # Временно отключаем строгую валидацию для отладки
    # если текст не пустой, пропускаем
    if len(text) >= 2:
        return text
    return ""


def fix_common_ocr_errors(text):
    """Исправляет типичные ошибки EasyOCR для номеров"""
    replacements = {
        'I': '1',       # I похожа на 1
        'l': '1',       # маленькое л похожа на 1
        'O': '0',       # O похожа на 0
        'B': '8',       # B похожа на 8
        'S': '5',       # S похожа на 5
        'Z': '2',       # Z похожа на 2
        'G': '9',       # G похожа на 9
        'U': 'V',       # U может быть V
    }
    fixed = ""
    for c in text:
        fixed += replacements.get(c, c)
    return fixed


def pick_best_text(history):
    if not history:
        return ""
    return Counter(history).most_common(1)[0][0]


def extract_paddle_text(results):
    """Совместимость с форматами ответа PaddleOCR 2.x и 3.x."""
    if not results:
        return "", 0.0

    parts = []
    confidences = []
    first = results[0]

    # PaddleOCR 3.x: список словарей с rec_texts / rec_scores
    if isinstance(first, dict):
        rec_texts = first.get('rec_texts') or []
        rec_scores = first.get('rec_scores') or []
        for idx, raw_text in enumerate(rec_texts):
            conf = float(rec_scores[idx]) if idx < len(rec_scores) else 0.0
            text_clean = str(raw_text).strip().upper()
            if text_clean and conf >= 0.25:
                parts.append(text_clean)
                confidences.append(conf)
    else:
        # PaddleOCR 2.x: [[ [bbox, (text, conf)], ... ]]
        line_items = first if isinstance(first, list) else results
        sortable_items = []
        for item in line_items:
            try:
                bbox = item[0]
                text, conf = item[1]
                x_pos = bbox[0][0] if bbox and bbox[0] else 0
                sortable_items.append((x_pos, str(text).strip().upper(), float(conf)))
            except Exception:
                continue

        sortable_items.sort(key=lambda row: row[0])
        for _, text_clean, conf in sortable_items:
            if text_clean and conf >= 0.25:
                parts.append(text_clean)
                confidences.append(conf)

    ocr_text = "".join(parts)
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return ocr_text, avg_confidence


def perform_ocr_and_save(crop_img, tid, ts):
    """Быстрый и совместимый OCR для вырезанного номера."""
    try:
        print(f"\n[OCR START] ID={tid}, crop shape={crop_img.shape}")

        if OCR_DEBUG:
            debug_path = os.path.join(plates_dir, f"debug_raw_{tid}_{ts}.jpg")
            cv2.imwrite(debug_path, crop_img)

        # Попытка 1: цветной кроп, увеличение
        processed1 = cv2.resize(crop_img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        if OCR_DEBUG:
            debug_processed_path = os.path.join(plates_dir, f"debug_processed_{tid}_{ts}_1.jpg")
            cv2.imwrite(debug_processed_path, processed1)

        start1 = time.time()
        results1 = reader.ocr(processed1)
        t1 = time.time() - start1
        ocr_text, avg_confidence = extract_paddle_text(results1)
        ocr_text = re.sub(r'\s+', '', ocr_text)

        print(f"[PERF] OCR attempt 1 time={t1:.3f}s, conf={avg_confidence:.3f}, text='{ocr_text}'")

        used_preprocess = False

        # Если ничего не нашли или низкая уверенность — пробуем предобработку
        if (not ocr_text) or (avg_confidence < OCR_CONF_THRESHOLD):
            gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)
            mean_val = float(np.mean(gray))
            print(f"[DEBUG] mean brightness={mean_val:.1f}")

            if (mean_val < OCR_BRIGHTNESS_LOW or mean_val > OCR_BRIGHTNESS_HIGH) or (not ocr_text) or (avg_confidence < OCR_CONF_THRESHOLD):
                print(f"[OCR] Попытка fallback preprocess_plate для ID={tid}")
                pre = preprocess_plate(crop_img)
                # преобразуем обратно в BGR для PaddleOCR и увеличим
                processed2 = cv2.cvtColor(pre, cv2.COLOR_GRAY2BGR)
                processed2 = cv2.resize(processed2, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
                if OCR_DEBUG:
                    debug_processed2 = os.path.join(plates_dir, f"debug_processed_{tid}_{ts}_2.jpg")
                    cv2.imwrite(debug_processed2, processed2)

                start2 = time.time()
                results2 = reader.ocr(processed2)
                t2 = time.time() - start2
                ocr_text2, avg_confidence2 = extract_paddle_text(results2)
                ocr_text2 = re.sub(r'\s+', '', ocr_text2)

                print(f"[PERF] OCR attempt 2 time={t2:.3f}s, conf={avg_confidence2:.3f}, text='{ocr_text2}'")
                used_preprocess = True

                # Выбираем лучший результат по уверенности
                if ocr_text2 and (avg_confidence2 >= avg_confidence):
                    ocr_text = ocr_text2
                    avg_confidence = avg_confidence2

        if not ocr_text:
            print(f"⚠️ PaddleOCR не нашёл текст для ID={tid} (после fallback)")
            return ''

        ocr_text = fix_common_ocr_errors(ocr_text)
        ocr_text = validate_plate(ocr_text)

        if ocr_text:
            with csv_lock:
                with open(ocr_csv_path, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([tid, ts, ocr_text, f"{avg_confidence:.3f}"])
            print(f"✅ УСПЕХ ID={tid}: '{ocr_text}' (conf={avg_confidence:.2f})" + (" (preprocessed)" if used_preprocess else ""))
        else:
            print(f"⚠️ Текст не прошел валидацию для ID={tid}")

        return ocr_text

    except Exception as e:
        print(f"❌ ОШИБКА OCR для ID={tid}: {e}")
        import traceback
        traceback.print_exc()
        return ''

# ROI: нижняя часть кадра (доля высоты для сохранения)
ROI_RATIO = 0.15  # нижние 15% кадра считаются зоной, где сохраняем номер

def center(box):
    """Возвращает центр бокса"""
    x1, y1, x2, y2 = box
    return ((x1 + x2) // 2, (y1 + y2) // 2)

def expand_box(box, frame_h, frame_w, padding=60):
    """Расширяет бокс на padding пиксели со всех сторон для полного номера"""
    x1, y1, x2, y2 = box
    x1 = max(0, x1 - padding)
    y1 = max(0, y1 - padding)
    x2 = min(frame_w, x2 + padding)
    y2 = min(frame_h, y2 + padding)
    return (x1, y1, x2, y2)

def process_video():
    global current_frame_num, seek_to, next_track_id
    frame_id = 0  # счётчик кадров для пропуска
    print(f"[VIDEO] Стартую process_video, total_frames={total_frames}, fps={fps}")

    def iou(a, b):
        """Простой расчет IoU между двумя боксами"""
        xa1, ya1, xa2, ya2 = a
        xb1, yb1, xb2, yb2 = b
        xi1 = max(xa1, xb1)
        yi1 = max(ya1, yb1)
        xi2 = min(xa2, xb2)
        yi2 = min(ya2, yb2)
        iw = max(0, xi2 - xi1)
        ih = max(0, yi2 - yi1)
        inter = iw * ih
        area_a = max(0, xa2 - xa1) * max(0, ya2 - ya1)
        area_b = max(0, xb2 - xb1) * max(0, yb2 - yb1)
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0

    while True:
        loop_start = time.time()
        detected_boxes = []  # 🔥 ИНИЦИАЛИЗАЦИЯ В НАЧАЛЕ ЦИКЛА
        try:
            # handle seek
            if seek_to is not None:
                with lock:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, seek_to)
                    current_frame_num = seek_to
                    seek_to = None

            if not is_playing:
                # print(f"[VIDEO] ⏸️ На паузе")
                time.sleep(0.1)
                continue
            
            if frame_id % 120 == 0:
                print(f"[VIDEO] ▶️ Обрабатываю frame={frame_id}, is_playing={is_playing}")

            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                current_frame_num = 0
                continue

            # пропускать половину кадров для ускорения
            frame_id += 1
            if frame_id % 2 != 0:
                continue

            # Быстрый YOLO (без трекера) по всему кадру
            results = model(frame, verbose=False)

            detected = results[0].plot()
            h, w = frame.shape[:2]
            # линия сохранения по низу кадра
            line_y = int(h * (1 - ROI_RATIO))
            # рисуем линию сохранения
            cv2.line(detected, (0, line_y), (w, line_y), (0, 0, 255), 2)
            pos_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))

            boxes = getattr(results[0], 'boxes', None)
            if frame_id % 120 == 0:
                print(f"[YOLO] Frame #{frame_id}: найдено объектов={len(boxes) if boxes else 0}")
            
            if boxes is not None:
                for box in boxes:
                    try:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                    except Exception:
                        continue

                    x1 = max(0, min(w-1, x1))
                    x2 = max(0, min(w, x2))
                    y1 = max(0, min(h-1, y1))
                    y2 = max(0, min(h, y2))

                    if x2 - x1 <= 10 or y2 - y1 <= 10:
                        continue

                    # ОСЛАБЛЯЕМ фильтр боксов для окончательной проверки
                    if (x2 - x1) < 40 or (y2 - y1) < 15:
                        continue
                    detected_boxes.append((x1, y1, x2, y2))

            # если нужно, можно было рисовать бокс, но скорость важнее

            # Матчим боксы с существующими треками
            matched_boxes = set()  # Индексы матченных боксов
            for tid, tr in list(tracks.items()):
                best_iou = 0
                best_box_idx = None
                
                # запоминаем предыдущий центр перед обновлением
                old_cx, old_cy = center(tr['last_box'])
                
                for idx, box in enumerate(detected_boxes):
                    if idx in matched_boxes:
                        continue
                    i = iou(tr['last_box'], box)
                    if i > 0.2 and i > best_iou:  # Снизили порог с 0.3 на 0.2
                        best_iou = i
                        best_box_idx = idx
                
                if best_box_idx is not None:
                    tr['prev_center'] = (old_cx, old_cy)
                    tr['last_box'] = detected_boxes[best_box_idx]
                    tr['last_seen'] = pos_frame
                    matched_boxes.add(best_box_idx)
                    # делаем OCR не чаще чем раз в 2 секунды, пока трек не сохранён
                    if not tr.get('saved'):
                        now = time.time()
                        if now - tr.get('last_ocr', 0) > 2:
                            x1, y1, x2, y2 = expand_box(tr['last_box'], h, w, padding=60)
                            crop = frame[y1:y2, x1:x2]
                            # Минимум 100px для OCR
                            if crop.shape[1] >= 100 and crop.shape[0] >= 30:
                                ts_inner = int(now * 1000)
                                print(f"[QUEUE] 📤 Положить ID={tid}, crop={crop.shape}")
                                try:
                                    # Добавляем четвертый элемент (full_thumb) — None для обычных попыток
                                    crop_queue.put((crop, tid, ts_inner, None), block=False)
                                    tr['last_ocr'] = now
                                    print(f"[QUEUE] ✅ В очереди осталось {crop_queue.qsize()}")
                                except queue.Full:
                                    print(f"[QUEUE] ❌ ПЕРЕПОЛНЕНА!")
                                    pass
                else:
                    # Трек потеряли
                    if pos_frame - tr['last_seen'] > INACTIVE_FRAMES:
                        tracks.pop(tid, None)

            # Новые боксы - создаем треки, сохраняем prev_center и флаг saved
            for idx, box in enumerate(detected_boxes):
                if idx in matched_boxes:
                    continue
                
                cx, cy = center(box)
                too_close = False
                
                # Проверяем расстояние до существующих треков
                for tr in tracks.values():
                    tcx, tcy = center(tr['last_box'])
                    dist = ((cx - tcx)**2 + (cy - tcy)**2) ** 0.5
                    if dist < 80:  # Если ближе 80 пикселей - это, вероятно, тот же трек
                        too_close = True
                        break
                
                if not too_close:
                    tid = next_track_id
                    next_track_id += 1
                    tracks[tid] = {
                        'last_box': box,
                        'last_seen': pos_frame,
                        'prev_center': center(box),
                        'saved': False,
                        'ocr_history': []
                    }
                    # сразу сохраняем, если центр уже ниже линии
                    # если трек появляется уже за линией сохранения — помечаем сразу
                    if line_y is not None and cy >= line_y:
                        tr = tracks[tid]
                        tr['saved'] = True

                        # Расширяем бокс для полного сохранения номера
                        expanded_box = expand_box(box, h, w, padding=60)
                        x1, y1, x2, y2 = expanded_box
                        crop = frame[y1:y2, x1:x2]

                        ts = int(time.time() * 1000)

                        # Не сохраняем файлы синхронно в главном потоке — это блокирует видео.
                        # Вместо этого кладём в очередь с миниатюрой full_thumb, а сохранение выполнит worker.
                        try:
                            # Миниатюра для UI (чтобы не кодировать полный кадр)
                            full_thumb = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
                        except Exception:
                            full_thumb = frame

                        try:
                            crop_queue.put((crop, tid, ts, full_thumb), block=False)
                        except queue.Full:
                            pass

                        ocr_text = "⏳ processing..."

                        # Подготовим уменьшенные изображения для UI (быстрее, чем записывать файлы)
                        try:
                            crop_thumb = cv2.resize(crop, (0, 0), fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
                        except Exception:
                            crop_thumb = crop

                        crop_b64 = crop_to_base64(crop_thumb)
                        full_b64 = crop_to_base64(full_thumb)

                        with detected_lock:
                            detected_plates.append({
                                'id': tid,
                                'frame': pos_frame,
                                'ts': ts,
                                'photo1': full_b64,
                                'photo2': crop_b64,
                                'ocr_text': ocr_text
                            })

                        print(f"✅ Машина ID={tid} сохранена при создании под линией")

            # Сохраняем машины при пересечении линии (line_y всегда есть)
            for tid, tr in list(tracks.items()):
                if tr.get('saved'):
                    continue
                cx, cy = center(tr['last_box'])
                prev_cx, prev_cy = tr.get('prev_center', (cx, cy))
                crossed = prev_cy < line_y and cy >= line_y
                if crossed:
                    tr['saved'] = True

                    # Расширяем бокс для полного сохранения номера
                    expanded_box = expand_box(tr['last_box'], h, w, padding=60)
                    x1, y1, x2, y2 = expanded_box
                    crop = frame[y1:y2, x1:x2]

                    ts = int(time.time() * 1000)

                    # Если ещё нет результата, ставим в очередь и помечаем как processing
                    ocr_text = pick_best_text(tr.get('ocr_history', []))
                    if not ocr_text:
                        try:
                            # передаём уменьшенную миниатюру кадра для сохранения в воркере
                            full_thumb = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
                        except Exception:
                            full_thumb = frame

                        try:
                            crop_queue.put((crop, tid, ts, full_thumb), block=False)
                        except queue.Full:
                            pass
                        ocr_text = "⏳ processing..."

                    # Подготовка мини-картинок для быстрой отдачи в UI
                    try:
                        crop_thumb = cv2.resize(crop, (0, 0), fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
                    except Exception:
                        crop_thumb = crop
                    crop_b64 = crop_to_base64(crop_thumb)
                    full_b64 = crop_to_base64(full_thumb if 'full_thumb' in locals() else cv2.resize(frame, (0, 0), fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA))

                    with detected_lock:
                        detected_plates.append({
                            'id': tid,
                            'frame': pos_frame,
                            'ts': ts,
                            'photo1': full_b64,
                            'photo2': crop_b64,
                            'ocr_text': ocr_text
                        })

                    print(f"✅ Машина ID={tid} сохранена при пересечении линии")

            current_frame_num = pos_frame

            try:
                frame_queue.get_nowait()
            except queue.Empty:
                pass
            
            frame_queue.put(detected)

            # попытка подстроиться под исходный FPS, чтобы видео не летело
            if fps and fps > 0:
                elapsed = time.time() - loop_start
                wait = (1.0 / fps) - elapsed
                if wait > 0:
                    time.sleep(wait)

        except Exception as e:
            print(f"❌ Ошибка в process_video: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(0.1)
            continue

def generate():
    while True:
        try:
            frame = frame_queue.get(timeout=1)
            ret, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()
        except queue.Empty:
            continue
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n'
               b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n\r\n'
               + frame_bytes + b'\r\n')


def crop_to_base64(crop):
    """Кодирует OpenCV изображение (numpy array) в base64 строку."""
    _, buffer = cv2.imencode('.jpg', crop)
    return base64.b64encode(buffer).decode('utf-8')

def crop_saver_worker():
    """OCR worker: читает номера из очереди, сохраняет результаты и обновляет историю"""
    print("[WORKER] 🚀 Стартован!")
    worker_count = 0
    while True:
        try:
            item = crop_queue.get(timeout=1)
            worker_count += 1
            # поддерживаем формат (crop, tid, ts) и (crop, tid, ts, full_thumb)
            if isinstance(item, tuple) and len(item) == 4:
                crop, tid, ts, full_thumb = item
            else:
                crop, tid, ts = item
                full_thumb = None
            print(f"[WORKER] #{worker_count} Получил: ID={tid}, shape={crop.shape}, has_full_thumb={full_thumb is not None}")
        except queue.Empty:
            if worker_count == 0:
                print(f"[WORKER] ⏳ Ждёт данных из очереди...")
            time.sleep(0.1)
            continue

        try:
            # Если слишком узкий фрагмент, пропускаем
            if crop.shape[1] < 80:
                print(f"[WORKER] ⚠️ Слишком мелкий: {crop.shape[1]} (нужно >= 80)")
                continue

            # Если был передан full_thumb — сохраняем crop и мини-кадр асинхронно в worker
            if full_thumb is not None:
                try:
                    crop_filename = f"plate_{tid}_{ts}.jpg"
                    crop_path = os.path.join(plates_dir, crop_filename)
                    _, crop_buf = cv2.imencode('.jpg', crop, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                    with open(crop_path, 'wb') as f:
                        f.write(crop_buf.tobytes())

                    full_filename = f"plate_{tid}_{ts}_full.jpg"
                    full_path = os.path.join(plates_dir, full_filename)
                    _, full_buf = cv2.imencode('.jpg', full_thumb, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                    with open(full_path, 'wb') as f:
                        f.write(full_buf.tobytes())

                    print(f"[WORKER] Сохранил файлы для ID={tid}: {crop_filename}, {full_filename}")
                except Exception as e:
                    print(f"[WORKER] Ошибка при сохранении файлов для ID={tid}: {e}")

            print(f"[WORKER] 🔄 START OCR для ID={tid}")
            ocr_text = perform_ocr_and_save(crop, tid, ts)
            print(f"[WORKER] 📝 Результат: '{ocr_text}'")
            
            # обновляем историю трека, только если OCR что-то реально нашел
            if ocr_text and tid in tracks:
                tr = tracks[tid]
                tr.setdefault('ocr_history', []).append(ocr_text)
                if len(tr['ocr_history']) > 30:
                    tr['ocr_history'].pop(0)
            
            # обновляем отображаемый элемент, если уже есть
            with detected_lock:
                for item in detected_plates:
                    if item.get('id') == tid and item.get('ts') == ts:
                        item['ocr_text'] = ocr_text
                        print(f"[WORKER] Обновил item для ID={tid}")
                        break
            
            print(f"[WORKER] OCR finished: '{ocr_text}'")
        except Exception as e:
            print(f"[WORKER] OCR error: {e}")
            import traceback
            traceback.print_exc()
            continue

@app.route('/')
def index():
    return render_template('video.html')

@app.route('/video')
def video():
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/info')
def info():
    return jsonify({
        'total': total_frames,
        'current': current_frame_num,
        'fps': fps,
        'playing': is_playing
    })

@app.route('/detected')
def detected():
    with detected_lock:
        return jsonify({'detected': detected_plates})

@app.route('/play')
def play():
    global is_playing
    is_playing = True
    return jsonify({'status': 'playing'})

@app.route('/pause')
def pause():
    global is_playing
    is_playing = False
    return jsonify({'status': 'paused'})

@app.route('/seek/<int:frame>')
def seek(frame):
    global seek_to
    seek_to = min(frame, total_frames - 1)
    return jsonify({'status': 'seeked', 'frame': frame})




if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 СТАРТУЮ ПРИЛОЖЕНИЕ")
    print("="*60)
    print(f"[INIT] Video: {video_path}")
    print(f"[INIT] Total frames: {total_frames}, FPS: {fps}")
    print(f"[INIT] CSV path: {ocr_csv_path}")
    print(f"[INIT] Plates dir: {plates_dir}")
    print("="*60 + "\n")
    
    thread = threading.Thread(target=process_video, daemon=True)
    thread.start()
    print("[MAIN] ✅ Thread process_video стартован")
    
    # Один OCR worker стабильнее для PaddleOCR и заметно меньше грузит CPU
    for i in range(OCR_WORKERS):
        threading.Thread(target=crop_saver_worker, daemon=True).start()
    print(f"[MAIN] ✅ {OCR_WORKERS} OCR worker(s) стартовали")
    print("[MAIN] 📡 Запускаю Flask на http://localhost:5000\n")
    
    app.run(debug=False, port=5000)
