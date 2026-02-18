import cv2
import threading
from ultralytics import YOLO
from flask import Flask, render_template, Response
import numpy as np

app = Flask(__name__)

# Глобальные переменные
current_frame = None
frame_lock = threading.Lock()
video_path = "videos/Satpaeva38_3_1_20260120100000_20260120101500.dav"
model = YOLO("model/best.pt")

def process_video():
    """Обработка видео в отдельном потоке"""
    global current_frame
    
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        print("❌ Не удалось открыть видео")
        return
    
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    
    frame_count = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            print("✅ Видео обработано полностью!")
            break
        
        # Обнаружение номеров на кадре
        results = model(frame, imgsz=640, verbose=False)
        annotated_frame = results[0].plot()
        
        frame_count += 1
        
        # Добавляем информацию
        info_text = f"Кадр: {frame_count}/{total_frames} | FPS: {fps:.1f}"
        cv2.putText(annotated_frame, info_text, (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Сохраняем текущий кадр
        with frame_lock:
            current_frame = annotated_frame
        
        if frame_count % 10 == 0:
            print(f"Обработано {frame_count}/{total_frames} кадров")
    
    cap.release()

def generate_frames():
    """Генератор для MJPEG потока"""
    global current_frame
    
    while True:
        with frame_lock:
            if current_frame is None:
                continue
            
            # Кодируем кадр в JPEG
            ret, buffer = cv2.imencode('.jpg', current_frame)
            frame_bytes = buffer.tobytes()
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n'
               b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n\r\n' 
               + frame_bytes + b'\r\n')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    # Запускаем обработку видео в отдельном потоке
    video_thread = threading.Thread(target=process_video, daemon=True)
    video_thread.start()
    
    print("🚀 Откройте браузер: http://localhost:5000")
    app.run(debug=False, port=5000, host='0.0.0.0')
