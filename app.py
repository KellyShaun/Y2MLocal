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

def clean_youtube_url(url):
    """Clean YouTube URL to remove playlist parameters and ensure it's a single video"""
    if 'youtube.com/watch' in url and '&' in url:
        # Extract only the video part, remove playlist parameters
        base_url = url.split('&')[0]
        return base_url
    return url

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

def download_with_cookies_simple(url, download_id, video_id):
    """Simplified download using yt-dlp with cookies - single video only"""
    try:
        cookies_path = 'cookies.txt'
        if not os.path.exists(cookies_path):
            print("❌ Cookies file not found")
            return False
        
        # Clean URL to ensure it's a single video, not a playlist
        clean_url = clean_youtube_url(url)
        print(f"🔧 Cleaned URL: {clean_url}")
            
        # Simple, focused yt-dlp options
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
            'cookiefile': cookies_path,
            'quiet': False,
            'no_warnings': False,
            'ignoreerrors': False,
            'no_check_certificate': True,
            'progress_hooks': [create_progress_hook(download_id)],
            'extract_flat': False,
            'socket_timeout': 30,
            'retries': 3,
            'fragment_retries': 3,
            'skip_unavailable_fragments': False,
            'noplaylist': True,  # CRITICAL: Don't download playlists
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'hls'],
                }
            },
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
        }
        
        print(f"🎯 Attempting single video download for: {video_id}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                # Extract info first to verify it works
                info = ydl.extract_info(clean_url, download=False)
                print(f"✅ Video info extracted: {info.get('title', 'Unknown')}")
                
                # Now download
                ydl.download([clean_url])
                print("✅ Download completed")
                
                # Find the downloaded MP3 file
                for f in os.listdir(DOWNLOAD_FOLDER):
                    if f.endswith('.mp3') and (video_id in f or info.get('title', '').replace(' ', '_') in f):
                        file_path = os.path.join(DOWNLOAD_FOLDER, f)
                        downloads_progress[download_id]['file'] = file_path
                        downloads_progress[download_id]['finished'] = True
                        downloads_progress[download_id]['progress'] = 100
                        print(f"✅ MP3 file ready: {f}")
                        return True
                        
            except Exception as e:
                print(f"❌ Download failed: {e}")
                return False
        
        return False
        
    except Exception as e:
        print(f"❌ Cookie-based download failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def try_simple_download(url, download_id, video_id):
    """Try simple download without cookies first"""
    try:
        clean_url = clean_youtube_url(url)
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
            'ignoreerrors': False,
            'progress_hooks': [create_progress_hook(download_id)],
            'noplaylist': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'extractor_args': {
                'youtube': {
                    'player_client': ['android'],
                }
            },
        }
        
        print(f"🔧 Trying simple download for: {video_id}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(clean_url, download=False)
                print(f"✅ Simple info extraction worked: {info.get('title', 'Unknown')}")
                
                ydl.download([clean_url])
                print("✅ Simple download completed")
                
                # Find the file
                for f in os.listdir(DOWNLOAD_FOLDER):
                    if f.endswith('.mp3') and (video_id in f or info.get('title', '').replace(' ', '_') in f):
                        file_path = os.path.join(DOWNLOAD_FOLDER, f)
                        downloads_progress[download_id]['file'] = file_path
                        downloads_progress[download_id]['finished'] = True
                        downloads_progress[download_id]['progress'] = 100
                        return True
                        
            except Exception as e:
                print(f"❌ Simple download failed: {e}")
                return False
        
        return False
        
    except Exception as e:
        print(f"❌ Simple download method failed: {e}")
        return False

def download_with_fallback(url, download_id):
    """Try multiple download methods with better error reporting"""
    video_id = extract_video_id(url)
    if not video_id:
        raise Exception("Could not extract video ID from URL")
    
    print(f"🎬 Starting download process for video: {video_id}")
    
    # Method 1: Try simple download first (no cookies)
    print("🔄 Trying simple download (no cookies)...")
    if try_simple_download(url, download_id, video_id):
        print("✅ Simple download succeeded!")
        return
    
    # Method 2: Try with cookies
    print("🔄 Trying download with cookies...")
    if download_with_cookies_simple(url, download_id, video_id):
        print("✅ Cookie download succeeded!")
        return
    
    # Method 3: Last resort - try external service
    print("🔄 Trying external service...")
    if try_external_download_service(video_id, download_id):
        print("✅ External service succeeded!")
        return
    
    raise Exception("All download methods failed. The video might be restricted or unavailable.")

def try_external_download_service(video_id, download_id):
    """Try external download service as last resort"""
    try:
        print(f"🌐 Trying external service for video: {video_id}")
        # This would be your external service implementation
        # For now, just return False since we want to focus on yt-dlp fixes
        return False
    except Exception as e:
        print(f"❌ External service failed: {e}")
        return False

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
                print(f"✅ File already exists: {f}")
                return
        
        # Try to download
        download_with_fallback(url, download_id)
        
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

@app.route('/cookies-status')
def cookies_status():
    """Check if cookies file exists and is valid"""
    cookies_path = 'cookies.txt'
    status = {
        'exists': os.path.exists(cookies_path),
        'size': 0,
        'has_youtube': False,
        'content_preview': ''
    }
    
    if status['exists']:
        try:
            with open(cookies_path, 'r') as f:
                content = f.read()
                status['size'] = len(content)
                status['has_youtube'] = 'youtube.com' in content or '.youtube.com' in content
                status['content_preview'] = content[:200] + '...' if len(content) > 200 else content
                
                # Check if it's in Netscape format
                lines = content.split('\n')
                if lines and ('# HTTP Cookie File' in lines[0] or '# Netscape HTTP Cookie File' in lines[0]):
                    status['format'] = 'netscape'
                else:
                    status['format'] = 'unknown'
                    
        except Exception as e:
            status['error'] = str(e)
    
    return jsonify(status)

@app.route('/cookies-help')
def cookies_help():
    """Provide instructions for setting up cookies"""
    help_info = {
        'instructions': [
            "1. Install the 'Get cookies.txt LOCALLY' extension in Chrome",
            "2. Go to YouTube.com and make sure you're logged in",
            "3. Click the extension and export cookies for youtube.com", 
            "4. Save the file as 'cookies.txt' in your app's root directory",
            "5. Restart your app",
            "6. Visit /cookies-status to verify cookies are working"
        ],
        'chrome_extension': 'https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc',
        'firefox_extension': 'https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/'
    }
    return jsonify(help_info)
    
@app.route('/info', methods=['POST'])
def info():
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({'success': False, 'error': 'No URL provided'})
    
    # Clean the URL to remove playlist parameters
    clean_url = clean_youtube_url(url)
    
    # Basic YouTube URL validation
    if not any(domain in clean_url for domain in ['youtube.com', 'youtu.be']):
        return jsonify({'success': False, 'error': 'Please provide a valid YouTube URL'})
    
    try:
        video_id = extract_video_id(clean_url)
        if not video_id:
            return jsonify({'success': False, 'error': 'Invalid YouTube URL'})
        
        video_info = get_basic_video_info(video_id)
        video_info['limited_info'] = True
        video_info['warning'] = 'Download may take longer due to YouTube restrictions'
        
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
        # Clean the URL first
        clean_url = clean_youtube_url(url)
        video_id = extract_video_id(clean_url)
        
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
        threading.Thread(target=download_to_mp3, args=(clean_url, download_id), daemon=True).start()
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
    
    # Check if cookies file exists
    if os.path.exists('cookies.txt'):
        print("✅ Cookies file found and will be used for downloads")
        # Verify cookies format
        try:
            with open('cookies.txt', 'r') as f:
                cookie_content = f.read()
                if 'youtube.com' in cookie_content:
                    print("✅ YouTube cookies detected in cookies file")
                else:
                    print("⚠️  Cookies file exists but may not contain YouTube cookies")
        except Exception as e:
            print(f"⚠️  Could not read cookies file: {e}")
    else:
        print("⚠️  No cookies.txt file found - downloads may be limited")
        print("💡 Visit /cookies-help for setup instructions")
    
    print("🚀 YouTube MP3 Downloader started")
    print("📡 Using optimized download methods")
    print(f"🔊 Download folder: {DOWNLOAD_FOLDER}")
    print("💡 Tip: Use single video URLs, not playlist URLs")
    
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
