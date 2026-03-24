import cv2
import threading
import queue
import time
from ultralytics import YOLO
from flask import Flask, render_template, Response, jsonify

app = Flask(__name__)
model = YOLO("model/best.pt")
video_path = "videos/Satpaeva38_3_1_20260120100000_20260120101500.dav"

cap = cv2.VideoCapture(video_path)
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS)

current_frame_num = 0
is_playing = False
seek_to = None
frame_queue = queue.Queue(maxsize=1)

lock = threading.Lock()

def process_video():
    global current_frame_num, seek_to
    
    while True:
        # Если нужна перемотка
        if seek_to is not None:
            with lock:
                cap.set(cv2.CAP_PROP_POS_FRAMES, seek_to)
                current_frame_num = seek_to
                seek_to = None
        
        # Если пауза, ждем
        if not is_playing:
            time.sleep(0.01)
            continue
        
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            current_frame_num = 0
            continue
        
        results = model(frame, verbose=False)
        detected = results[0].plot()
        
        current_frame_num = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
        
        try:
            frame_queue.get_nowait()
        except queue.Empty:
            pass
        
        frame_queue.put(detected)

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
    thread = threading.Thread(target=process_video, daemon=True)
    thread.start()
    print("🌐 Откройте http://localhost:5000")
    app.run(debug=False, port=5000)
