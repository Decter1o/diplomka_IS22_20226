import time
import queue
import cv2
from core.base_processor import BaseProcessor


class VideoFileProcessor(BaseProcessor):
    """Обрабатывает загруженный видеофайл за один проход.

    Отличия от LiveCameraProcessor:
    - Один проход: при EOF цикл завершается.
    - Без FPS-троттлинга: обработка идёт на максимальной скорости.
    - Без ROI-линии: номера принимаются из всего кадра, угол камеры неизвестен.
    - Срабатывание: любой трек с видимым номером, периодический OCR раз в секунду.
    """

    def process_video(self):
        frame_id = 0

        # ── ШАГ 1: открытие файла ────────────────────────────────────────
        if not self.cap.isOpened():
            print(f"[FILE][FAIL] Не удалось открыть файл: {self.video_source}", flush=True)
            return
        print(
            f"[FILE][OK] Файл открыт: {self.video_source} | "
            f"кадров={self.total_frames} fps={self.fps:.1f}",
            flush=True,
        )

        while True:
            try:
                ret, frame = self.cap.read()
                if not ret:
                    print(f"[FILE][OK] Конец файла {self.name}, обработано кадров={frame_id}", flush=True)
                    break

                frame_id += 1
                if frame_id % 3 != 0:
                    continue

                h, w = frame.shape[:2]
                pos_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
                self.current_frame_num = pos_frame

                # ── ШАГ 2: детекция ──────────────────────────────────────
                # roi_y=0: принимаем номера из всего кадра, угол видео неизвестен
                car_dets, plate_dets = self._detect(frame, h, w, roi_y=0)
                if frame_id % 90 == 0:
                    print(
                        f"[FILE][DETECT] frame={frame_id}/{self.total_frames} "
                        f"авто={len(car_dets)} номера={len(plate_dets)} "
                        f"треков={len(self.tracks)}",
                        flush=True,
                    )

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

                # ── ШАГ 3: постановка в очередь ─────────────────────────
                now = time.time()
                for tid, tr in list(self.tracks.items()):
                    if not tr.get('best_plate_box'):
                        continue
                    if now - tr.get('last_ocr', 0) > 1:
                        print(f"[FILE][QUEUE] Трек ID={tid} отправлен в очередь OCR", flush=True)
                        self._enqueue_track(frame, tr, tid, h, w, mark_saved=False)
                        tr['last_ocr'] = now

            except Exception as e:
                print(f"[FILE][FAIL] Ошибка в process_video: {e}", flush=True)
                import traceback
                traceback.print_exc()
                time.sleep(0.05)