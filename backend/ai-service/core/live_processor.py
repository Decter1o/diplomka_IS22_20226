import time
import queue
import cv2
from core.base_processor import BaseProcessor


class LiveCameraProcessor(BaseProcessor):
    """Обрабатывает непрерывный RTSP-поток.

    Цикл бесконечный — при обрыве потока перемотка на начало.
    Срабатывание: авто пересекает ROI-линию снизу + периодический OCR
    пока авто находится в зоне.
    FPS-троттлинг синхронизирует обработку с реальным временем потока.
    """

    # ── добавил─────────────────

    def _enqueue_track(self, frame, tr, tid, h, w, mark_saved=True):
        """Для LIVE: отправляем ТОЛЬКО номер (plate_crop), не машину."""
        plate_crop = None
        if tr.get('best_plate_box') is not None:
            plate_crop = self._crop_frame(frame, tr['best_plate_box'], h, w, padding=10)
            if plate_crop is not None and (plate_crop.shape[1] < 20 or plate_crop.shape[0] < 8):
                plate_crop = None

        # Если нет plate_crop — не добавляем в очередь
        if plate_crop is None:
            return

        try:
            full_thumb = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
        except Exception:
            full_thumb = frame

        ts = int(time.time() * 1000)
        try:
            # Отправляем ТОЛЬКО plate_crop, car_crop = None
            self.crop_queue.put((None, plate_crop, tid, ts, full_thumb), block=False)
            if mark_saved:
                tr['saved'] = True
        except queue.Full:
            print(f"[QUEUE][FAIL] Очередь переполнена, трек ID={tid} отброшен", flush=True)
            self.logger.warning(f"crop_queue full, dropping tid={tid}")

# ── добавил─────────────────

    def process_video(self):
        frame_id = 0
        self.logger.info(f"[LIVE] Starting for {self.name}, fps={self.fps}")

        while True:
            loop_start = time.time()
            try:
                if frame_id % 120 == 0:
                    self.logger.info(f"[LIVE] frame={frame_id} cam={self.name}")

                ret, frame = self.cap.read()
                if not ret:
                    self.logger.warning(f"[LIVE] Stream read failed for {self.name}, reconnecting in 3s...")
                    time.sleep(3)
                    self.cap.release()
                    self.cap = cv2.VideoCapture(self.video_source)
                    self.current_frame_num = 0
                    continue

                frame_id += 1
                if frame_id % 2 != 0:
                    continue

                h, w = frame.shape[:2]
                line_y = int(h * (1 - self.ROI_RATIO))
                pos_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
                self.current_frame_num = pos_frame

                car_dets, plate_dets = self._detect(frame, h, w, roi_y=line_y)
                car_to_plate = self._match_plates_to_cars(car_dets, plate_dets)
                new_tracks, car_index_to_tid = self._match_tracks(car_dets, pos_frame)
                self._update_plate_boxes(new_tracks, car_index_to_tid, car_to_plate)
                self.tracks = new_tracks
                self._remove_stale_tracks(pos_frame)

                # ── Аннотированный кадр для MJPEG-стрима ─────────────────
                annotated = frame.copy()
                for tid, tr in self.tracks.items():
                    x1, y1, x2, y2 = tr['last_box']
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 200, 0), 2)
                    cv2.putText(annotated, f"#{tid}", (x1, max(0, y1 - 6)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 0), 2)
                # Боксы номеров берём из текущего кадра (plate_dets), а не из best_plate_box
                for p in plate_dets:
                    px1, py1, px2, py2 = p['box']
                    cv2.rectangle(annotated, (px1, py1), (px2, py2), (0, 80, 255), 2)
                cv2.putText(
                    annotated,
                    f"frame {frame_id}/{self.total_frames} | tracks: {len(self.tracks)}",
                    (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 220, 255), 2,
                )
                try:
                    self.frame_queue.put_nowait(annotated)
                except queue.Full:
                    pass

                for tid, tr in list(self.tracks.items()):
                    if tr.get('saved'):
                        continue
                    cx, cy = self._center(tr['last_box'])
                    prev_cx, prev_cy = tr.get('prev_center', (cx, cy))
                    crossed = prev_cy < line_y <= cy

                    if crossed:
                        tr['saved'] = True
                        self._enqueue_track(frame, tr, tid, h, w)
                        self.logger.info(f"[LIVE] ID={tid} crossed line frame={pos_frame}")
                    elif cy >= line_y:
                        now = time.time()
                        if now - tr.get('last_ocr', 0) > 2:
                            self._enqueue_track(frame, tr, tid, h, w, mark_saved=False)
                            tr['last_ocr'] = now

            except Exception as e:
                self.logger.error(f"[LIVE] Error for {self.name}: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(0.1)