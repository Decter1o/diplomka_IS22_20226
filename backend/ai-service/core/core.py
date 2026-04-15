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
import tomllib
from ultralytics import YOLO
from paddleocr import PaddleOCR
from collections import Counter
from .logger import PlateLogger

class PlateProcessor:
    def __init__(self, video_source, name="default"):
        self.name = name
        self.video_source = video_source

        # Загрузка конфигурации
        config_path = os.path.join(os.path.dirname(__file__), 'comfig.toml')
        with open(config_path, 'rb') as f:
            config = tomllib.load(f)

        self.OCR_DEBUG = config['app']['OCR_DEBUG']
        self.OCR_WORKERS = config['app']['OCR_WORKERS']
        self.OCR_CONF_THRESHOLD = config['app']['OCR_CONF_THRESHOLD']
        self.OCR_BRIGHTNESS_LOW = config['app']['OCR_BRIGHTNESS_LOW']
        self.OCR_BRIGHTNESS_HIGH = config['app']['OCR_BRIGHTNESS_HIGH']
        self.ROI_RATIO = config['app']['ROI_RATIO']
        self.INACTIVE_FRAMES = config['app']['INACTIVE_FRAMES']

        # Настройка логирования
        self.logger = PlateLogger.get_logger(self.name)

        self.model = YOLO("ai-model/best.pt")

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
        self.logger.info(f"PaddleOCR loaded successfully for {self.name}")

        self.cap = cv2.VideoCapture(video_source)
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)

        self.current_frame_num = 0
        self.crop_queue = queue.Queue(maxsize=50)
        self.plates_dir = os.path.join(os.path.dirname(__file__), '..', 'plates')
        os.makedirs(self.plates_dir, exist_ok=True)

        self.ocr_csv_path = os.path.join(os.path.dirname(__file__), '..', 'ocr_results.csv')
        self.csv_lock = threading.Lock()
        if not os.path.exists(self.ocr_csv_path):
            with open(self.ocr_csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['camera', 'id', 'timestamp', 'ocr_text', 'confidence'])

        self.lock = threading.Lock()
        self.tracks = {}
        self.next_track_id = 1

        self.processing_thread = None
        self.worker_threads = []

    def preprocess_plate(self, img):
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

    def validate_plate(self, text):
        text = re.sub(r'[^A-Z0-9]', '', text)
        if len(text) >= 2:
            return text
        return ""

    def fix_common_ocr_errors(self, text):
        replacements = {
            'I': '1', 'l': '1', 'O': '0', 'B': '8', 'S': '5', 'Z': '2', 'G': '9', 'U': 'V'
        }
        return "".join(replacements.get(c, c) for c in text)

    def pick_best_text(self, history):
        if not history:
            return ""
        return Counter(history).most_common(1)[0][0]

    def extract_paddle_text(self, results):
        if not results:
            return "", 0.0
        parts = []
        confidences = []
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

    def perform_ocr_and_save(self, crop_img, tid, ts):
        try:
            self.logger.info(f"OCR START for {self.name} ID={tid}, crop shape={crop_img.shape}")
            processed1 = cv2.resize(crop_img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            start1 = time.time()
            results1 = self.reader.ocr(processed1)
            t1 = time.time() - start1
            ocr_text, avg_confidence = self.extract_paddle_text(results1)
            ocr_text = re.sub(r'\s+', '', ocr_text)
            self.logger.debug(f"OCR attempt 1 for {self.name} time={t1:.3f}s, conf={avg_confidence:.3f}, text='{ocr_text}'")

            if (not ocr_text) or (avg_confidence < self.OCR_CONF_THRESHOLD):
                gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)
                mean_val = float(np.mean(gray))
                if (mean_val < self.OCR_BRIGHTNESS_LOW or mean_val > self.OCR_BRIGHTNESS_HIGH) or (not ocr_text) or (avg_confidence < self.OCR_CONF_THRESHOLD):
                    self.logger.info(f"Fallback preprocess_plate for {self.name} ID={tid}")
                    pre = self.preprocess_plate(crop_img)
                    processed2 = cv2.cvtColor(pre, cv2.COLOR_GRAY2BGR)
                    processed2 = cv2.resize(processed2, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
                    start2 = time.time()
                    results2 = self.reader.ocr(processed2)
                    t2 = time.time() - start2
                    ocr_text2, avg_confidence2 = self.extract_paddle_text(results2)
                    ocr_text2 = re.sub(r'\s+', '', ocr_text2)
                    self.logger.debug(f"OCR attempt 2 for {self.name} time={t2:.3f}s, conf={avg_confidence2:.3f}, text='{ocr_text2}'")
                    if ocr_text2 and (avg_confidence2 >= avg_confidence):
                        ocr_text = ocr_text2
                        avg_confidence = avg_confidence2

            if not ocr_text:
                self.logger.warning(f"PaddleOCR found no text for {self.name} ID={tid}")
                return ''

            ocr_text = self.fix_common_ocr_errors(ocr_text)
            ocr_text = self.validate_plate(ocr_text)

            if ocr_text:
                with self.csv_lock:
                    with open(self.ocr_csv_path, 'a', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerow([self.name, tid, ts, ocr_text, f"{avg_confidence:.3f}"])
                self.logger.info(f"SUCCESS for {self.name} ID={tid}: '{ocr_text}' (conf={avg_confidence:.2f})")
            else:
                self.logger.warning(f"Text validation failed for {self.name} ID={tid}")

            return ocr_text
        except Exception as e:
            self.logger.error(f"OCR error for {self.name} ID={tid}: {e}")
            import traceback
            traceback.print_exc()
            return ''

    def center(self, box):
        x1, y1, x2, y2 = box
        return ((x1 + x2) // 2, (y1 + y2) // 2)

    def expand_box(self, box, frame_h, frame_w, padding=60):
        x1, y1, x2, y2 = box
        x1 = max(0, x1 - padding)
        y1 = max(0, y1 - padding)
        x2 = min(frame_w, x2 + padding)
        y2 = min(frame_h, y2 + padding)
        return (x1, y1, x2, y2)

    def process_video(self):
        frame_id = 0

        def iou(a, b):
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
            detected_boxes = []
            try:
                if frame_id % 120 == 0:
                    self.logger.info(f"Processing frame={frame_id} for {self.name}")

                ret, frame = self.cap.read()
                if not ret:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    self.current_frame_num = 0
                    continue

                frame_id += 1
                if frame_id % 2 != 0:
                    continue

                results = self.model(frame, verbose=False)
                h, w = frame.shape[:2]
                line_y = int(h * (1 - self.ROI_RATIO))
                pos_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))

                boxes = getattr(results[0], 'boxes', None)
                if frame_id % 120 == 0:
                    self.logger.debug(f"YOLO for {self.name} frame #{frame_id}: found {len(boxes) if boxes else 0} objects")

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
                        if (x2 - x1) < 40 or (y2 - y1) < 15:
                            continue
                        detected_boxes.append((x1, y1, x2, y2))

                matched_boxes = set()
                for tid, tr in list(self.tracks.items()):
                    best_iou = 0
                    best_box_idx = None
                    old_cx, old_cy = self.center(tr['last_box'])
                    for idx, box in enumerate(detected_boxes):
                        if idx in matched_boxes:
                            continue
                        i = iou(tr['last_box'], box)
                        if i > 0.2 and i > best_iou:
                            best_iou = i
                            best_box_idx = idx
                    if best_box_idx is not None:
                        tr['prev_center'] = (old_cx, old_cy)
                        tr['last_box'] = detected_boxes[best_box_idx]
                        tr['last_seen'] = pos_frame
                        matched_boxes.add(best_box_idx)
                        if not tr.get('saved'):
                            now = time.time()
                            if now - tr.get('last_ocr', 0) > 2:
                                x1, y1, x2, y2 = self.expand_box(tr['last_box'], h, w, padding=60)
                                crop = frame[y1:y2, x1:x2]
                                if crop.shape[1] >= 100 and crop.shape[0] >= 30:
                                    ts_inner = int(now * 1000)
                                    self.logger.debug(f"Queue put for {self.name} ID={tid}, crop={crop.shape}")
                                    try:
                                        self.crop_queue.put((crop, tid, ts_inner, None), block=False)
                                        tr['last_ocr'] = now
                                    except queue.Full:
                                        self.logger.warning(f"Queue full for {self.name}")
                    else:
                        if pos_frame - tr['last_seen'] > self.INACTIVE_FRAMES:
                            self.tracks.pop(tid, None)

                for idx, box in enumerate(detected_boxes):
                    if idx in matched_boxes:
                        continue
                    cx, cy = self.center(box)
                    too_close = False
                    for tr in self.tracks.values():
                        tcx, tcy = self.center(tr['last_box'])
                        dist = ((cx - tcx)**2 + (cy - tcy)**2) ** 0.5
                        if dist < 80:
                            too_close = True
                            break
                    if not too_close:
                        tid = self.next_track_id
                        self.next_track_id += 1
                        self.tracks[tid] = {
                            'last_box': box,
                            'last_seen': pos_frame,
                            'prev_center': self.center(box),
                            'saved': False,
                            'ocr_history': []
                        }
                        if cy >= line_y:
                            tr = self.tracks[tid]
                            tr['saved'] = True
                            expanded_box = self.expand_box(box, h, w, padding=60)
                            x1, y1, x2, y2 = expanded_box
                            crop = frame[y1:y2, x1:x2]
                            ts = int(time.time() * 1000)
                            try:
                                full_thumb = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
                            except Exception:
                                full_thumb = frame
                            try:
                                self.crop_queue.put((crop, tid, ts, full_thumb), block=False)
                            except queue.Full:
                                pass
                            self.logger.info(f"Vehicle {self.name} ID={tid} saved on creation")

                for tid, tr in list(self.tracks.items()):
                    if tr.get('saved'):
                        continue
                    cx, cy = self.center(tr['last_box'])
                    prev_cx, prev_cy = tr.get('prev_center', (cx, cy))
                    crossed = prev_cy < line_y and cy >= line_y
                    if crossed:
                        tr['saved'] = True
                        expanded_box = self.expand_box(tr['last_box'], h, w, padding=60)
                        x1, y1, x2, y2 = expanded_box
                        crop = frame[y1:y2, x1:x2]
                        ts = int(time.time() * 1000)
                        ocr_text = self.pick_best_text(tr.get('ocr_history', []))
                        if not ocr_text:
                            try:
                                full_thumb = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
                            except Exception:
                                full_thumb = frame
                            try:
                                self.crop_queue.put((crop, tid, ts, full_thumb), block=False)
                            except queue.Full:
                                pass
                        self.logger.info(f"Vehicle {self.name} ID={tid} saved on line crossing")

                self.current_frame_num = pos_frame

                if self.fps and self.fps > 0:
                    elapsed = time.time() - loop_start
                    wait = (1.0 / self.fps) - elapsed
                    if wait > 0:
                        time.sleep(wait)

            except Exception as e:
                self.logger.error(f"Error in process_video for {self.name}: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(0.1)
                continue

    def crop_saver_worker(self):
        self.logger.info(f"Worker started for {self.name}")
        worker_count = 0
        while True:
            try:
                item = self.crop_queue.get(timeout=1)
                worker_count += 1
                if isinstance(item, tuple) and len(item) == 4:
                    crop, tid, ts, full_thumb = item
                else:
                    crop, tid, ts = item
                    full_thumb = None
                self.logger.debug(f"Worker {self.name} #{worker_count} received: ID={tid}, shape={crop.shape}, has_full_thumb={full_thumb is not None}")
            except queue.Empty:
                if worker_count == 0:
                    self.logger.debug(f"Worker {self.name} waiting for data...")
                time.sleep(0.1)
                continue

            try:
                if crop.shape[1] < 80:
                    self.logger.warning(f"Worker {self.name} crop too small: {crop.shape[1]} (need >= 80)")
                    continue

                if full_thumb is not None:
                    try:
                        crop_filename = f"plate_{self.name}_{tid}_{ts}.jpg"
                        crop_path = os.path.join(self.plates_dir, crop_filename)
                        _, crop_buf = cv2.imencode('.jpg', crop, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                        with open(crop_path, 'wb') as f:
                            f.write(crop_buf.tobytes())

                        full_filename = f"plate_{self.name}_{tid}_{ts}_full.jpg"
                        full_path = os.path.join(self.plates_dir, full_filename)
                        _, full_buf = cv2.imencode('.jpg', full_thumb, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                        with open(full_path, 'wb') as f:
                            f.write(full_buf.tobytes())

                        self.logger.info(f"Worker {self.name} saved files for ID={tid}: {crop_filename}, {full_filename}")
                    except Exception as e:
                        self.logger.error(f"Worker {self.name} error saving files for ID={tid}: {e}")

                self.logger.debug(f"Worker {self.name} starting OCR for ID={tid}")
                ocr_text = self.perform_ocr_and_save(crop, tid, ts)
                self.logger.debug(f"Worker {self.name} OCR result: '{ocr_text}'")

                if ocr_text and tid in self.tracks:
                    tr = self.tracks[tid]
                    tr.setdefault('ocr_history', []).append(ocr_text)
                    if len(tr['ocr_history']) > 30:
                        tr['ocr_history'].pop(0)

                self.logger.debug(f"Worker {self.name} OCR finished: '{ocr_text}'")
            except Exception as e:
                self.logger.error(f"Worker {self.name} OCR error: {e}")
                import traceback
                traceback.print_exc()
                continue

    def start_processing(self):
        self.logger.info(f"Starting video processing for {self.name}")
        self.logger.info(f"Video: {self.video_source}")
        self.logger.info(f"Total frames: {self.total_frames}, FPS: {self.fps}")
        self.logger.info(f"CSV path: {self.ocr_csv_path}")
        self.logger.info(f"Plates dir: {self.plates_dir}")

        self.processing_thread = threading.Thread(target=self.process_video, daemon=True)
        self.processing_thread.start()
        self.logger.info(f"Thread process_video started for {self.name}")

        for i in range(self.OCR_WORKERS):
            worker_thread = threading.Thread(target=self.crop_saver_worker, daemon=True)
            worker_thread.start()
            self.worker_threads.append(worker_thread)
        self.logger.info(f"{self.OCR_WORKERS} OCR worker(s) started for {self.name}")
        self.logger.info(f"Video processing started for {self.name}")

    def stop_processing(self):
        if self.cap:
            self.cap.release()
        self.logger.info(f"Processing stopped for {self.name}")


def process_camera(name, url):
    processor = PlateProcessor(url, name)
    processor.start_processing()
    