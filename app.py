import os
import platform
import tempfile
import subprocess
import uuid
import threading
import time
import random
from flask import Flask, request, send_file, jsonify, render_template
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

DOWNLOAD_FOLDER = "downloads"
COOKIES_FILE = "cookies.txt"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# ----------------------------
# Enhanced yt-dlp configuration with better cookie handling
# ----------------------------
def get_random_user_agent():
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0',
    ]
    return random.choice(user_agents)

def get_ydl_opts():
    base_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': False,
        'extract_flat': False,
        'ignoreerrors': True,
        'no_check_certificate': True,
        'prefer_ffmpeg': True,
        'geo_bypass': True,
        'geo_bypass_country': 'US',
        'http_headers': {
            'User-Agent': get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Accept-Encoding': 'gzip,deflate',
            'Referer': 'https://www.youtube.com/',
        },
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
                'player_skip': ['configs', 'webpage'],
            }
        },
        'no_part': True,
        'no_overwrites': True,
        'continue_dl': False,
        'retries': 10,
        'fragment_retries': 10,
        'skip_unavailable_fragments': True,
    }
    
    # Add cookies with verification
    if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100:
        base_opts['cookiefile'] = COOKIES_FILE
        print(f"✓ Using cookies from {COOKIES_FILE} (size: {os.path.getsize(COOKIES_FILE)} bytes)")
    else:
        print(f"✗ Cookies file not found or too small: {COOKIES_FILE}")
    
    return base_opts

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

# NEW: Simple direct extraction that works better
def extract_info_simple(url):
    """Simple extraction that works better for restricted videos"""
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'ignoreerrors': True,
        'no_check_certificate': True,
        'extract_flat': False,
    }
    
    # Try with cookies first
    if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100:
        ydl_opts['cookiefile'] = COOKIES_FILE
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

def extract_audio_info_with_fallback(url):
    """Simplified extraction with immediate fallback"""
    video_id = extract_video_id(url)
    if not video_id:
        raise Exception("Invalid YouTube URL - could not extract video ID")
    
    try:
        # Try simple extraction first (fastest)
        info = extract_info_simple(url)
        return _process_video_info(info)
    except Exception as e:
        print(f"Simple extraction failed: {e}")
        # Fallback to Invidious immediately
        return _extract_with_invidious(video_id)

def _extract_with_invidious(video_id):
    """Fallback to Invidious API - most reliable"""
    invidious_instances = [
        "https://vid.puffyan.us",
        "https://inv.riverside.rocks", 
        "https://yt.artemislena.eu",
        "https://invidious.nerdvpn.de"
    ]
    
    for instance in invidious_instances:
        try:
            import requests
            api_url = f"{instance}/api/v1/videos/{video_id}"
            print(f"Trying Invidious instance: {instance}")
            response = requests.get(api_url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                filename = sanitize_filename(f"{data.get('title', 'unknown')}.mp3")
                file_path = os.path.join(DOWNLOAD_FOLDER, filename)
                already_downloaded = os.path.exists(file_path)
                
                result = {
                    'title': data.get('title', 'Unknown Title'),
                    'ext': 'mp3',
                    'thumbnail': data.get('videoThumbnails', [{}])[4].get('url') if data.get('videoThumbnails') else None,  # Use higher quality thumbnail
                    'uploader': data.get('author', 'Unknown'),
                    'duration': time.strftime('%M:%S', time.gmtime(data.get('lengthSeconds', 0))),
                    'view_count': data.get('viewCount', 0),
                    'file_path': file_path,
                    'already_downloaded': already_downloaded,
                    'source': 'invidious'
                }
                print(f"✓ Successfully got info from Invidious: {result['title']}")
                return result
        except Exception as e:
            print(f"Invidious instance {instance} failed: {e}")
            continue
    
    raise Exception("All extraction methods failed")

def _process_video_info(info):
    """Process video info into standardized format"""
    filename = sanitize_filename(f"{info.get('title', 'unknown')}.mp3")
    file_path = os.path.join(DOWNLOAD_FOLDER, filename)
    already_downloaded = os.path.exists(file_path)
    
    return {
        'title': info.get('title', 'Unknown Title'),
        'ext': info.get('ext', 'm4a'),
        'thumbnail': info.get('thumbnail'),
        'uploader': info.get('uploader', 'Unknown'),
        'duration': time.strftime('%M:%S', time.gmtime(info.get('duration', 0))),
        'view_count': info.get('view_count', 0),
        'file_path': file_path,
        'already_downloaded': already_downloaded,
        'source': 'youtube'
    }

def download_to_mp3(url, download_id):
    try:
        # Simple download approach
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'ignoreerrors': True,
            'no_check_certificate': True,
            'outtmpl': os.path.join(tempfile.gettempdir(), '%(title)s.%(ext)s'),
            'progress_hooks': [create_progress_hook(download_id)],
            'retries': 5,
        }
        
        # Add cookies if available
        if os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100:
            ydl_opts['cookiefile'] = COOKIES_FILE
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # Find the downloaded file
        temp_dir = tempfile.gettempdir()
        temp_files = [f for f in os.listdir(temp_dir) if f.endswith(('.m4a', '.webm', '.opus'))]
        
        if not temp_files:
            raise Exception("No audio file found after download")
        
        temp_file = os.path.join(temp_dir, temp_files[0])
        final_filename = sanitize_filename(f"{os.path.splitext(temp_files[0])[0]}.mp3")
        final_mp3 = os.path.join(DOWNLOAD_FOLDER, final_filename)
        
        # Convert to MP3
        ffmpeg_path = detect_ffmpeg_path()
        result = subprocess.run([
            ffmpeg_path, '-y', '-i', temp_file, 
            '-vn', '-acodec', 'libmp3lame', 
            '-ab', '192k', '-ar', '44100', 
            final_mp3
        ], capture_output=True, text=True)
        
        if result.returncode != 0:
            raise Exception(f"FFmpeg conversion failed: {result.stderr}")
        
        # Clean up temp file
        if os.path.exists(temp_file):
            os.remove(temp_file)
        
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
    
    # Basic YouTube URL validation
    if not any(domain in url for domain in ['youtube.com', 'youtu.be']):
        return jsonify({'success': False, 'error': 'Please provide a valid YouTube URL'})
    
    try:
        info = extract_audio_info_with_fallback(url)
        return jsonify({'success': True, **info})
    except Exception as e:
        error_msg = str(e)
        print(f"Error extracting info: {error_msg}")
        return jsonify({
            'success': False, 
            'error': 'Could not fetch video info. The video may be restricted or unavailable.'
        })

@app.route('/download-mp3', methods=['POST'])
def download_mp3():
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({'success': False, 'error': 'No URL provided'})

    try:
        # Quick check if already downloaded
        video_id = extract_video_id(url)
        if video_id:
            # Check if any existing file contains this video ID
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

@app.route('/cookie-status')
def cookie_status():
    """Check if cookies are available and working"""
    has_cookies = os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 100
    status = "available" if has_cookies else "not found or invalid"
    cookie_size = os.path.getsize(COOKIES_FILE) if os.path.exists(COOKIES_FILE) else 0
    
    return jsonify({
        'success': True, 
        'cookies_available': has_cookies,
        'status': status,
        'cookie_size': cookie_size
    })

# Health check endpoint
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
        if f.endswith(('.m4a', '.webm', '.opus', '.part')):
            try:
                os.remove(os.path.join(temp_dir, f))
            except:
                pass
    
    # Check cookies on startup
    if os.path.exists(COOKIES_FILE):
        print(f"Cookies file found: {COOKIES_FILE} ({os.path.getsize(COOKIES_FILE)} bytes)")
    else:
        print(f"Cookies file not found: {COOKIES_FILE}")
    
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
