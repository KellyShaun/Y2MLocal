import os
import platform
import tempfile
import subprocess
import uuid
import threading
import time
from flask import Flask, request, send_file, jsonify, render_template
import yt_dlp

app = Flask(__name__)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# ----------------------------
# In-memory progress tracking
# ----------------------------
downloads_progress = {}

# ----------------------------
# Utility functions
# ----------------------------
def detect_ffmpeg_path():
    system = platform.system().lower()
    if system.startswith("win"):
        return r"C:\ffmpeg\bin\ffmpeg.exe"
    elif os.path.exists("/usr/bin/ffmpeg"):
        return "/usr/bin/ffmpeg"
    elif os.path.exists("/usr/local/bin/ffmpeg"):
        return "/usr/local/bin/ffmpeg"
    else:
        return "ffmpeg"

def sanitize_filename(filename):
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '')
    filename = filename.replace("'", '').replace('"', '')
    if len(filename) > 100:
        name, ext = os.path.splitext(filename)
        filename = name[:100 - len(ext)] + ext
    return filename

def create_progress_hook(download_id):
    def hook(d):
        if d['status'] == 'downloading':
            percent_str = d.get('_percent_str', '0.0%').strip()
            try:
                downloads_progress[download_id]['progress'] = float(percent_str.strip('%'))
            except:
                downloads_progress[download_id]['progress'] = 0.0
        elif d['status'] == 'finished':
            downloads_progress[download_id]['progress'] = 100
            downloads_progress[download_id]['finished'] = True
        elif d['status'] == 'error':
            downloads_progress[download_id]['error'] = d.get('error', 'Unknown error')
            downloads_progress[download_id]['finished'] = True
    return hook

def extract_audio_info(url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'noplaylist': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        filename = sanitize_filename(f"{info.get('title', 'unknown')}.mp3")
        file_path = os.path.join(DOWNLOAD_FOLDER, filename)
        already_downloaded = os.path.exists(file_path)
        return {
            'title': info.get('title', 'unknown'),
            'ext': info.get('ext', 'm4a'),
            'thumbnail': info.get('thumbnail'),
            'uploader': info.get('uploader'),
            'duration': time.strftime('%M:%S', time.gmtime(info.get('duration', 0))),
            'view_count': info.get('view_count', 0),
            'file_path': file_path,
            'already_downloaded': already_downloaded
        }

def download_to_mp3(url, download_id):
    try:
        info = extract_audio_info(url)
        title = sanitize_filename(info['title'])
        tmp_audio = os.path.join(tempfile.gettempdir(), f"{title}.{info['ext']}")
        final_mp3 = os.path.join(DOWNLOAD_FOLDER, f"{title}.mp3")

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': tmp_audio,
            'quiet': True,
            'noplaylist': True,
            'progress_hooks': [create_progress_hook(download_id)]
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        ffmpeg_path = detect_ffmpeg_path()
        subprocess.run([ffmpeg_path, '-y', '-i', tmp_audio, '-vn', '-ab', '192k', '-ar', '44100', final_mp3])

        downloads_progress[download_id]['file'] = final_mp3
        downloads_progress[download_id]['finished'] = True
    except Exception as e:
        downloads_progress[download_id]['error'] = str(e)
        downloads_progress[download_id]['finished'] = True

# ----------------------------
# Flask routes
# ----------------------------
@app.route('/')
def home():
    return render_template("index.html")

@app.route('/info', methods=['POST'])
def info():
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({'success': False, 'error': 'No URL provided'})
    try:
        info = extract_audio_info(url)
        return jsonify({'success': True, **info})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/download-mp3', methods=['POST'])
def download_mp3():
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({'success': False, 'error': 'No URL provided'})

    info = extract_audio_info(url)
    if info['already_downloaded']:
        return jsonify({
            'success': False,
            'error': 'This video has already been downloaded',
            'existing_file': os.path.basename(info['file_path'])
        })

    download_id = str(uuid.uuid4())
    downloads_progress[download_id] = {'progress': 0, 'finished': False, 'file': None}
    threading.Thread(target=download_to_mp3, args=(url, download_id), daemon=True).start()
    return jsonify({'success': True, 'download_id': download_id})

@app.route('/progress/<download_id>')
def progress_route(download_id):
    info = downloads_progress.get(download_id)
    if not info:
        return jsonify({'status': 'error', 'error': 'Invalid download ID'})
    return jsonify(info)

@app.route('/play-audio/<filename>')
def play_audio(filename):
    path = os.path.join(DOWNLOAD_FOLDER, filename)
    if not os.path.exists(path):
        return jsonify({'success': False, 'error': 'File not found'}), 404
    return send_file(path, as_attachment=False)

@app.route('/get-file/<filename>')
def get_file(filename):
    path = os.path.join(DOWNLOAD_FOLDER, filename)
    if not os.path.exists(path):
        return jsonify({'success': False, 'error': 'File not found'}), 404
    return send_file(path, as_attachment=True)

@app.route('/delete/<filename>', methods=['DELETE'])
def delete_file(filename):
    path = os.path.join(DOWNLOAD_FOLDER, filename)
    if os.path.exists(path):
        os.remove(path)
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'File not found'})

@app.route('/downloads')
@app.route('/downloads-list')
def downloads_list():
    files = []
    for f in os.listdir(DOWNLOAD_FOLDER):
        path = os.path.join(DOWNLOAD_FOLDER, f)
        if os.path.isfile(path):
            size = os.path.getsize(path)
            modified = os.path.getmtime(path)
            files.append({
                'filename': f,
                'name': f,
                'size': size,
                'modified': modified,
                'size_formatted': f"{size/1024/1024:.2f} MB",
                'modified_formatted': time.strftime('%Y-%m-%d', time.localtime(modified)),
                'duration_formatted': 'Unknown'
            })
    return jsonify({'success': True, 'downloads': files})

# ----------------------------
# Main
# ----------------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
