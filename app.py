from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import os
import threading
import time
import logging
import json
import platform
from flask import send_from_directory

# =========================
# Environment & Setup
# =========================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['DOWNLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'downloads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(app.config['DOWNLOAD_FOLDER'], exist_ok=True)

print("✅ YouTube MP3 Downloader starting...")
print(f"📂 Download folder: {app.config['DOWNLOAD_FOLDER']}")

# =========================
# Import or Fallback Downloader
# =========================

try:
    from utils.youtube_downloader import YouTubeDownloader
    print("✓ YouTubeDownloader imported successfully")
except ImportError as e:
    print(f"⚠️ YouTubeDownloader import failed: {e}")
    class YouTubeDownloader:
        def __init__(self, folder):
            self.download_folder = folder
        def download_audio(self, url, progress_hook=None):
            return {'success': False, 'error': 'Downloader not available'}
        def get_video_info(self, url):
            return {'success': False, 'error': 'Downloader not available'}

# =========================
# Download Tracking & History
# =========================

download_progress = {}
HISTORY_FILE = os.path.join(BASE_DIR, 'download_history.json')

def load_download_history():
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Error loading history: {e}")
    return []

def save_download_history(history):
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Error saving history: {e}")

download_history = load_download_history()
print(f"🧾 Loaded {len(download_history)} previous downloads")

# =========================
# Utility Functions
# =========================

def is_render_env():
    """Detect if running on Render"""
    return "RENDER" in os.environ or os.path.exists("/opt/render/project/src")

def get_ffmpeg_path():
    """Get correct FFmpeg path depending on OS/environment"""
    if is_render_env():
        return "/usr/bin/ffmpeg"
    elif platform.system().lower().startswith("win"):
        return r"C:\ffmpeg\bin"
    else:
        return "/usr/bin/ffmpeg"

def get_cookie_path():
    """Optional: Cookie path if provided"""
    cookie_file = os.path.join(BASE_DIR, "cookies.txt")
    return cookie_file if os.path.exists(cookie_file) else None

# =========================
# Download Thread
# =========================

class DownloadThread(threading.Thread):
    def __init__(self, url, download_id):
        threading.Thread.__init__(self)
        self.url = url
        self.download_id = download_id

        # Pass dynamic ffmpeg/cookie settings to downloader
        self.downloader = YouTubeDownloader(
            app.config['DOWNLOAD_FOLDER'],
            ffmpeg_path=get_ffmpeg_path(),
            cookie_path=get_cookie_path()
        )

    def run(self):
        try:
            download_progress[self.download_id] = {
                'status': 'downloading',
                'progress': 0,
                'filename': None,
                'error': None
            }

            print(f"🎬 Starting download for: {self.url}")
            result = self.downloader.download_audio(self.url, self.progress_hook)

            if result.get('success'):
                filename = result['filename']
                print(f"✅ Download complete: {filename}")
                download_progress[self.download_id] = {
                    'status': 'completed',
                    'progress': 100,
                    'filename': filename,
                    'title': result.get('title'),
                    'duration': result.get('duration'),
                    'error': None
                }
                download_history.append({
                    'filename': filename,
                    'title': result.get('title'),
                    'url': self.url,
                    'timestamp': time.time(),
                    'duration': result.get('duration'),
                    'file_size': self.get_file_size(filename)
                })
                save_download_history(download_history)

            else:
                err = result.get('error', 'Unknown error')
                print(f"❌ Download failed: {err}")
                download_progress[self.download_id] = {
                    'status': 'error',
                    'progress': 0,
                    'filename': None,
                    'error': err
                }

        except Exception as e:
            logger.error(f"Thread error: {e}")
            download_progress[self.download_id] = {
                'status': 'error',
                'progress': 0,
                'filename': None,
                'error': str(e)
            }

    def progress_hook(self, d):
        if d['status'] == 'downloading' and '_percent_str' in d:
            try:
                progress = float(d['_percent_str'].strip().replace('%', ''))
                download_progress[self.download_id]['progress'] = progress
            except ValueError:
                pass
        elif d['status'] == 'finished':
            download_progress[self.download_id]['progress'] = 100
            print("🔄 Converting to MP3...")

    def get_file_size(self, filename):
        try:
            filepath = os.path.join(app.config['DOWNLOAD_FOLDER'], filename)
            return os.path.getsize(filepath)
        except:
            return 0

# =========================
# (Keep all your routes exactly the same)
# =========================
# — No change needed below this line —
# =========================

# ... paste all your existing routes here (from index() to get_stats()) ...
@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')


app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')  # must be inside 'templates/'


if __name__ == '__main__':
    existing_downloads = []
    try:
        existing_downloads = os.listdir(app.config['DOWNLOAD_FOLDER'])
    except Exception:
        pass

    print(f"Found {len(existing_downloads)} existing MP3 files.")
    app.run(host='0.0.0.0', port=5000, debug=True)





