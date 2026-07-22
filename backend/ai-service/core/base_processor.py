import os
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

import cv2
import threading
import queue
import time
import math
import numpy as np
import re
import tomllib
from ultralytics import YOLO
from paddleocr import PaddleOCR
from collections import Counter
from core.logger import PlateLogger
from broker.producer_kafka import KafkaManager
from minio_client import MinioStorage

CLASS_CAR = 0
CLASS_PLATE = 1

_KZ_PATTERNS = [
    r'^\d{3}[A-Z]{3}\d{2}$',
    r'^[A-Z]\d{3}[A-Z]{2}$',
    r'^\d{3}[A-Z]{2}\d{2}$',
]

_LETTERS_TO_DIGITS = {'O': '0', 'I': '1', 'L': '1', 'Z': '2', 'S': '5', 'B': '8', 'G': '9'}
_DIGITS_TO_LETTERS = {'0': 'O', '1': 'I', '8': 'B', '5': 'S', '2': 'Z'}

_DIGIT_POSITIONS = {
    8: {0, 1, 2, 6, 7},
    7: {0, 1, 2, 5, 6},
    6: {1, 2, 3},
}
_LETTER_POSITIONS = {
    8: {3, 4, 5},
    7: {3, 4},
    6: {0, 4, 5},
}


class BaseProcessor:
    """Общая логика детекции, трекинга, OCR, MinIO и Kafka.

    Подклассы реализуют process_video() под свой режим работы.
    """

    def __init__(self, video_source, name="default", job_id=None):
        self.name = name
        self.video_source = video_source
        self.job_id = job_id

        config_path = os.path.join(os.path.dirname(__file__), 'config.toml')
        with open(config_path, 'rb') as f:
            config = tomllib.load(f)

        self.OCR_DEBUG = config['app']['OCR_DEBUG']
        self.OCR_WORKERS = config['app']['OCR_WORKERS']
        self.OCR_CONF_THRESHOLD = config['app']['OCR_CONF_THRESHOLD']
        self.OCR_BRIGHTNESS_LOW = config['app']['OCR_BRIGHTNESS_LOW']
        self.OCR_BRIGHTNESS_HIGH = config['app']['OCR_BRIGHTNESS_HIGH']
        self.ROI_RATIO = config['app']['ROI_RATIO']
        self.INACTIVE_FRAMES = config['app']['INACTIVE_FRAMES']

        self.logger = PlateLogger.get_logger(self.name)

        self.logger.info(f"Loading YOLO model for {self.name}")
        self.model = YOLO("ai-model/best.pt")
        self._detect_class_mapping()

        self.logger.info(f"Loading PaddleOCR for {self.name}")
        self.reader = PaddleOCR(
            lang='en',
            text_detection_model_name='PP-OCRv5_mobile_det',
            text_recognition_model_name='en_PP-OCRv5_mobile_rec',
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            enable_mkldnn=False,
            cpu_threads=2,
        )
        self.logger.info(f"PaddleOCR loaded for {self.name}")

        self.cap = cv2.VideoCapture(video_source)
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)

        self.current_frame_num = 0
        self.crop_queue = queue.Queue(maxsize=50)
        self.frame_queue = queue.Queue(maxsize=2)

        self.minio_storage = MinioStorage(logger=self.logger)

        self.lock = threading.Lock()
        self.tracks = {}
        self.next_track_id = 1

        self.processing_thread = None
        self.worker_threads = []

        self.kafka_manager = KafkaManager(logger=self.logger)

    # ------------------------------------------------------------------
    # Авто-определение классов модели
    # ------------------------------------------------------------------

    def _detect_class_mapping(self):
        global CLASS_CAR, CLASS_PLATE
        try:
            names = getattr(self.model, 'names', None)
            if isinstance(names, dict):
                for idx, name in names.items():
                    s = str(name).lower()
                    if any(k in s for k in ('plate', 'licen', 'number')):
                        CLASS_PLATE = idx
                    elif any(k in s for k in ('car', 'vehicle', 'truck')):
                        CLASS_CAR = idx
            self.logger.info(f"Class mapping: CAR={CLASS_CAR}, PLATE={CLASS_PLATE}")
        except Exception as e:
            self.logger.warning(f"Could not detect class mapping, using defaults: {e}")

    # ------------------------------------------------------------------
    # Геометрия
    # ------------------------------------------------------------------

    @staticmethod
    def _center(box):
        x1, y1, x2, y2 = box
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    @staticmethod
    def _iou(a, b):
        xa1, ya1, xa2, ya2 = a
        xb1, yb1, xb2, yb2 = b
        xi1, yi1 = max(xa1, xb1), max(ya1, yb1)
        xi2, yi2 = min(xa2, xb2), min(ya2, yb2)
        inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
        area_a = max(0, xa2 - xa1) * max(0, ya2 - ya1)
        area_b = max(0, xb2 - xb1) * max(0, yb2 - yb1)
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0

    @staticmethod
    def _distance(c1, c2):
        return math.hypot(c1[0] - c2[0], c1[1] - c2[1])

    def _expand_box(self, box, frame_h, frame_w, padding=60):
        x1, y1, x2, y2 = box
        return (
            max(0, x1 - padding),
            max(0, y1 - padding),
            min(frame_w, x2 + padding),
            min(frame_h, y2 + padding),
        )

    def _crop_frame(self, frame, box, h, w, padding=0):
        x1, y1, x2, y2 = self._expand_box(box, h, w, padding=padding)
        crop = frame[y1:y2, x1:x2]
        return crop if crop.size > 0 else None

    # ------------------------------------------------------------------
    # Детекция YOLO
    # ------------------------------------------------------------------

    def _detect(self, frame, h, w, roi_y=0):
        """Запускает YOLO и возвращает (car_dets, plate_dets).

        roi_y — минимальная Y-координата центра номера. 0 означает весь кадр.
        """
        results = self.model(frame, verbose=False)
        boxes = getattr(results[0], 'boxes', None)

        car_dets, plate_dets = [], []
        for box in boxes or []:
            try:
                cls = int(box.cls[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
            except Exception:
                continue

            x1 = max(0, min(w - 1, x1))
            x2 = max(0, min(w, x2))
            y1 = max(0, min(h - 1, y1))
            y2 = max(0, min(h, y2))

            if x2 - x1 < 40 or y2 - y1 < 15:
                continue

            tbox = (x1, y1, x2, y2)
            if cls == CLASS_CAR:
                car_dets.append({'box': tbox, 'conf': conf})
            elif cls == CLASS_PLATE:
                cy = (y1 + y2) // 2
                if cy >= roi_y:
                    plate_dets.append({'box': tbox, 'conf': conf})

        return car_dets, plate_dets

    # ------------------------------------------------------------------
    # Связка plate → car
    # ------------------------------------------------------------------

    def _match_plates_to_cars(self, car_dets, plate_dets):
        car_to_plate = {}
        for p in plate_dets:
            pbox = p['box']
            px1, py1, px2, py2 = pbox
            p_area = max(0, px2 - px1) * max(0, py2 - py1)
            p_center = self._center(pbox)
            p_conf = p.get('conf', 0.0)

            for ci, c in enumerate(car_dets):
                cbox = c['box']
                cx1, cy1, cx2, cy2 = cbox
                contained = px1 >= cx1 and py1 >= cy1 and px2 <= cx2 and py2 <= cy2
                center_inside = cx1 <= p_center[0] <= cx2 and cy1 <= p_center[1] <= cy2
                iou_val = self._iou(pbox, cbox)

                if contained or center_inside or iou_val >= 0.05:
                    old = car_to_plate.get(ci)
                    if old is None or p_area > old['area'] or (p_area == old['area'] and p_conf > old['conf']):
                        car_to_plate[ci] = {'box': pbox, 'area': p_area, 'conf': p_conf}
                    break
        return car_to_plate

    # ------------------------------------------------------------------
    # Трекинг
    # ------------------------------------------------------------------

    def _match_tracks(self, car_dets, pos_frame):
        MATCH_DISTANCE_MAX = 300.0
        MATCH_SCORE_THRESHOLD = 0.12

        new_tracks = {}
        used_old = set()
        car_index_to_tid = {}

        for ci, det in enumerate(car_dets):
            c_box = det['box']
            c_center = self._center(c_box)
            best_id, best_score = None, -1.0

            for tid, tr in self.tracks.items():
                if tid in used_old:
                    continue
                try:
                    old_box = tr['last_box']
                    old_center = self._center(old_box)
                except Exception:
                    continue
                iou_val = self._iou(c_box, old_box)
                dist = self._distance(c_center, old_center)
                dist_score = max(0.0, (MATCH_DISTANCE_MAX - dist) / MATCH_DISTANCE_MAX)
                score = iou_val * 0.7 + dist_score * 0.3

                if score > best_score:
                    best_score = score
                    best_id = tid

            if best_id is not None and best_score >= MATCH_SCORE_THRESHOLD:
                tr = self.tracks[best_id]
                tr['prev_center'] = self._center(tr['last_box'])
                tr['last_box'] = c_box
                tr['last_seen'] = pos_frame
                new_tracks[best_id] = tr
                used_old.add(best_id)
                car_index_to_tid[ci] = best_id
            else:
                tid = self.next_track_id
                self.next_track_id += 1
                new_tracks[tid] = {
                    'last_box': c_box,
                    'last_seen': pos_frame,
                    'prev_center': self._center(c_box),
                    'saved': False,
                    'ocr_history': [],
                    'best_plate_box': None,
                    'best_plate_area': 0,
                }
                car_index_to_tid[ci] = tid

        return new_tracks, car_index_to_tid

    def _update_plate_boxes(self, new_tracks, car_index_to_tid, car_to_plate):
        """Обновляет лучший номерной бокс для каждого трека."""
        for ci, tid in car_index_to_tid.items():
            if ci not in car_to_plate:
                continue
            pinfo = car_to_plate[ci]
            tr = new_tracks[tid]
            if pinfo['area'] > tr.get('best_plate_area', 0):
                tr['best_plate_area'] = pinfo['area']
                tr['best_plate_box'] = pinfo['box']

    def _remove_stale_tracks(self, pos_frame):
        """Удаляет треки, не обновлявшиеся дольше INACTIVE_FRAMES."""
        for tid in list(self.tracks.keys()):
            tr = self.tracks.get(tid)
            if tr and pos_frame - tr.get('last_seen', 0) > self.INACTIVE_FRAMES:
                self.tracks.pop(tid, None)

    # ------------------------------------------------------------------
    # OCR утилиты
    # ------------------------------------------------------------------

    def _preprocess_plate(self, img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 9, 75, 75)
        gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=1)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
        return thresh

    def _extract_paddle_text(self, results):
        if not results:
            return "", 0.0
        parts, confidences = [], []
        first = results[0]
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
            line_items = first if isinstance(first, list) else results
            sortable = []
            for item in line_items:
                try:
                    bbox = item[0]
                    text, conf = item[1]
                    x_pos = bbox[0][0] if bbox and bbox[0] else 0
                    sortable.append((x_pos, str(text).strip().upper(), float(conf)))
                except Exception:
                    continue
            for _, text_clean, conf in sorted(sortable, key=lambda r: r[0]):
                if text_clean and conf >= 0.25:
                    parts.append(text_clean)
                    confidences.append(conf)
        ocr_text = "".join(parts)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        return ocr_text, avg_confidence

    def _fix_common_ocr_errors(self, text):
        s = re.sub(r'[^A-Z0-9]', '', str(text or '').strip().upper())
        if not s:
            return s
        n = len(s)
        digit_pos = _DIGIT_POSITIONS.get(n)
        letter_pos = _LETTER_POSITIONS.get(n)

        if digit_pos is None or letter_pos is None:
            return "".join(_LETTERS_TO_DIGITS.get(c, c) for c in s)

        chars = list(s)
        for i, ch in enumerate(chars):
            if i in digit_pos and ch in _LETTERS_TO_DIGITS:
                chars[i] = _LETTERS_TO_DIGITS[ch]
            elif i in letter_pos and ch in _DIGITS_TO_LETTERS:
                chars[i] = _DIGITS_TO_LETTERS[ch]
        return "".join(chars)

    def _validate_plate(self, text):
        text = re.sub(r'[^A-Z0-9]', '', str(text).strip().upper())
        for pattern in _KZ_PATTERNS:
            if re.match(pattern, text):
                return text
        return ""

    def _pick_best_text(self, history):
        if not history:
            return ""
        return Counter(history).most_common(1)[0][0]

    # ------------------------------------------------------------------
    # Постановка в очередь
    # ------------------------------------------------------------------

    def _enqueue_track(self, frame, tr, tid, h, w, mark_saved=True):
        car_crop = self._crop_frame(frame, tr['last_box'], h, w, padding=60)
        if car_crop is None or car_crop.shape[1] < 80 or car_crop.shape[0] < 30:
            return

        plate_crop = None
        if tr.get('best_plate_box') is not None:
            plate_crop = self._crop_frame(frame, tr['best_plate_box'], h, w, padding=10)
            if plate_crop is not None and (plate_crop.shape[1] < 20 or plate_crop.shape[0] < 8):
                plate_crop = None

        try:
            full_thumb = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
        except Exception:
            full_thumb = frame

        ts = int(time.time() * 1000)
        try:
            self.crop_queue.put((car_crop, plate_crop, tid, ts, full_thumb), block=False)
            if mark_saved:
                tr['saved'] = True
        except queue.Full:
            print(f"[QUEUE][FAIL] Очередь переполнена, трек ID={tid} отброшен", flush=True)
            self.logger.warning(f"crop_queue full, dropping tid={tid}")

    # ------------------------------------------------------------------
    # OCR воркер
    # ------------------------------------------------------------------

    def perform_ocr_and_save(self, crop_img, tid, ts, crop_url='', full_url=''):
        try:
            # ── ШАГ 5а: OCR проход 1 ─────────────────────────────────────
            processed1 = cv2.resize(crop_img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            t0 = time.time()
            results1 = self.reader.ocr(processed1)
            ocr_text, avg_confidence = self._extract_paddle_text(results1)
            ocr_text = re.sub(r'\s+', '', ocr_text)
            print(
                f"[OCR][PASS1] ID={tid} текст='{ocr_text}' "
                f"уверенность={avg_confidence:.2f} время={time.time()-t0:.2f}s",
                flush=True,
            )

            # ── ШАГ 5б: OCR проход 2 (fallback) ─────────────────────────
            if not ocr_text or avg_confidence < self.OCR_CONF_THRESHOLD:
                gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)
                mean_val = float(np.mean(gray))
                need_fallback = (
                    not ocr_text
                    or avg_confidence < self.OCR_CONF_THRESHOLD
                    or mean_val < self.OCR_BRIGHTNESS_LOW
                    or mean_val > self.OCR_BRIGHTNESS_HIGH
                )
                if need_fallback:
                    print(f"[OCR][PASS2] ID={tid} запускаем fallback, яркость={mean_val:.1f}", flush=True)
                    pre = self._preprocess_plate(crop_img)
                    processed2 = cv2.cvtColor(pre, cv2.COLOR_GRAY2BGR)
                    processed2 = cv2.resize(processed2, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
                    t0 = time.time()
                    results2 = self.reader.ocr(processed2)
                    ocr_text2, avg_confidence2 = self._extract_paddle_text(results2)
                    ocr_text2 = re.sub(r'\s+', '', ocr_text2)
                    print(
                        f"[OCR][PASS2] ID={tid} текст='{ocr_text2}' "
                        f"уверенность={avg_confidence2:.2f} время={time.time()-t0:.2f}s",
                        flush=True,
                    )
                    if ocr_text2 and avg_confidence2 >= avg_confidence:
                        ocr_text, avg_confidence = ocr_text2, avg_confidence2

            if not ocr_text:
                print(f"[OCR][FAIL] ID={tid} текст не распознан", flush=True)
                return ''

            # ── ШАГ 5в: коррекция и валидация ────────────────────────────
            ocr_text_corrected = self._fix_common_ocr_errors(ocr_text)
            ocr_text_validated = self._validate_plate(ocr_text_corrected)

            if not ocr_text_validated:
                print(
                    f"[OCR][INVALID] ID={tid} '{ocr_text}' → '{ocr_text_corrected}' "
                    f"не прошёл валидацию КЗ паттернов → unknown_plate",
                    flush=True,
                )
                try:
                    self.kafka_manager.publish_unknown_plate(
                        camera_name=self.name,
                        plate_number=ocr_text_corrected,
                        confidence=float(avg_confidence),
                        timestamp=ts,
                        plates_photo_url=crop_url,
                        full_photo_url=full_url,
                        job_id=self.job_id,
                    )
                    print(f"[KAFKA][OK] unknown_plate отправлен: '{ocr_text_corrected}'", flush=True)
                except Exception as e:
                    print(f"[KAFKA][FAIL] unknown_plate не отправлен ID={tid}: {e}", flush=True)
                return ''

            ocr_text = ocr_text_validated
            print(f"[OCR][OK] ID={tid} номер='{ocr_text}' уверенность={avg_confidence:.2f}", flush=True)

            # ── ШАГ 6: Kafka ─────────────────────────────────────────────
            try:
                self.kafka_manager.publish_detection(
                    camera_name=self.name,
                    plate_number=ocr_text,
                    confidence=float(avg_confidence),
                    timestamp=ts,
                    plates_photo_url=crop_url,
                    full_photo_url=full_url,
                    job_id=self.job_id,
                )
                print(f"[KAFKA][OK] plate_detections отправлен: '{ocr_text}' камера={self.name}", flush=True)
            except Exception as e:
                print(f"[KAFKA][FAIL] '{ocr_text}': {e}", flush=True)

            return ocr_text

        except Exception as e:
            print(f"[OCR][FAIL] Исключение ID={tid}: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return ''

    def crop_saver_worker(self):
        print(f"[WORKER][OK] OCR-воркер запущен для {self.name}", flush=True)

        while True:
            try:
                item = self.crop_queue.get(timeout=1)
            except queue.Empty:
                time.sleep(0.1)
                continue

            try:
                if len(item) == 5:
                    car_crop, plate_crop, tid, ts, full_thumb = item
                elif len(item) == 4:
                    car_crop, tid, ts, full_thumb = item
                    plate_crop = None
                else:
                    print(f"[WORKER][FAIL] Неизвестный формат элемента очереди len={len(item)}", flush=True)
                    continue

                if car_crop is None and plate_crop is None:
                    print(f"[WORKER][FAIL] Оба кропа None для ID={tid}", flush=True)
                    continue

                print(
                    f"[WORKER][OK] Получен элемент из очереди: ID={tid} "
                    f"car={'есть' if car_crop is not None else 'нет'} "
                    f"plate={'есть' if plate_crop is not None else 'нет'}",
                    flush=True,
                )

                # ── ШАГ 4: MinIO ─────────────────────────────────────────
                crop_url, full_url = '', ''
                if full_thumb is not None:
                    try:
                        upload_crop = plate_crop if plate_crop is not None else car_crop
                        _, crop_buf = cv2.imencode('.jpg', upload_crop, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                        _, full_buf = cv2.imencode('.jpg', full_thumb, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                        crop_url, full_url = self.minio_storage.upload_plate_pair(
                            crop_buf=crop_buf.tobytes(),
                            full_buf=full_buf.tobytes(),
                            camera_name=self.name,
                            tid=tid,
                            ts=ts,
                        )
                        print(f"[MINIO][OK] ID={tid} crop={crop_url}", flush=True)
                    except Exception as e:
                        print(f"[MINIO][FAIL] ID={tid}: {e}", flush=True)

                # ── ШАГ 5: OCR ───────────────────────────────────────────
                ocr_target = plate_crop if plate_crop is not None else car_crop
                ocr_text = self.perform_ocr_and_save(ocr_target, tid, ts, crop_url=crop_url, full_url=full_url)

                if ocr_text and tid in self.tracks:
                    tr = self.tracks[tid]
                    tr.setdefault('ocr_history', []).append(ocr_text)
                    if len(tr['ocr_history']) > 30:
                        tr['ocr_history'].pop(0)

            except Exception as e:
                print(f"[WORKER][FAIL] Ошибка воркера {self.name}: {e}", flush=True)
                import traceback
                traceback.print_exc()
            finally:
                self.crop_queue.task_done()

    # ------------------------------------------------------------------
    # Жизненный цикл
    # ------------------------------------------------------------------

    def process_video(self):
        raise NotImplementedError

    def start_processing(self):
        self.logger.info(f"Starting processing for {self.name}")
        self.logger.info(f"Video: {self.video_source}, frames: {self.total_frames}, fps: {self.fps}")

        self.processing_thread = threading.Thread(target=self.process_video, daemon=True)
        self.processing_thread.start()

        for _ in range(self.OCR_WORKERS):
            t = threading.Thread(target=self.crop_saver_worker, daemon=True)
            t.start()
            self.worker_threads.append(t)

    def stop_processing(self):
        if self.cap:
            self.cap.release()
        if self.kafka_manager:
            try:
                self.kafka_manager.close()
            except Exception as e:
                self.logger.error(f"Error closing KafkaManager: {e}")
        self.logger.info(f"Processing stopped for {self.name}")