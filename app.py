import os
import time
import requests
import re
import json
from flask import Flask, request, send_file, jsonify, render_template
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

def sanitize_filename(filename):
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '')
    filename = filename.replace("'", '').replace('"', '')
    if len(filename) > 100:
        name, ext = os.path.splitext(filename)
        filename = name[:100 - len(ext)] + ext
    return filename

def extract_video_id(url):
    """Extract video ID from YouTube URL"""
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

def get_video_info(video_id):
    """Get basic video info from YouTube"""
    try:
        # Try oEmbed first
        oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        response = requests.get(oembed_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return {
                'title': data.get('title', 'Unknown Title'),
                'uploader': data.get('author_name', 'Unknown'),
                'thumbnail': f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
                'success': True
            }
    except:
        pass
    
    return {
        'title': f'Video {video_id}',
        'uploader': 'Unknown',
        'thumbnail': f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
        'success': True
    }

@app.route('/')
def home():
    return render_template("index.html")

@app.route('/video-info', methods=['POST'])
def video_info():
    """Get video information"""
    data = request.json
    url = data.get('url', '')
    
    if not url:
        return jsonify({'success': False, 'error': 'No URL provided'})
    
    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({'success': False, 'error': 'Invalid YouTube URL'})
    
    info = get_video_info(video_id)
    info['video_id'] = video_id
    
    return jsonify(info)

@app.route('/convert', methods=['POST'])
def convert_video():
    """Convert YouTube video using external APIs"""
    data = request.json
    video_url = data.get('url', '')
    service = data.get('service', '')
    
    if not video_url:
        return jsonify({'success': False, 'error': 'No URL provided'})
    
    video_id = extract_video_id(video_url)
    if not video_id:
        return jsonify({'success': False, 'error': 'Invalid YouTube URL'})
    
    try:
        if service == 'loader':
            # Try loader.to API
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Content-Type': 'application/x-www-form-urlencoded',
            }
            
            payload = {
                'url': video_url,
                'format': 'mp3'
            }
            
            response = requests.post(
                'https://loader.to/ajax/download.php',
                data=payload,
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    return jsonify({
                        'success': True,
                        'download_url': result.get('download_url'),
                        'title': result.get('title', f'video_{video_id}'),
                        'service': 'loader.to'
                    })
        
        elif service == 'ytmp3':
            # Try ytmp3 API alternative
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }
            
            # Use a different conversion service
            response = requests.get(
                f'https://api.vevio.com/convert',
                params={'url': video_url, 'format': 'mp3'},
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('url'):
                    return jsonify({
                        'success': True,
                        'download_url': data.get('url'),
                        'title': data.get('title', f'video_{video_id}'),
                        'service': 'ytmp3'
                    })
        
        # Fallback: Return direct download links for user to click
        return jsonify({
            'success': True,
            'direct_links': [
                {
                    'name': 'YTMP3.cc',
                    'url': f'https://ytmp3.cc/?url={video_url}',
                    'type': 'external'
                },
                {
                    'name': 'Loader.to',
                    'url': f'https://loader.to/en87/download-youtube-mp3.html?video={video_url}',
                    'type': 'external'
                },
                {
                    'name': 'Y2Mate',
                    'url': f'https://y2mate.com/youtube/{video_id}',
                    'type': 'external'
                }
            ],
            'message': 'Click any link below to download directly'
        })
        
    except Exception as e:
        return jsonify({
            'success': False, 
            'error': f'Conversion failed: {str(e)}'
        })

@app.route('/upload-mp3', methods=['POST'])
def upload_mp3():
    """Handle MP3 files uploaded from client"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'})
        
        file = request.files['file']
        video_id = request.form.get('video_id', 'unknown')
        video_title = request.form.get('video_title', 'video')
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        if file and (file.filename.endswith('.mp3') or file.content_type == 'audio/mpeg'):
            safe_title = sanitize_filename(video_title)
            filename = f"{safe_title}_{video_id}.mp3"
            file_path = os.path.join(DOWNLOAD_FOLDER, filename)
            file.save(file_path)
            
            return jsonify({
                'success': True, 
                'filename': filename,
                'message': 'File uploaded successfully'
            })
        else:
            return jsonify({'success': False, 'error': 'Invalid file type. Please upload MP3 files only.'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': f'Upload failed: {str(e)}'})

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
    files.sort(key=lambda x: x['modified'], reverse=True)
    return jsonify({'success': True, 'downloads': files})

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'timestamp': time.time()})

if __name__ == "__main__":
    print("🚀 YouTube MP3 Downloader with Direct Conversion")
    print(f"📁 Download folder: {DOWNLOAD_FOLDER}")
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
