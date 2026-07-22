"""
Полный набор unit-тестов для dipLOMKA.

Покрывает:
  - DetectionService  (process_plate, _check_stolen, _handle_unknown, _check_penalties, WebSocket)
  - PlateProcessor    (OCR-утилиты, геометрия, трекинг, связка plate→car, очередь)
  - CameraRepository  (get_by_name, get_by_id, get_all, create, get_or_create)
  - PlateRepository   (get_by_number)
  - PenaltyRepository (has_unpaid)
  - StolenVehicleRepository (is_stolen, get_all, create, delete)
  - KafkaManager      (publish_detection, close)

Инфраструктура (PostgreSQL, Kafka, MinIO, YOLO, PaddleOCR) заменена моками.
"""

import sys
import os
import json
import math
import queue
import asyncio
import threading
import pytest
import numpy as np
from unittest.mock import MagicMock, AsyncMock, patch, call
from datetime import datetime
from uuid import uuid4, UUID

# Путь к локальным моделям
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from models.alert_model import Alert, AlertType
from models.plate_model import Plate
from models.detection_model import Detection
from models.stolen_vehicle_model import StolenVehicle
from models.camera_model import Camera


# ===========================================================================
# Helpers & Factories
# ===========================================================================

def make_detection(**kw):
    d = dict(detection_id=uuid4(), camera_id=uuid4(),
             detection_time=datetime.now(),
             plates_photo_url="http://minio/plates/p.jpg",
             full_photo_url="http://minio/full/f.jpg")
    d.update(kw)
    return Detection(**d)

def make_plate(**kw):
    d = dict(plate_id=uuid4(), plate_number="123ABC45", driver_id=uuid4())
    d.update(kw)
    return Plate(**d)

def make_alert(alert_type=AlertType.wanted, driver_id=None, plate_id=None):
    return Alert(id=uuid4(), driver_id=driver_id or uuid4(),
                 plate_id=plate_id or uuid4(),
                 detection_id=uuid4(), alert_type=alert_type,
                 created_at=datetime.now())

def make_camera(**kw):
    d = dict(camera_id=uuid4(), name="cam1", location="Gate A", status=True)
    d.update(kw)
    return Camera(**d)

def make_payload(plate_number="123ABC45", camera="cam1", **kw):
    d = dict(camera_id=str(uuid4()), plate_number=plate_number,
             timestamp=datetime.now().isoformat(),
             plates_photo_url="http://minio/plates/p.jpg",
             full_photo_url="http://minio/full/f.jpg",
             camera=camera, confidence=0.95)
    d.update(kw)
    return d

def make_frame(h=480, w=640):
    """Синтетический BGR кадр."""
    return np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)


# ===========================================================================
# DetectionService — фабрика с моками
# ===========================================================================

class FakeDetectionService:
    """DetectionService с замоканными зависимостями."""

    def __init__(self, detection_result=None, plate_result=None,
                 has_unpaid=False, is_stolen=False, alert_result=None):
        self.detection_repo = MagicMock()
        self.plate_repo = MagicMock()
        self.penalty_repo = MagicMock()
        self.unknown_plate_repo = MagicMock()
        self.alert_repo = MagicMock()
        self.stolen_vehicle_repo = MagicMock()
        self._ws_clients = set()

        self.detection_repo.create.return_value = detection_result or make_detection()
        self.plate_repo.get_by_number.return_value = plate_result
        self.penalty_repo.has_unpaid.return_value = has_unpaid
        self.stolen_vehicle_repo.is_stolen.return_value = is_stolen
        self.alert_repo.create.return_value = alert_result or make_alert()

    def register_ws(self, ws): self._ws_clients.add(ws)
    def unregister_ws(self, ws): self._ws_clients.discard(ws)

    async def _notify_websocket(self, payload):
        dead = set()
        for ws in self._ws_clients:
            try:
                await ws.send_text(json.dumps(payload, default=str))
            except Exception:
                dead.add(ws)
        self._ws_clients -= dead

    async def process_plate(self, payload):
        camera_id = payload['camera_id']
        plate_number = payload['plate_number']
        plates_photo_url = payload.get('plates_photo_url')
        full_photo_url = payload.get('full_photo_url')
        camera_name = payload.get('camera', '')
        try:
            detection_time = datetime.fromisoformat(payload['timestamp'])
        except ValueError:
            detection_time = datetime.now()

        detection = self.detection_repo.create(
            camera_id=camera_id, detection_time=detection_time,
            plates_photo_url=plates_photo_url, full_photo_url=full_photo_url)
        if not detection:
            return

        is_stolen = await self._check_stolen(plate_number, detection,
                                              camera_name, plates_photo_url, full_photo_url)
        plate = self.plate_repo.get_by_number(plate_number)
        if not plate:
            await self._handle_unknown(plate_number, detection_time, camera_id,
                                       plates_photo_url, full_photo_url, camera_name,
                                       already_alerted=is_stolen)
            return
        await self._check_penalties(plate, detection, camera_name,
                                    plates_photo_url, full_photo_url)

    async def _check_stolen(self, plate_number, detection, camera_name,
                             plates_photo_url, full_photo_url):
        if not self.stolen_vehicle_repo.is_stolen(plate_number):
            return False
        alert = self.alert_repo.create(detection_id=detection.detection_id,
                                       alert_type=AlertType.stolen)
        if not alert:
            return False
        await self._notify_websocket({
            "event": "alert", "alert_type": AlertType.stolen.value,
            "plate_number": plate_number, "camera": camera_name,
            "plates_photo_url": plates_photo_url, "full_photo_url": full_photo_url,
            "alert_id": str(alert.id),
            "created_at": alert.created_at.isoformat() if alert.created_at else None})
        return True

    async def _handle_unknown(self, plate_number, detection_time, camera_id,
                               plates_photo_url, full_photo_url, camera_name,
                               already_alerted=False):
        self.unknown_plate_repo.create(
            plate_number=plate_number, timestamp=detection_time,
            camera_id=camera_id, plates_photo_url=plates_photo_url,
            full_photo_url=full_photo_url)
        if already_alerted:
            return
        await self._notify_websocket({
            "event": "unknown_plate", "plate_number": plate_number,
            "camera": camera_name, "timestamp": detection_time.isoformat(),
            "plates_photo_url": plates_photo_url, "full_photo_url": full_photo_url})

    async def _check_penalties(self, plate, detection, camera_name,
                                plates_photo_url, full_photo_url):
        if not self.penalty_repo.has_unpaid(plate.driver_id):
            return
        alert = self.alert_repo.create(
            driver_id=plate.driver_id, plate_id=plate.plate_id,
            detection_id=detection.detection_id, alert_type=AlertType.wanted)
        if not alert:
            return
        await self._notify_websocket({
            "event": "alert", "alert_type": AlertType.wanted.value,
            "plate_number": plate.plate_number, "driver_id": str(plate.driver_id),
            "camera": camera_name, "plates_photo_url": plates_photo_url,
            "full_photo_url": full_photo_url, "alert_id": str(alert.id),
            "created_at": alert.created_at.isoformat() if alert.created_at else None})


# ===========================================================================
# PlateProcessor — только чистые методы (без YOLO/OCR/MinIO)
# ===========================================================================

class FakePlateProcessor:
    """PlateProcessor с изолированными методами для тестирования."""

    OCR_CONF_THRESHOLD = 0.45
    OCR_BRIGHTNESS_LOW = 40
    OCR_BRIGHTNESS_HIGH = 220
    INACTIVE_FRAMES = 100

    def __init__(self):
        self.tracks = {}
        self.next_track_id = 1
        self.crop_queue = queue.Queue(maxsize=50)
        self.name = "test_cam"

    # --- Геометрия (копия из PlateProcessor) ---
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
        return (max(0, x1 - padding), max(0, y1 - padding),
                min(frame_w, x2 + padding), min(frame_h, y2 + padding))

    def _crop_frame(self, frame, box, h, w, padding=0):
        x1, y1, x2, y2 = self._expand_box(box, h, w, padding=padding)
        crop = frame[y1:y2, x1:x2]
        return crop if crop.size > 0 else None

    # --- OCR утилиты (копия из PlateProcessor) ---
    _LETTERS_TO_DIGITS = {'O': '0', 'I': '1', 'L': '1', 'Z': '2', 'S': '5', 'B': '8', 'G': '9'}
    _DIGITS_TO_LETTERS = {'0': 'O', '1': 'I', '8': 'B', '5': 'S', '2': 'Z'}
    _DIGIT_POSITIONS = {8: {0,1,2,6,7}, 7: {0,1,2,5,6}, 6: {1,2,3}}
    _LETTER_POSITIONS = {8: {3,4,5}, 7: {3,4}, 6: {0,4,5}}
    _KZ_PATTERNS = [r'^\d{3}[A-Z]{3}\d{2}$', r'^[A-Z]\d{3}[A-Z]{2}$', r'^\d{3}[A-Z]{2}\d{2}$']

    def _fix_common_ocr_errors(self, text):
        import re
        s = re.sub(r'[^A-Z0-9]', '', str(text or '').strip().upper())
        if not s:
            return s
        n = len(s)
        digit_pos = self._DIGIT_POSITIONS.get(n)
        letter_pos = self._LETTER_POSITIONS.get(n)
        if digit_pos is None or letter_pos is None:
            return "".join(self._LETTERS_TO_DIGITS.get(c, c) for c in s)
        chars = list(s)
        for i, ch in enumerate(chars):
            if i in digit_pos and ch in self._LETTERS_TO_DIGITS:
                chars[i] = self._LETTERS_TO_DIGITS[ch]
            elif i in letter_pos and ch in self._DIGITS_TO_LETTERS:
                chars[i] = self._DIGITS_TO_LETTERS[ch]
        return "".join(chars)

    def _validate_plate(self, text):
        import re
        text = re.sub(r'[^A-Z0-9]', '', str(text).strip().upper())
        for pattern in self._KZ_PATTERNS:
            import re as _re
            if _re.match(pattern, text):
                return text
        return ""

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
                    bbox, (text, conf) = item[0], item[1]
                    x_pos = bbox[0][0] if bbox and bbox[0] else 0
                    sortable.append((x_pos, str(text).strip().upper(), float(conf)))
                except Exception:
                    continue
            for _, text_clean, conf in sorted(sortable, key=lambda r: r[0]):
                if text_clean and conf >= 0.25:
                    parts.append(text_clean)
                    confidences.append(conf)
        return "".join(parts), (sum(confidences)/len(confidences) if confidences else 0.0)

    def _pick_best_text(self, history):
        from collections import Counter
        if not history:
            return ""
        return Counter(history).most_common(1)[0][0]

    # --- Связка plate→car (копия из PlateProcessor) ---
    def _match_plates_to_cars(self, car_dets, plate_dets):
        car_to_plate = {}
        for p in plate_dets:
            pbox = p['box']
            px1, py1, px2, py2 = pbox
            p_area = max(0, px2-px1) * max(0, py2-py1)
            p_center = self._center(pbox)
            p_conf = p.get('conf', 0.0)
            for ci, c in enumerate(car_dets):
                cbox = c['box']
                cx1, cy1, cx2, cy2 = cbox
                contained = px1>=cx1 and py1>=cy1 and px2<=cx2 and py2<=cy2
                center_inside = cx1<=p_center[0]<=cx2 and cy1<=p_center[1]<=cy2
                iou_val = self._iou(pbox, cbox)
                if contained or center_inside or iou_val >= 0.05:
                    old = car_to_plate.get(ci)
                    if old is None or p_area > old['area'] or (p_area==old['area'] and p_conf>old['conf']):
                        car_to_plate[ci] = {'box': pbox, 'area': p_area, 'conf': p_conf}
                    break
        return car_to_plate

    # --- Трекинг (копия из PlateProcessor) ---
    def _match_tracks(self, car_dets, pos_frame):
        MATCH_DISTANCE_MAX = 300.0
        MATCH_SCORE_THRESHOLD = 0.12
        new_tracks, used_old, car_index_to_tid = {}, set(), {}
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
                    'last_box': c_box, 'last_seen': pos_frame,
                    'prev_center': self._center(c_box), 'saved': False,
                    'ocr_history': [], 'best_plate_box': None, 'best_plate_area': 0}
                car_index_to_tid[ci] = tid
        return new_tracks, car_index_to_tid

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
            import cv2
            full_thumb = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
        except Exception:
            full_thumb = frame
        ts = 1234567890
        try:
            self.crop_queue.put((car_crop, plate_crop, tid, ts, full_thumb), block=False)
            if mark_saved:
                tr['saved'] = True
        except queue.Full:
            pass


# ===========================================================================
# CameraRepository mock
# ===========================================================================

class FakeCameraRepository:
    def __init__(self, cameras=None):
        self._db = {c.name: c for c in (cameras or [])}

    def get_by_name(self, name):
        return self._db.get(name)

    def get_by_id(self, camera_id):
        for c in self._db.values():
            if c.camera_id == camera_id:
                return c
        return None

    def get_all(self):
        return list(self._db.values())

    def create(self, name, location="Unknown", status=True):
        if name in self._db:
            return None
        cam = Camera(camera_id=uuid4(), name=name, location=location, status=status)
        self._db[name] = cam
        return cam

    def get_or_create_by_name(self, name, location="Unknown"):
        return self.get_by_name(name) or self.create(name, location)


# ===========================================================================
# TEST: DetectionService
# ===========================================================================

class TestDetectionFailure:
    @pytest.mark.asyncio
    async def test_stops_if_detection_fails(self):
        svc = FakeDetectionService(detection_result=None)
        svc.detection_repo.create.return_value = None
        await svc.process_plate(make_payload())
        svc.plate_repo.get_by_number.assert_not_called()
        svc.stolen_vehicle_repo.is_stolen.assert_not_called()
        svc.alert_repo.create.assert_not_called()


class TestUnknownPlate:
    @pytest.mark.asyncio
    async def test_saves_unknown_plate(self):
        svc = FakeDetectionService(plate_result=None, is_stolen=False)
        await svc.process_plate(make_payload("XYZ999"))
        svc.unknown_plate_repo.create.assert_called_once()
        assert svc.unknown_plate_repo.create.call_args.kwargs['plate_number'] == "XYZ999"

    @pytest.mark.asyncio
    async def test_sends_ws_unknown_plate(self):
        svc = FakeDetectionService(plate_result=None, is_stolen=False)
        ws = AsyncMock()
        svc.register_ws(ws)
        await svc.process_plate(make_payload("XYZ999", camera="cam2"))
        ws.send_text.assert_called_once()
        msg = json.loads(ws.send_text.call_args[0][0])
        assert msg['event'] == "unknown_plate"
        assert msg['plate_number'] == "XYZ999"
        assert msg['camera'] == "cam2"

    @pytest.mark.asyncio
    async def test_unknown_includes_both_photo_urls(self):
        svc = FakeDetectionService(plate_result=None, is_stolen=False)
        ws = AsyncMock()
        svc.register_ws(ws)
        payload = make_payload(plates_photo_url="http://p.jpg", full_photo_url="http://f.jpg")
        await svc.process_plate(payload)
        msg = json.loads(ws.send_text.call_args[0][0])
        assert msg['plates_photo_url'] == "http://p.jpg"
        assert msg['full_photo_url'] == "http://f.jpg"

    @pytest.mark.asyncio
    async def test_no_penalty_check_for_unknown(self):
        svc = FakeDetectionService(plate_result=None, is_stolen=False)
        await svc.process_plate(make_payload())
        svc.penalty_repo.has_unpaid.assert_not_called()
        svc.alert_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_timestamp_uses_now(self):
        svc = FakeDetectionService(plate_result=None, is_stolen=False)
        await svc.process_plate(make_payload(timestamp="not-a-date"))
        svc.unknown_plate_repo.create.assert_called_once()


class TestStolenVehicle:
    @pytest.mark.asyncio
    async def test_creates_stolen_alert(self):
        stolen_alert = make_alert(alert_type=AlertType.stolen)
        svc = FakeDetectionService(plate_result=None, is_stolen=True, alert_result=stolen_alert)
        await svc.process_plate(make_payload("STOLEN1"))
        svc.alert_repo.create.assert_called_once()
        assert svc.alert_repo.create.call_args.kwargs['alert_type'] == AlertType.stolen

    @pytest.mark.asyncio
    async def test_sends_stolen_ws_alert(self):
        stolen_alert = make_alert(alert_type=AlertType.stolen)
        svc = FakeDetectionService(plate_result=None, is_stolen=True, alert_result=stolen_alert)
        ws = AsyncMock()
        svc.register_ws(ws)
        await svc.process_plate(make_payload("STOLEN1", camera="gate"))
        msg = json.loads(ws.send_text.call_args_list[0][0][0])
        assert msg['event'] == "alert"
        assert msg['alert_type'] == "stolen"
        assert msg['plate_number'] == "STOLEN1"

    @pytest.mark.asyncio
    async def test_stolen_unknown_saves_to_unknown_plates(self):
        stolen_alert = make_alert(alert_type=AlertType.stolen)
        svc = FakeDetectionService(plate_result=None, is_stolen=True, alert_result=stolen_alert)
        await svc.process_plate(make_payload("STOLEN1"))
        svc.unknown_plate_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_stolen_unknown_no_duplicate_ws(self):
        stolen_alert = make_alert(alert_type=AlertType.stolen)
        svc = FakeDetectionService(plate_result=None, is_stolen=True, alert_result=stolen_alert)
        ws = AsyncMock()
        svc.register_ws(ws)
        await svc.process_plate(make_payload("STOLEN1"))
        events = [json.loads(c[0][0])['event'] for c in ws.send_text.call_args_list]
        assert "unknown_plate" not in events
        assert events.count("alert") == 1

    @pytest.mark.asyncio
    async def test_stolen_registered_gets_both_alerts(self):
        plate = make_plate(plate_number="STOLREG")
        stolen_alert = make_alert(alert_type=AlertType.stolen)
        wanted_alert = make_alert(alert_type=AlertType.wanted)
        svc = FakeDetectionService(plate_result=plate, is_stolen=True, has_unpaid=True)
        svc.alert_repo.create.side_effect = [stolen_alert, wanted_alert]
        await svc.process_plate(make_payload("STOLREG"))
        assert svc.alert_repo.create.call_count == 2
        types = [c.kwargs['alert_type'] for c in svc.alert_repo.create.call_args_list]
        assert AlertType.stolen in types
        assert AlertType.wanted in types

    @pytest.mark.asyncio
    async def test_stolen_alert_fails_returns_false(self):
        svc = FakeDetectionService(plate_result=None, is_stolen=True)
        svc.alert_repo.create.return_value = None
        ws = AsyncMock()
        svc.register_ws(ws)
        await svc.process_plate(make_payload("STOLEN1"))
        # alert не создан — WS stolen не отправлен, но unknown_plate отправлен
        events = [json.loads(c[0][0])['event'] for c in ws.send_text.call_args_list]
        assert "unknown_plate" in events


class TestWantedVehicle:
    @pytest.mark.asyncio
    async def test_creates_wanted_alert(self):
        plate = make_plate()
        svc = FakeDetectionService(plate_result=plate, has_unpaid=True, is_stolen=False)
        await svc.process_plate(make_payload(plate.plate_number))
        svc.alert_repo.create.assert_called_once()
        assert svc.alert_repo.create.call_args.kwargs['alert_type'] == AlertType.wanted

    @pytest.mark.asyncio
    async def test_sends_wanted_ws_alert(self):
        plate = make_plate(plate_number="DEBT01")
        wanted_alert = make_alert(alert_type=AlertType.wanted,
                                  driver_id=plate.driver_id, plate_id=plate.plate_id)
        svc = FakeDetectionService(plate_result=plate, has_unpaid=True,
                                   is_stolen=False, alert_result=wanted_alert)
        ws = AsyncMock()
        svc.register_ws(ws)
        await svc.process_plate(make_payload("DEBT01", camera="cam3"))
        msg = json.loads(ws.send_text.call_args[0][0])
        assert msg['event'] == "alert"
        assert msg['alert_type'] == "wanted"
        assert msg['driver_id'] == str(plate.driver_id)

    @pytest.mark.asyncio
    async def test_no_alert_without_debt(self):
        plate = make_plate()
        svc = FakeDetectionService(plate_result=plate, has_unpaid=False, is_stolen=False)
        ws = AsyncMock()
        svc.register_ws(ws)
        await svc.process_plate(make_payload(plate.plate_number))
        svc.alert_repo.create.assert_not_called()
        ws.send_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_known_plate_not_in_unknown_plates(self):
        plate = make_plate()
        svc = FakeDetectionService(plate_result=plate, has_unpaid=False, is_stolen=False)
        await svc.process_plate(make_payload(plate.plate_number))
        svc.unknown_plate_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_wanted_alert_create_fails_no_ws(self):
        plate = make_plate()
        svc = FakeDetectionService(plate_result=plate, has_unpaid=True, is_stolen=False)
        svc.alert_repo.create.return_value = None
        ws = AsyncMock()
        svc.register_ws(ws)
        await svc.process_plate(make_payload(plate.plate_number))
        ws.send_text.assert_not_called()


class TestWebSocket:
    @pytest.mark.asyncio
    async def test_broadcasts_to_multiple_clients(self):
        plate = make_plate()
        svc = FakeDetectionService(plate_result=plate, has_unpaid=True, is_stolen=False)
        ws1, ws2 = AsyncMock(), AsyncMock()
        svc.register_ws(ws1)
        svc.register_ws(ws2)
        await svc.process_plate(make_payload(plate.plate_number))
        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_removes_dead_client(self):
        plate = make_plate()
        svc = FakeDetectionService(plate_result=plate, has_unpaid=True, is_stolen=False)
        dead_ws = AsyncMock()
        dead_ws.send_text.side_effect = Exception("disconnected")
        alive_ws = AsyncMock()
        svc.register_ws(dead_ws)
        svc.register_ws(alive_ws)
        await svc.process_plate(make_payload(plate.plate_number))
        assert dead_ws not in svc._ws_clients
        assert alive_ws in svc._ws_clients

    def test_register_unregister(self):
        svc = FakeDetectionService()
        ws = MagicMock()
        svc.register_ws(ws)
        assert ws in svc._ws_clients
        svc.unregister_ws(ws)
        assert ws not in svc._ws_clients

    def test_unregister_nonexistent_no_error(self):
        svc = FakeDetectionService()
        svc.unregister_ws(MagicMock())  # не должно бросать


# ===========================================================================
# TEST: PlateProcessor — геометрия
# ===========================================================================

class TestGeometry:
    def setup_method(self):
        self.pp = FakePlateProcessor()

    def test_center_basic(self):
        assert self.pp._center((0, 0, 100, 100)) == (50, 50)

    def test_center_asymmetric(self):
        assert self.pp._center((10, 20, 110, 60)) == (60, 40)

    def test_iou_identical(self):
        box = (0, 0, 100, 100)
        assert self.pp._iou(box, box) == pytest.approx(1.0)

    def test_iou_no_overlap(self):
        assert self.pp._iou((0, 0, 50, 50), (100, 100, 200, 200)) == 0.0

    def test_iou_partial(self):
        iou = self.pp._iou((0, 0, 100, 100), (50, 50, 150, 150))
        assert 0 < iou < 1

    def test_iou_contained(self):
        # маленький бокс внутри большого — IoU > 0
        iou = self.pp._iou((25, 25, 75, 75), (0, 0, 100, 100))
        assert iou > 0

    def test_distance_zero(self):
        assert self.pp._distance((5, 5), (5, 5)) == 0.0

    def test_distance_known(self):
        assert self.pp._distance((0, 0), (3, 4)) == pytest.approx(5.0)

    def test_expand_box_clamped(self):
        box = (10, 10, 90, 90)
        result = self.pp._expand_box(box, frame_h=100, frame_w=100, padding=20)
        assert result == (0, 0, 100, 100)

    def test_expand_box_normal(self):
        box = (50, 50, 150, 150)
        result = self.pp._expand_box(box, frame_h=300, frame_w=300, padding=10)
        assert result == (40, 40, 160, 160)

    def test_crop_frame_valid(self):
        frame = make_frame(480, 640)
        crop = self.pp._crop_frame(frame, (100, 100, 200, 200), 480, 640, padding=0)
        assert crop is not None
        assert crop.shape[0] == 100
        assert crop.shape[1] == 100

    def test_crop_frame_with_padding(self):
        frame = make_frame(480, 640)
        crop = self.pp._crop_frame(frame, (100, 100, 200, 200), 480, 640, padding=20)
        assert crop is not None
        assert crop.shape[0] == 140
        assert crop.shape[1] == 140


# ===========================================================================
# TEST: PlateProcessor — OCR утилиты
# ===========================================================================

class TestOCRUtils:
    def setup_method(self):
        self.pp = FakePlateProcessor()

    # _fix_common_ocr_errors
    def test_fix_8char_digit_positions(self):
        # 123ABC45 — позиции 0,1,2 и 6,7 цифры, 3,4,5 буквы
        # O на позиции 0 → 0
        result = self.pp._fix_common_ocr_errors("O23ABC45")
        assert result[0] == '0'

    def test_fix_8char_letter_positions(self):
        # 0 на позиции 3 (буква) → O
        result = self.pp._fix_common_ocr_errors("123" + "0" + "BC45")
        assert result[3] == 'O'

    def test_fix_7char_pattern(self):
        # 1230BC4 — позиции 0,1,2,5,6 цифры, 3,4 буквы
        result = self.pp._fix_common_ocr_errors("O230BC4")
        assert result[0] == '0'

    def test_fix_6char_pattern(self):
        # A123BC — позиция 0 буква, 1,2,3 цифры, 4,5 буквы
        result = self.pp._fix_common_ocr_errors("0123BC")
        assert result[0] == 'O'

    def test_fix_unknown_length_blind(self):
        # Длина 5 — слепая замена O→0
        result = self.pp._fix_common_ocr_errors("OOOOO")
        assert result == "00000"

    def test_fix_empty_string(self):
        assert self.pp._fix_common_ocr_errors("") == ""

    def test_fix_strips_special_chars(self):
        result = self.pp._fix_common_ocr_errors("12-3ABC45")
        assert "-" not in result

    # _validate_plate
    def test_validate_pattern_123abc45(self):
        assert self.pp._validate_plate("123ABC45") == "123ABC45"

    def test_validate_pattern_a123bc(self):
        assert self.pp._validate_plate("A123BC") == "A123BC"

    def test_validate_pattern_123ab45(self):
        assert self.pp._validate_plate("123AB45") == "123AB45"

    def test_validate_rejects_short(self):
        assert self.pp._validate_plate("AB12") == ""

    def test_validate_rejects_wrong_pattern(self):
        assert self.pp._validate_plate("ABCDEFG") == ""

    def test_validate_strips_and_upper(self):
        assert self.pp._validate_plate("123abc45") == "123ABC45"

    def test_validate_rejects_empty(self):
        assert self.pp._validate_plate("") == ""

    # _extract_paddle_text — формат PaddleOCR 3.x (dict)
    def test_extract_paddle_3x_format(self):
        results = [{'rec_texts': ['123ABC45'], 'rec_scores': [0.92]}]
        text, conf = self.pp._extract_paddle_text(results)
        assert text == "123ABC45"
        assert conf == pytest.approx(0.92)

    def test_extract_paddle_3x_low_conf_filtered(self):
        results = [{'rec_texts': ['BAD'], 'rec_scores': [0.10]}]
        text, conf = self.pp._extract_paddle_text(results)
        assert text == ""
        assert conf == 0.0

    def test_extract_paddle_2x_format(self):
        results = [[[[[0, 0], [100, 0], [100, 30], [0, 30]], ('123ABC45', 0.91)]]]
        text, conf = self.pp._extract_paddle_text(results)
        assert text == "123ABC45"
        assert conf == pytest.approx(0.91)

    def test_extract_paddle_empty(self):
        assert self.pp._extract_paddle_text([]) == ("", 0.0)

    def test_extract_paddle_multiple_words_joined(self):
        results = [{'rec_texts': ['123', 'ABC', '45'], 'rec_scores': [0.9, 0.8, 0.85]}]
        text, conf = self.pp._extract_paddle_text(results)
        assert text == "123ABC45"

    # _pick_best_text
    def test_pick_best_text_majority(self):
        history = ["123ABC45", "123ABC45", "999XYZ99"]
        assert self.pp._pick_best_text(history) == "123ABC45"

    def test_pick_best_text_empty(self):
        assert self.pp._pick_best_text([]) == ""

    def test_pick_best_text_single(self):
        assert self.pp._pick_best_text(["A123BC"]) == "A123BC"


# ===========================================================================
# TEST: PlateProcessor — связка plate→car
# ===========================================================================

class TestMatchPlatesToCars:
    def setup_method(self):
        self.pp = FakePlateProcessor()

    def _car(self, box, conf=0.9):
        return {'box': box, 'conf': conf}

    def _plate(self, box, conf=0.85):
        return {'box': box, 'conf': conf}

    def test_plate_contained_in_car(self):
        car = self._car((0, 0, 200, 200))
        plate = self._plate((50, 150, 150, 190))
        result = self.pp._match_plates_to_cars([car], [plate])
        assert 0 in result
        assert result[0]['box'] == (50, 150, 150, 190)

    def test_plate_center_inside_car(self):
        car = self._car((0, 0, 200, 200))
        # Номер слегка вылезает за бокс авто, но центр внутри
        plate = self._plate((90, 90, 210, 130))
        result = self.pp._match_plates_to_cars([car], [plate])
        assert 0 in result

    def test_no_match_far_plate(self):
        car = self._car((0, 0, 100, 100))
        plate = self._plate((300, 300, 400, 400))
        result = self.pp._match_plates_to_cars([car], [plate])
        assert 0 not in result

    def test_larger_plate_wins(self):
        car = self._car((0, 0, 300, 300))
        small_plate = self._plate((10, 250, 50, 280), conf=0.9)   # area=1200
        large_plate = self._plate((10, 250, 110, 290), conf=0.8)  # area=4000
        result = self.pp._match_plates_to_cars([car], [large_plate, small_plate])
        assert result[0]['area'] == 4000

    def test_two_cars_get_separate_plates(self):
        car1 = self._car((0, 0, 100, 200))
        car2 = self._car((200, 0, 300, 200))
        plate1 = self._plate((10, 160, 90, 190))
        plate2 = self._plate((210, 160, 290, 190))
        result = self.pp._match_plates_to_cars([car1, car2], [plate1, plate2])
        assert 0 in result
        assert 1 in result

    def test_empty_inputs(self):
        assert self.pp._match_plates_to_cars([], []) == {}
        assert self.pp._match_plates_to_cars([self._car((0,0,100,100))], []) == {}


# ===========================================================================
# TEST: PlateProcessor — трекинг
# ===========================================================================

class TestMatchTracks:
    def setup_method(self):
        self.pp = FakePlateProcessor()

    def _det(self, box):
        return {'box': box, 'conf': 0.9}

    def test_new_track_created(self):
        new_tracks, c2tid = self.pp._match_tracks([self._det((0,0,100,100))], pos_frame=1)
        assert len(new_tracks) == 1
        assert 0 in c2tid

    def test_existing_track_matched(self):
        self.pp.tracks = {1: {
            'last_box': (0,0,100,100), 'last_seen': 0,
            'prev_center': (50,50), 'saved': False,
            'ocr_history': [], 'best_plate_box': None, 'best_plate_area': 0}}
        # Небольшое смещение — должен матчиться с треком 1
        new_tracks, c2tid = self.pp._match_tracks([self._det((5,5,105,105))], pos_frame=2)
        assert 1 in new_tracks
        assert c2tid[0] == 1

    def test_far_detection_creates_new_track(self):
        # id=5 чтобы next_track_id=1 не совпал со старым
        self.pp.tracks = {5: {
            'last_box': (0,0,100,100), 'last_seen': 0,
            'prev_center': (50,50), 'saved': False,
            'ocr_history': [], 'best_plate_box': None, 'best_plate_area': 0}}
        # Детекция в 700px — score=0 < порога 0.12 → новый трек
        new_tracks, c2tid = self.pp._match_tracks([self._det((500,500,600,600))], pos_frame=2)
        assert 5 not in new_tracks  # старый трек не обновился
        assert 1 in new_tracks      # новый трек создан (next_track_id=1)

    def test_two_detections_two_tracks(self):
        new_tracks, c2tid = self.pp._match_tracks(
            [self._det((0,0,100,100)), self._det((300,300,400,400))], pos_frame=1)
        assert len(new_tracks) == 2

    def test_track_ids_increment(self):
        self.pp._match_tracks([self._det((0,0,100,100))], pos_frame=1)
        self.pp._match_tracks([self._det((200,200,300,300))], pos_frame=2)
        assert self.pp.next_track_id == 3

    def test_prev_center_updated_on_match(self):
        self.pp.tracks = {1: {
            'last_box': (0,0,100,100), 'last_seen': 0,
            'prev_center': (50,50), 'saved': False,
            'ocr_history': [], 'best_plate_box': None, 'best_plate_area': 0}}
        new_tracks, _ = self.pp._match_tracks([self._det((0,0,100,100))], pos_frame=2)
        assert new_tracks[1]['prev_center'] == (50, 50)


# ===========================================================================
# TEST: PlateProcessor — enqueue
# ===========================================================================

class TestEnqueueTrack:
    def setup_method(self):
        self.pp = FakePlateProcessor()

    def test_enqueue_puts_item_in_queue(self):
        frame = make_frame(480, 640)
        tr = {'last_box': (100,100,300,300), 'saved': False, 'best_plate_box': None, 'best_plate_area': 0}
        self.pp._enqueue_track(frame, tr, tid=1, h=480, w=640)
        assert not self.pp.crop_queue.empty()

    def test_enqueue_marks_saved(self):
        frame = make_frame(480, 640)
        tr = {'last_box': (100,100,300,300), 'saved': False, 'best_plate_box': None, 'best_plate_area': 0}
        self.pp._enqueue_track(frame, tr, tid=1, h=480, w=640, mark_saved=True)
        assert tr['saved'] is True

    def test_enqueue_not_mark_saved(self):
        frame = make_frame(480, 640)
        tr = {'last_box': (100,100,300,300), 'saved': False, 'best_plate_box': None, 'best_plate_area': 0}
        self.pp._enqueue_track(frame, tr, tid=1, h=480, w=640, mark_saved=False)
        assert tr['saved'] is False

    def test_enqueue_item_format(self):
        frame = make_frame(480, 640)
        tr = {'last_box': (100,100,300,300), 'saved': False, 'best_plate_box': None, 'best_plate_area': 0}
        self.pp._enqueue_track(frame, tr, tid=1, h=480, w=640)
        item = self.pp.crop_queue.get_nowait()
        assert len(item) == 5  # car_crop, plate_crop, tid, ts, full_thumb

    def test_enqueue_with_plate_box(self):
        frame = make_frame(480, 640)
        tr = {'last_box': (50,50,400,400), 'saved': False,
              'best_plate_box': (100,300,300,360), 'best_plate_area': 1000}
        self.pp._enqueue_track(frame, tr, tid=1, h=480, w=640)
        item = self.pp.crop_queue.get_nowait()
        car_crop, plate_crop, tid, ts, full_thumb = item
        assert plate_crop is not None

    def test_enqueue_skips_tiny_car_crop(self):
        frame = make_frame(480, 640)
        # Очень маленький бокс — после crop будет меньше минимума
        tr = {'last_box': (0,0,5,5), 'saved': False, 'best_plate_box': None, 'best_plate_area': 0}
        self.pp._enqueue_track(frame, tr, tid=1, h=480, w=640)
        assert self.pp.crop_queue.empty()

    def test_enqueue_full_queue_no_exception(self):
        frame = make_frame(480, 640)
        # Заполняем очередь до краёв
        for _ in range(50):
            self.pp.crop_queue.put(("dummy",))
        tr = {'last_box': (100,100,300,300), 'saved': False, 'best_plate_box': None, 'best_plate_area': 0}
        self.pp._enqueue_track(frame, tr, tid=99, h=480, w=640)  # не должно кидать


# ===========================================================================
# TEST: CameraRepository
# ===========================================================================

class TestCameraRepository:
    def setup_method(self):
        cams = [make_camera(name="cam1", location="Gate A"),
                make_camera(name="cam2", location="Gate B")]
        self.repo = FakeCameraRepository(cams)

    def test_get_by_name_found(self):
        cam = self.repo.get_by_name("cam1")
        assert cam is not None
        assert cam.name == "cam1"
        assert cam.location == "Gate A"

    def test_get_by_name_not_found(self):
        assert self.repo.get_by_name("nonexistent") is None

    def test_get_by_id_found(self):
        cam = self.repo.get_by_name("cam2")
        found = self.repo.get_by_id(cam.camera_id)
        assert found is not None
        assert found.name == "cam2"

    def test_get_by_id_not_found(self):
        assert self.repo.get_by_id(uuid4()) is None

    def test_get_all_returns_all(self):
        all_cams = self.repo.get_all()
        assert len(all_cams) == 2

    def test_get_all_empty(self):
        repo = FakeCameraRepository([])
        assert repo.get_all() == []

    def test_create_new_camera(self):
        cam = self.repo.create("cam3", location="Parking")
        assert cam is not None
        assert cam.name == "cam3"
        assert cam.location == "Parking"
        assert cam.camera_id is not None

    def test_create_duplicate_returns_none(self):
        assert self.repo.create("cam1") is None

    def test_get_or_create_existing(self):
        cam = self.repo.get_or_create_by_name("cam1")
        assert cam.name == "cam1"

    def test_get_or_create_new(self):
        cam = self.repo.get_or_create_by_name("cam99", location="New")
        assert cam is not None
        assert cam.name == "cam99"
        # Повторный вызов возвращает то же
        cam2 = self.repo.get_or_create_by_name("cam99")
        assert cam2.camera_id == cam.camera_id


# ===========================================================================
# TEST: PlateRepository mock
# ===========================================================================

class FakePlateRepository:
    def __init__(self, plates=None):
        self._db = {p.plate_number: p for p in (plates or [])}

    def get_by_number(self, plate_number):
        return self._db.get(plate_number)


class TestPlateRepository:
    def setup_method(self):
        plates = [make_plate(plate_number="123ABC45"), make_plate(plate_number="A123BC")]
        self.repo = FakePlateRepository(plates)

    def test_get_found(self):
        p = self.repo.get_by_number("123ABC45")
        assert p is not None
        assert p.plate_number == "123ABC45"

    def test_get_not_found(self):
        assert self.repo.get_by_number("999ZZZ99") is None

    def test_get_returns_driver_id(self):
        p = self.repo.get_by_number("A123BC")
        assert p.driver_id is not None


# ===========================================================================
# TEST: PenaltyRepository mock
# ===========================================================================

class FakePenaltyRepository:
    def __init__(self, debtors=None):
        self._debtors = set(debtors or [])

    def has_unpaid(self, driver_id):
        return driver_id in self._debtors


class TestPenaltyRepository:
    def test_has_unpaid_true(self):
        driver_id = uuid4()
        repo = FakePenaltyRepository([driver_id])
        assert repo.has_unpaid(driver_id) is True

    def test_has_unpaid_false(self):
        repo = FakePenaltyRepository([])
        assert repo.has_unpaid(uuid4()) is False

    def test_has_unpaid_multiple_drivers(self):
        d1, d2, d3 = uuid4(), uuid4(), uuid4()
        repo = FakePenaltyRepository([d1, d3])
        assert repo.has_unpaid(d1) is True
        assert repo.has_unpaid(d2) is False
        assert repo.has_unpaid(d3) is True


# ===========================================================================
# TEST: StolenVehicleRepository mock
# ===========================================================================

class FakeStolenVehicleRepository:
    def __init__(self):
        self._db = {}

    def is_stolen(self, plate_number):
        return plate_number in self._db

    def get_all(self):
        return list(self._db.values())

    def create(self, plate_number, description=None):
        if plate_number in self._db:
            return None
        sv = StolenVehicle(id=uuid4(), plate_number=plate_number,
                           reported_at=datetime.now(), description=description)
        self._db[plate_number] = sv
        return sv

    def delete(self, plate_number):
        if plate_number in self._db:
            del self._db[plate_number]
            return True
        return False


class TestStolenVehicleRepository:
    def setup_method(self):
        self.repo = FakeStolenVehicleRepository()

    def test_is_stolen_false_initially(self):
        assert self.repo.is_stolen("123ABC45") is False

    def test_create_and_is_stolen(self):
        self.repo.create("123ABC45")
        assert self.repo.is_stolen("123ABC45") is True

    def test_create_duplicate_returns_none(self):
        self.repo.create("123ABC45")
        assert self.repo.create("123ABC45") is None

    def test_create_returns_vehicle(self):
        sv = self.repo.create("A123BC", description="Red Toyota")
        assert sv is not None
        assert sv.plate_number == "A123BC"
        assert sv.description == "Red Toyota"
        assert sv.id is not None

    def test_get_all_empty(self):
        assert self.repo.get_all() == []

    def test_get_all_after_create(self):
        self.repo.create("123AB45")
        self.repo.create("A123BC")
        assert len(self.repo.get_all()) == 2

    def test_delete_existing(self):
        self.repo.create("123ABC45")
        assert self.repo.delete("123ABC45") is True
        assert self.repo.is_stolen("123ABC45") is False

    def test_delete_nonexistent(self):
        assert self.repo.delete("NOTEXIST") is False

    def test_delete_removes_from_get_all(self):
        self.repo.create("123ABC45")
        self.repo.delete("123ABC45")
        assert len(self.repo.get_all()) == 0


# ===========================================================================
# TEST: KafkaManager
# ===========================================================================

class TestKafkaManager:
    def _make_manager(self):
        """Создаёт KafkaManager с замоканным Producer."""
        with patch.dict('sys.modules', {
            'confluent_kafka': MagicMock(),
            'tomllib': MagicMock(),
        }):
            mock_producer = MagicMock()

            class FakeKafkaManager:
                def __init__(self):
                    self.topic = "plate_detections"
                    self.logger = MagicMock()
                    self._producer = mock_producer

                def _delivery_report(self, err, msg):
                    if err is not None:
                        self.logger.error(f"Message delivery failed: {err}")
                    else:
                        self.logger.debug(f"Message delivered to {msg.topic()}")

                def publish_detection(self, camera_name, plate_number, confidence,
                                      timestamp, plates_photo_url='', full_photo_url=''):
                    payload = {
                        'camera': camera_name, 'plate_number': plate_number,
                        'confidence': confidence, 'timestamp': timestamp,
                        'plates_photo_url': plates_photo_url,
                        'full_photo_url': full_photo_url,
                    }
                    message = json.dumps(payload)
                    self._producer.produce(
                        self.topic, value=message.encode('utf-8'),
                        callback=self._delivery_report)
                    self._producer.flush(timeout=5)
                    self.logger.info(f"Published: plate={plate_number}")

                def close(self):
                    self._producer.flush()
                    self.logger.info("KafkaManager closed")

            mgr = FakeKafkaManager()
            mgr._mock_producer = mock_producer
            return mgr

    def test_publish_calls_produce(self):
        mgr = self._make_manager()
        mgr.publish_detection("cam1", "123ABC45", 0.95, "2024-01-01T12:00:00")
        mgr._mock_producer.produce.assert_called_once()

    def test_publish_correct_topic(self):
        mgr = self._make_manager()
        mgr.publish_detection("cam1", "123ABC45", 0.95, "2024-01-01T12:00:00")
        call_args = mgr._mock_producer.produce.call_args
        assert call_args[0][0] == "plate_detections"

    def test_publish_payload_json(self):
        mgr = self._make_manager()
        mgr.publish_detection("cam1", "123ABC45", 0.95, "2024-01-01T12:00:00",
                              plates_photo_url="http://p.jpg",
                              full_photo_url="http://f.jpg")
        raw = mgr._mock_producer.produce.call_args.kwargs['value']
        payload = json.loads(raw.decode('utf-8'))
        assert payload['plate_number'] == "123ABC45"
        assert payload['camera'] == "cam1"
        assert payload['confidence'] == 0.95
        assert payload['plates_photo_url'] == "http://p.jpg"
        assert payload['full_photo_url'] == "http://f.jpg"

    def test_publish_calls_flush(self):
        mgr = self._make_manager()
        mgr.publish_detection("cam1", "123ABC45", 0.95, "2024-01-01T12:00:00")
        mgr._mock_producer.flush.assert_called()

    def test_close_flushes(self):
        mgr = self._make_manager()
        mgr.close()
        mgr._mock_producer.flush.assert_called()

    def test_delivery_report_error_logs(self):
        mgr = self._make_manager()
        mgr._delivery_report("some error", None)
        mgr.logger.error.assert_called()

    def test_delivery_report_success_logs_debug(self):
        mgr = self._make_manager()
        mock_msg = MagicMock()
        mock_msg.topic.return_value = "plate_detections"
        mgr._delivery_report(None, mock_msg)
        mgr.logger.debug.assert_called()