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
    
    # Remove playlist parameters and extract only the video ID
    url = url.split('&')[0]  # Remove everything after &
    
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

def try_y2mate_service(video_id, download_id):
    """Try y2mate service for download"""
    try:
        print(f"🌐 Trying y2mate service for: {video_id}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': 'https://www.y2mate.com',
            'Referer': 'https://www.y2mate.com/',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        
        # Step 1: Analyze the video
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
                video_title = analyze_data.get('title', f'video_{video_id}')
                vid = analyze_data.get('vid')
                
                print(f"✅ y2mate analysis successful: {video_title}")
                
                # Step 2: Get download links
                convert_data = {
                    'vid': vid,
                    'k': 'mp3'
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
                            print(f"📥 Download URL obtained, starting download...")
                            
                            # Download the file
                            filename = sanitize_filename(f"{video_title}.mp3")
                            file_path = os.path.join(DOWNLOAD_FOLDER, filename)
                            
                            # Update progress
                            downloads_progress[download_id]['progress'] = 50
                            
                            audio_response = requests.get(download_url, stream=True, timeout=120)
                            if audio_response.status_code == 200:
                                total_size = int(audio_response.headers.get('content-length', 0))
                                downloaded_size = 0
                                
                                with open(file_path, 'wb') as f:
                                    for chunk in audio_response.iter_content(chunk_size=8192):
                                        if chunk:
                                            f.write(chunk)
                                            downloaded_size += len(chunk)
                                            if total_size > 0:
                                                progress = 50 + (downloaded_size / total_size) * 50
                                                downloads_progress[download_id]['progress'] = progress
                                
                                downloads_progress[download_id]['file'] = file_path
                                downloads_progress[download_id]['finished'] = True
                                downloads_progress[download_id]['progress'] = 100
                                print(f"✅ y2mate download successful: {filename}")
                                return True
                            else:
                                print(f"❌ Failed to download from y2mate: {audio_response.status_code}")
        else:
            print(f"❌ y2mate analysis failed: {analyze_response.status_code}")
            
    except Exception as e:
        print(f"❌ y2mate service failed: {e}")
    
    return False

def try_onlinevideoconverter(video_id, download_id):
    """Try onlinevideoconverter service"""
    try:
        print(f"🌐 Trying onlinevideoconverter for: {video_id}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*',
        }
        
        payload = {
            'url': f'https://www.youtube.com/watch?v={video_id}',
            'format': 'mp3'
        }
        
        response = requests.post(
            'https://api.onlinevideoconverter.pro/api/convert',
            json=payload,
            headers=headers,
            timeout=60
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                download_url = data.get('url')
                if download_url:
                    print(f"📥 Onlinevideoconverter URL obtained")
                    
                    filename = sanitize_filename(f"video_{video_id}.mp3")
                    file_path = os.path.join(DOWNLOAD_FOLDER, filename)
                    
                    downloads_progress[download_id]['progress'] = 70
                    
                    audio_response = requests.get(download_url, stream=True, timeout=120)
                    if audio_response.status_code == 200:
                        with open(file_path, 'wb') as f:
                            for chunk in audio_response.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                        
                        downloads_progress[download_id]['file'] = file_path
                        downloads_progress[download_id]['finished'] = True
                        downloads_progress[download_id]['progress'] = 100
                        print(f"✅ Onlinevideoconverter download successful")
                        return True
                        
    except Exception as e:
        print(f"❌ Onlinevideoconverter failed: {e}")
    
    return False

def try_savemp3_service(video_id, download_id):
    """Try savemp3 service as fallback"""
    try:
        print(f"🌐 Trying savemp3 service for: {video_id}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        
        # Use savemp3 API
        response = requests.get(
            f'https://api.savemp3.com/api/convert',
            params={'url': f'https://www.youtube.com/watch?v={video_id}'},
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                download_url = data.get('url')
                if download_url:
                    filename = sanitize_filename(f"video_{video_id}.mp3")
                    file_path = os.path.join(DOWNLOAD_FOLDER, filename)
                    
                    audio_response = requests.get(download_url, timeout=120)
                    if audio_response.status_code == 200:
                        with open(file_path, 'wb') as f:
                            f.write(audio_response.content)
                        
                        downloads_progress[download_id]['file'] = file_path
                        downloads_progress[download_id]['finished'] = True
                        downloads_progress[download_id]['progress'] = 100
                        print(f"✅ Savemp3 download successful")
                        return True
                        
    except Exception as e:
        print(f"❌ Savemp3 service failed: {e}")
    
    return False

def download_with_external_services(video_id, download_id):
    """Use external services to download the video"""
    services = [
        ("y2mate", try_y2mate_service),
        ("onlinevideoconverter", try_onlinevideoconverter),
        ("savemp3", try_savemp3_service),
    ]
    
    for service_name, service_func in services:
        print(f"🔄 Trying {service_name}...")
        downloads_progress[download_id]['progress'] = 10
        downloads_progress[download_id]['status'] = f'Trying {service_name}...'
        
        if service_func(video_id, download_id):
            print(f"✅ {service_name} succeeded!")
            return True
        else:
            print(f"❌ {service_name} failed")
            downloads_progress[download_id]['progress'] = 0
    
    return False

def download_to_mp3(url, download_id):
    """Main download function using external services"""
    try:
        video_id = extract_video_id(url)
        if not video_id:
            raise Exception("Could not extract video ID from URL")
        
        print(f"🎬 Starting download process for video: {video_id}")
        
        # Check if already downloaded
        for f in os.listdir(DOWNLOAD_FOLDER):
            if f.endswith('.mp3') and video_id in f:
                downloads_progress[download_id]['file'] = os.path.join(DOWNLOAD_FOLDER, f)
                downloads_progress[download_id]['finished'] = True
                downloads_progress[download_id]['progress'] = 100
                print(f"✅ File already exists: {f}")
                return
        
        # Try external services
        if download_with_external_services(video_id, download_id):
            return
        else:
            raise Exception("All external services failed. YouTube may be blocking all download services from this server.")
        
    except Exception as e:
        downloads_progress[download_id]['error'] = str(e)
        downloads_progress[download_id]['finished'] = True
        print(f"💥 Download failed: {e}")

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
        video_info['warning'] = 'Using external download services (may be slower)'
        
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
        downloads_progress[download_id] = {
            'progress': 0, 
            'finished': False, 
            'file': None,
            'status': 'Starting download...'
        }
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
    print("🌐 Using external download services")
    print("💡 Note: Downloads use third-party services since YouTube blocks direct downloads")
    print(f"🔊 Download folder: {DOWNLOAD_FOLDER}")
    
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
