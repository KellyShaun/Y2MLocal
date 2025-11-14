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
# Multiple Invidious instances for redundancy
# ----------------------------
INVIDIOUS_INSTANCES = [
    "https://vid.puffyan.us",
    "https://inv.riverside.rocks", 
    "https://yt.artemislena.eu",
    "https://invidious.nerdvpn.de",
    "https://y.com.sb",
    "https://inv.nadeko.net",
    "https://invidious.flokinet.to",
    "https://inv.us.projectsegfau.lt"
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
    """Get video info from Invidious API - primary method"""
    for instance in INVIDIOUS_INSTANCES:
        try:
            api_url = f"{instance}/api/v1/videos/{video_id}"
            print(f"Trying Invidious instance: {instance}")
            response = requests.get(api_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                
                # Check if video is available
                if data.get('error'):
                    continue
                
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
                    'source': 'invidious'
                }
                print(f"✓ Successfully got info from Invidious: {result['title']}")
                return result
        except Exception as e:
            print(f"Invidious instance {instance} failed: {str(e)}")
            continue
    
    return None

def get_video_info_from_youtube_direct(video_id):
    """Fallback: Try direct YouTube extraction with minimal settings"""
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'ignoreerrors': True,
            'no_check_certificate': True,
            'extract_flat': False,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            
            filename = sanitize_filename(f"{info.get('title', 'unknown')}.mp3")
            file_path = os.path.join(DOWNLOAD_FOLDER, filename)
            already_downloaded = os.path.exists(file_path)
            
            return {
                'title': info.get('title', 'Unknown Title'),
                'uploader': info.get('uploader', 'Unknown'),
                'duration': time.strftime('%H:%M:%S', time.gmtime(info.get('duration', 0))),
                'view_count': info.get('view_count', 0),
                'thumbnail': info.get('thumbnail'),
                'file_path': file_path,
                'already_downloaded': already_downloaded,
                'video_id': video_id,
                'source': 'youtube_direct'
            }
    except Exception as e:
        print(f"YouTube direct extraction failed: {str(e)}")
        return None

def get_basic_video_info(video_id):
    """Final fallback: Get minimal info using public methods"""
    try:
        # Try to get basic info from oEmbed
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        response = requests.get(oembed_url, timeout=5)
        
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
    except:
        pass
    
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

def extract_audio_info(url):
    """Main function to extract video info with multiple fallbacks"""
    video_id = extract_video_id(url)
    if not video_id:
        raise Exception("Could not extract video ID from URL")
    
    print(f"Extracting info for video: {video_id}")
    
    # Method 1: Try Invidious first
    info = get_video_info_from_invidious(video_id)
    if info:
        return info
    
    # Method 2: Try direct YouTube extraction
    info = get_video_info_from_youtube_direct(video_id)
    if info:
        return info
    
    # Method 3: Get basic info as last resort
    info = get_basic_video_info(video_id)
    return info

def download_to_mp3(url, download_id):
    """Main download function"""
    try:
        video_id = extract_video_id(url)
        if not video_id:
            raise Exception("Could not extract video ID from URL")
        
        # Get video info
        video_info = extract_audio_info(url)
        
        # Check if already downloaded
        if video_info['already_downloaded']:
            downloads_progress[download_id]['file'] = video_info['file_path']
            downloads_progress[download_id]['finished'] = True
            downloads_progress[download_id]['progress'] = 100
            return
        
        # Download using yt-dlp with minimal settings
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'progress_hooks': [create_progress_hook(download_id)],
            'ignoreerrors': True,
            'no_check_certificate': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # Update progress
        downloads_progress[download_id]['file'] = video_info['file_path'].replace('.mp3', '').replace('.m4a', '') + '.mp3'
        downloads_progress[download_id]['finished'] = True
        downloads_progress[download_id]['progress'] = 100
        
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
        video_info = extract_audio_info(url)
        
        # If we only have basic info, note that download might not work
        if video_info['source'] in ['oembed', 'fallback']:
            video_info['limited_info'] = True
            video_info['warning'] = 'Limited information available. Download may not work for this video.'
        else:
            video_info['limited_info'] = False
            
        return jsonify({'success': True, **video_info})
        
    except Exception as e:
        error_msg = str(e)
        print(f"Error getting video info: {error_msg}")
        return jsonify({
            'success': False, 
            'error': 'Could not fetch video info. The video may be private, unavailable, or restricted in your region.'
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
    print("📡 Using multiple methods for reliable access")
    print(f"🔊 Download folder: {DOWNLOAD_FOLDER}")
    
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
