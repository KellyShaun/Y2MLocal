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
# External download services as fallback
# ----------------------------
EXTERNAL_SERVICES = [
    {
        'name': 'y2mate',
        'api_url': 'https://www.y2mate.com/mates/analyzeV2/ajax',
        'download_url': 'https://www.y2mate.com/mates/convertV2/index'
    },
    {
        'name': 'onlinevideoconverter',
        'api_url': 'https://onlinevideoconverter.pro/api/convert'
    }
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

def get_basic_video_info(video_id):
    """Get basic video info using public methods"""
    try:
        # Try to get basic info from oEmbed
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        response = requests.get(oembed_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            filename = sanitize_filename(f"{data.get('title', 'unknown')}.mp3")
            file_path = os.path.join(DOWNLOAD_FOLDER, filename)
            already_downloaded = os.path.exists(file_path)
            
            return {
                'title': data.get('title', 'Unknown Title'),
                'uploader': data.get('author_name', 'Unknown'),
                'duration': 'Unknown',
                'view_count': 0,
                'thumbnail': f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
                'file_path': file_path,
                'already_downloaded': already_downloaded,
                'video_id': video_id,
                'source': 'oembed'
            }
    except Exception as e:
        print(f"oEmbed failed: {e}")
    
    # Absolute fallback - just the video ID
    filename = sanitize_filename(f"video_{video_id}.mp3")
    file_path = os.path.join(DOWNLOAD_FOLDER, filename)
    already_downloaded = os.path.exists(file_path)
    
    return {
        'title': f"Video {video_id}",
        'uploader': 'Unknown',
        'duration': 'Unknown',
        'view_count': 0,
        'thumbnail': f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
        'file_path': file_path,
        'already_downloaded': already_downloaded,
        'video_id': video_id,
        'source': 'fallback'
    }

def try_external_download_service(video_id, download_id):
    """Try to download using external services"""
    try:
        # Method 1: Try y2mate-like service
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': 'https://www.y2mate.com',
            'Referer': 'https://www.y2mate.com/'
        }
        
        # Analyze the video
        analyze_data = {
            'k_query': f'https://www.youtube.com/watch?v={video_id}',
            'k_page': 'home',
            'hl': 'en',
            'q_auto': 0
        }
        
        analyze_response = requests.post(
            'https://www.y2mate.com/mates/analyzeV2/ajax',
            data=analyze_data,
            headers=headers,
            timeout=30
        )
        
        if analyze_response.status_code == 200:
            analyze_data = analyze_response.json()
            if analyze_data.get('status') == 'success':
                # Get the download link
                video_title = analyze_data.get('title', f'video_{video_id}')
                vid = analyze_data.get('vid')
                
                convert_data = {
                    'vid': vid,
                    'k': f'https://www.youtube.com/watch?v={video_id}'
                }
                
                convert_response = requests.post(
                    'https://www.y2mate.com/mates/convertV2/index',
                    data=convert_data,
                    headers=headers,
                    timeout=30
                )
                
                if convert_response.status_code == 200:
                    convert_data = convert_response.json()
                    if convert_data.get('status') == 'success':
                        download_url = convert_data.get('dlink')
                        if download_url:
                            # Download the file
                            filename = sanitize_filename(f"{video_title}.mp3")
                            file_path = os.path.join(DOWNLOAD_FOLDER, filename)
                            
                            audio_response = requests.get(download_url, stream=True, timeout=60)
                            if audio_response.status_code == 200:
                                with open(file_path, 'wb') as f:
                                    for chunk in audio_response.iter_content(chunk_size=8192):
                                        if chunk:
                                            f.write(chunk)
                                
                                downloads_progress[download_id]['file'] = file_path
                                downloads_progress[download_id]['finished'] = True
                                downloads_progress[download_id]['progress'] = 100
                                return True
    except Exception as e:
        print(f"External service download failed: {e}")
    
    return False

def download_with_fallback(url, download_id):
    """Try multiple download methods"""
    video_id = extract_video_id(url)
    if not video_id:
        raise Exception("Could not extract video ID from URL")
    
    # Method 1: Try external services first
    print("Trying external download services...")
    if try_external_download_service(video_id, download_id):
        return
    
    # Method 2: Try yt-dlp with aggressive settings as last resort
    print("Trying yt-dlp with aggressive settings...")
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'no_check_certificate': True,
            'progress_hooks': [create_progress_hook(download_id)],
            'extract_flat': False,
            'socket_timeout': 30,
            'retries': 10,
            'fragment_retries': 10,
            'skip_unavailable_fragments': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Accept-Encoding': 'gzip,deflate',
                'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
                'Keep-Alive': '300',
                'Connection': 'keep-alive',
                'Referer': 'https://www.youtube.com/',
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # Find the downloaded file and convert to MP3 if needed
            downloaded_files = [f for f in os.listdir(DOWNLOAD_FOLDER) 
                              if video_id in f and f.endswith(('.m4a', '.webm', '.opus'))]
            
            if downloaded_files:
                original_file = os.path.join(DOWNLOAD_FOLDER, downloaded_files[0])
                mp3_file = original_file.rsplit('.', 1)[0] + '.mp3'
                
                # Convert to MP3
                ffmpeg_path = detect_ffmpeg_path()
                result = subprocess.run([
                    ffmpeg_path, '-y', '-i', original_file, 
                    '-vn', '-acodec', 'libmp3lame', 
                    '-ab', '192k', '-ar', '44100', 
                    mp3_file
                ], capture_output=True, text=True)
                
                if result.returncode == 0 and os.path.exists(mp3_file):
                    # Remove original file
                    if os.path.exists(original_file):
                        os.remove(original_file)
                    
                    downloads_progress[download_id]['file'] = mp3_file
                    downloads_progress[download_id]['finished'] = True
                    downloads_progress[download_id]['progress'] = 100
                    return
        
        # If we get here, yt-dlp failed
        raise Exception("All download methods failed")
        
    except Exception as e:
        print(f"yt-dlp download failed: {e}")
        raise Exception(f"Download failed: {str(e)}")

def download_to_mp3(url, download_id):
    """Main download function"""
    try:
        video_id = extract_video_id(url)
        if not video_id:
            raise Exception("Could not extract video ID from URL")
        
        # Check if already downloaded
        for f in os.listdir(DOWNLOAD_FOLDER):
            if f.endswith('.mp3') and video_id in f:
                downloads_progress[download_id]['file'] = os.path.join(DOWNLOAD_FOLDER, f)
                downloads_progress[download_id]['finished'] = True
                downloads_progress[download_id]['progress'] = 100
                return
        
        # Try to download
        download_with_fallback(url, download_id)
        
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
        
        video_info = get_basic_video_info(video_id)
        video_info['limited_info'] = True
        video_info['warning'] = 'Download may take longer as we use external services'
        
        return jsonify({'success': True, **video_info})
        
    except Exception as e:
        error_msg = str(e)
        print(f"Error getting video info: {error_msg}")
        return jsonify({
            'success': False, 
            'error': 'Could not fetch video info. Please check the URL and try again.'
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
        if f.endswith(('.m4a', '.webm', '.opus', '.part')):
            try:
                os.remove(os.path.join(temp_dir, f))
            except:
                pass
    
    print("🚀 YouTube MP3 Downloader started")
    print("📡 Using external services for reliable downloads")
    print(f"🔊 Download folder: {DOWNLOAD_FOLDER}")
    
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
