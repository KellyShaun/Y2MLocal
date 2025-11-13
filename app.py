from flask import Flask, render_template, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
import os
import threading
import time
import json
import logging
import platform

# =========================
# Setup & Environment
# =========================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['DOWNLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'downloads')
os.makedirs(app.config['DOWNLOAD_FOLDER'], exist_ok=True)

HISTORY_FILE = os.path.join(BASE_DIR, 'download_history.json')

download_progress = {}

print("✅ YouTube MP3 Downloader starting...")
print(f"📂 Download folder: {app.config['DOWNLOAD_FOLDER']}")

# =========================
# Fallback Downloader
# =========================

try:
    from utils.youtube_downloader import YouTubeDownloader
    print("✓ YouTubeDownloader imported successfully")
except ImportError:
    print("⚠️ YouTubeDownloader import failed, using dummy downloader")

    class YouTubeDownloader:
        def __init__(self, folder, ffmpeg_path=None, cookie_path=None):
            self.download_folder = folder

        def download_audio(self, url, progress_hook=None):
            # Dummy download
            time.sleep(2)
            filename = "sample.mp3"
            if progress_hook:
                progress_hook({'status': 'finished'})
            return {'success': True, 'filename': filename, 'title': 'Sample Video', 'duration': '03:45'}

        def get_video_info(self, url):
            return {'success': True, 'title': 'Sample Video', 'thumbnail': '', 'uploader': 'Uploader', 'view_count': 1234, 'duration': '03:45'}

# =========================
# Helper functions
# =========================

def load_download_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_download_history(history):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

def get_ffmpeg_path():
    if platform.system().lower().startswith("win"):
        return r"C:\ffmpeg\bin\ffmpeg.exe"
    return "/usr/bin/ffmpeg"

download_history = load_download_history()

# =========================
# Routes
# =========================

@app.route('/')
def index():
    return render_template('index.html')  # Your main HTML

@app.route('/downloads', methods=['GET'])
def list_downloads():
    files = []
    for filename in os.listdir(app.config['DOWNLOAD_FOLDER']):
        if filename.endswith('.mp3'):
            filepath = os.path.join(app.config['DOWNLOAD_FOLDER'], filename)
            files.append({
                'filename': filename,
                'name': os.path.splitext(filename)[0],
                'size': os.path.getsize(filepath),
                'modified': os.path.getmtime(filepath),
                'size_formatted': None,
                'modified_formatted': None,
                'duration_formatted': None
            })
    return jsonify({'success': True, 'downloads': files})

@app.route('/info', methods=['POST'])
def video_info():
    data = request.get_json()
    url = data.get('url')
    downloader = YouTubeDownloader(app.config['DOWNLOAD_FOLDER'], ffmpeg_path=get_ffmpeg_path())
    info = downloader.get_video_info(url)
    return jsonify(info)

@app.route('/download', methods=['POST'])
def download_video():
    data = request.get_json()
    url = data.get('url')
    download_id = str(int(time.time() * 1000))
    thread = DownloadThread(url, download_id)
    thread.start()
    return jsonify({'success': True, 'download_id': download_id})

@app.route('/progress/<download_id>')
def progress(download_id):
    prog = download_progress.get(download_id)
    if not prog:
        return jsonify({'status': 'error', 'progress': 0, 'error': 'Download ID not found'})
    return jsonify(prog)

@app.route('/play-audio/<filename>')
def play_audio(filename):
    return send_from_directory(app.config['DOWNLOAD_FOLDER'], filename)

@app.route('/delete/<filename>', methods=['DELETE'])
def delete_file(filename):
    try:
        path = os.path.join(app.config['DOWNLOAD_FOLDER'], filename)
        if os.path.exists(path):
            os.remove(path)
            global download_history
            download_history = [d for d in download_history if d['filename'] != filename]
            save_download_history(download_history)
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'File not found'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# =========================
# Download Thread
# =========================

class DownloadThread(threading.Thread):
    def __init__(self, url, download_id):
        threading.Thread.__init__(self)
        self.url = url
        self.download_id = download_id
        self.downloader = YouTubeDownloader(app.config['DOWNLOAD_FOLDER'], ffmpeg_path=get_ffmpeg_path())

    def run(self):
        download_progress[self.download_id] = {'status': 'downloading', 'progress': 0, 'filename': None, 'error': None}
        result = self.downloader.download_audio(self.url, self.progress_hook)
        if result.get('success'):
            filename = result['filename']
            download_progress[self.download_id] = {'status': 'completed', 'progress': 100, 'filename': filename, 'title': result.get('title'), 'error': None}
            download_history.append({'filename': filename, 'title': result.get('title'), 'url': self.url, 'timestamp': time.time(), 'duration': result.get('duration')})
            save_download_history(download_history)
        else:
            download_progress[self.download_id] = {'status': 'error', 'progress': 0, 'filename': None, 'error': result.get('error', 'Unknown error')}

    def progress_hook(self, d):
        if d['status'] == 'downloading' and '_percent_str' in d:
            try:
                download_progress[self.download_id]['progress'] = float(d['_percent_str'].strip('%'))
            except:
                pass
        elif d['status'] == 'finished':
            download_progress[self.download_id]['progress'] = 100

# =========================
# Run Server
# =========================

if __name__ == '__main__':
    existing_downloads = [f for f in os.listdir(app.config['DOWNLOAD_FOLDER']) if f.endswith('.mp3')]
    print(f"Found {len(existing_downloads)} existing MP3 files.")
    app.run(host='0.0.0.0', port=5000, debug=True)
