import os
import platform
import tempfile
import subprocess
import uuid
import threading
import time
import random
import requests
from flask import Flask, request, send_file, jsonify, render_template
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# ----------------------------
# Invidious API configuration (BYPASSES YOUTUBE RESTRICTIONS)
# ----------------------------
INVIDIOUS_INSTANCES = [
    "https://vid.puffyan.us",
    "https://inv.riverside.rocks", 
    "https://yt.artemislena.eu",
    "https://invidious.nerdvpn.de",
    "https://y.com.sb",
    "https://inv.nadeko.net"
]

# ----------------------------
# In-memory progress tracking
# ----------------------------
downloads_progress = {}

# ----------------------------
# Utility functions
# ----------------------------
def detect_ffmpeg_path():
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

def extract_video_id(url):
    """Extract video ID from various YouTube URL formats"""
    import re
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([^&?/]+)',
        r'youtube\.com/watch\?.*v=([^&]+)',
        r'youtu\.be/([^?]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_video_info_from_invidious(video_id):
    """Get video info from Invidious API - much more reliable"""
    for instance in INVIDIOUS_INSTANCES:
        try:
            api_url = f"{instance}/api/v1/videos/{video_id}"
            print(f"Trying Invidious instance: {instance}")
            response = requests.get(api_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                
                # Get the best available audio stream
                audio_streams = [fmt for fmt in data.get('adaptiveFormats', []) 
                               if 'audio' in fmt.get('type', '')]
                
                if audio_streams:
                    best_audio = max(audio_streams, key=lambda x: x.get('bitrate', 0))
                    audio_url = best_audio.get('url')
                else:
                    # Fallback to default format
                    audio_url = None
                
                filename = sanitize_filename(f"{data.get('title', 'unknown')}.mp3")
                file_path = os.path.join(DOWNLOAD_FOLDER, filename)
                already_downloaded = os.path.exists(file_path)
                
                result = {
                    'title': data.get('title', 'Unknown Title'),
                    'uploader': data.get('author', 'Unknown'),
                    'duration': time.strftime('%H:%M:%S', time.gmtime(data.get('lengthSeconds', 0))),
                    'view_count': data.get('viewCount', 0),
                    'thumbnail': data.get('videoThumbnails', [{}])[4].get('url') if data.get('videoThumbnails') else None,
                    'file_path': file_path,
                    'already_downloaded': already_downloaded,
                    'video_id': video_id,
                    'audio_url': audio_url,
                    'source': 'invidious'
                }
                print(f"✓ Successfully got info from Invidious: {result['title']}")
                return result
        except Exception as e:
            print(f"Invidious instance {instance} failed: {str(e)}")
            continue
    
    raise Exception("All Invidious instances failed")

def download_audio_from_invidious(video_info, download_id):
    """Download audio using Invidious streams"""
    try:
        if video_info.get('audio_url'):
            # Download directly from Invidious audio stream
            audio_url = video_info['audio_url']
            temp_file = os.path.join(tempfile.gettempdir(), f"{video_info['video_id']}.audio")
            
            # Download with progress
            response = requests.get(audio_url, stream=True)
            total_size = int(response.headers.get('content-length', 0))
            
            with open(temp_file, 'wb') as f:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            downloads_progress[download_id]['progress'] = progress
            
            # Convert to MP3
            final_mp3 = video_info['file_path']
            ffmpeg_path = detect_ffmpeg_path()
            result = subprocess.run([
                ffmpeg_path, '-y', '-i', temp_file, 
                '-vn', '-acodec', 'libmp3lame', 
                '-ab', '192k', '-ar', '44100', 
                final_mp3
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                raise Exception(f"FFmpeg conversion failed: {result.stderr}")
            
            # Clean up
            if os.path.exists(temp_file):
                os.remove(temp_file)
                
        else:
            # Fallback to yt-dlp with minimal options
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
                'progress_hooks': [create_progress_hook(download_id)],
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([f"https://www.youtube.com/watch?v={video_info['video_id']}"])
        
        downloads_progress[download_id]['file'] = video_info['file_path']
        downloads_progress[download_id]['finished'] = True
        downloads_progress[download_id]['progress'] = 100
        
    except Exception as e:
        downloads_progress[download_id]['error'] = str(e)
        downloads_progress[download_id]['finished'] = True

def download_to_mp3(url, download_id):
    """Main download function using Invidious"""
    try:
        video_id = extract_video_id(url)
        if not video_id:
            raise Exception("Could not extract video ID from URL")
        
        # Get video info from Invidious
        video_info = get_video_info_from_invidious(video_id)
        
        # Check if already downloaded
        if video_info['already_downloaded']:
            downloads_progress[download_id]['file'] = video_info['file_path']
            downloads_progress[download_id]['finished'] = True
            downloads_progress[download_id]['progress'] = 100
            return
        
        # Download the audio
        download_audio_from_invidious(video_info, download_id)
        
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
    
    # Basic YouTube URL validation
    if not any(domain in url for domain in ['youtube.com', 'youtu.be']):
        return jsonify({'success': False, 'error': 'Please provide a valid YouTube URL'})
    
    try:
        video_id = extract_video_id(url)
        if not video_id:
            return jsonify({'success': False, 'error': 'Invalid YouTube URL'})
        
        video_info = get_video_info_from_invidious(video_id)
        return jsonify({'success': True, **video_info})
        
    except Exception as e:
        error_msg = str(e)
        print(f"Error getting video info: {error_msg}")
        return jsonify({
            'success': False, 
            'error': 'Could not fetch video info. The video may be unavailable or restricted.'
        })

@app.route('/download-mp3', methods=['POST'])
def download_mp3():
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({'success': False, 'error': 'No URL provided'})

    try:
        video_id = extract_video_id(url)
        if not video_id:
            return jsonify({'success': False, 'error': 'Invalid YouTube URL'})

        # Quick check if already downloaded
        for f in os.listdir(DOWNLOAD_FOLDER):
            if f.endswith('.mp3') and video_id in f:
                return jsonify({
                    'success': False,
                    'error': 'This video has already been downloaded',
                    'existing_file': f
                })

        download_id = str(uuid.uuid4())
        downloads_progress[download_id] = {'progress': 0, 'finished': False, 'file': None}
        threading.Thread(target=download_to_mp3, args=(url, download_id), daemon=True).start()
        return jsonify({'success': True, 'download_id': download_id})
        
    except Exception as e:
        error_msg = str(e)
        return jsonify({'success': False, 'error': f'Download failed: {error_msg}'})

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
        if os.path.isfile(path) and f.endswith('.mp3'):
            size = os.path.getsize(path)
            modified = os.path.getmtime(path)
            files.append({
                'filename': f,
                'name': os.path.splitext(f)[0],
                'size': size,
                'modified': modified,
                'size_formatted': f"{size/1024/1024:.2f} MB",
                'modified_formatted': time.strftime('%Y-%m-%d %H:%M', time.localtime(modified)),
            })
    # Sort by modification time (newest first)
    files.sort(key=lambda x: x['modified'], reverse=True)
    return jsonify({'success': True, 'downloads': files})

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'timestamp': time.time()})

# ----------------------------
# Main
# ----------------------------
if __name__ == "__main__":
    # Clean up any temp files on startup
    temp_dir = tempfile.gettempdir()
    for f in os.listdir(temp_dir):
        if f.endswith(('.m4a', '.webm', '.opus', '.part', '.audio')):
            try:
                os.remove(os.path.join(temp_dir, f))
            except:
                pass
    
    print("🚀 YouTube MP3 Downloader started")
    print("📡 Using Invidious instances for reliable access")
    print(f"🔊 Download folder: {DOWNLOAD_FOLDER}")
    
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
