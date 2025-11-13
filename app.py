from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import os
import threading
import time
import logging
import json

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get the absolute path to the project directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['DOWNLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'downloads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

print(f"Starting YouTube MP3 Downloader...")
print(f"Download folder: {app.config['DOWNLOAD_FOLDER']}")

# Ensure download directory exists
os.makedirs(app.config['DOWNLOAD_FOLDER'], exist_ok=True)

# Import YouTubeDownloader
try:
    from utils.youtube_downloader import YouTubeDownloader
    print("✓ YouTubeDownloader imported successfully")
except ImportError as e:
    print(f"✗ YouTubeDownloader import failed: {e}")
    # Create simple fallback
    class YouTubeDownloader:
        def __init__(self, folder):
            self.download_folder = folder
            print("Using fallback downloader")
        def download_audio(self, url, progress_hook=None):
            return {'success': False, 'error': 'Downloader not available'}
        def get_video_info(self, url):
            return {'success': False, 'error': 'Downloader not available'}

# Store download progress (temporary - resets on app restart)
download_progress = {}

# File to store download history persistently
HISTORY_FILE = os.path.join(BASE_DIR, 'download_history.json')

def load_download_history():
    """Load download history from file"""
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading history: {e}")
    return []

def save_download_history(history):
    """Save download history to file"""
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving history: {e}")

# Load existing history on startup
download_history = load_download_history()
print(f"Loaded {len(download_history)} downloads from history")

class DownloadThread(threading.Thread):
    def __init__(self, url, download_id):
        threading.Thread.__init__(self)
        self.url = url
        self.download_id = download_id
        self.downloader = YouTubeDownloader(app.config['DOWNLOAD_FOLDER'])

    def run(self):
        try:
            download_progress[self.download_id] = {
                'status': 'downloading',
                'progress': 0,
                'filename': None,
                'error': None
            }
            
            print(f"Starting download for URL: {self.url}")
            result = self.downloader.download_audio(self.url, self.progress_hook)
            print(f"Download result: {result}")
            
            if result['success']:
                download_progress[self.download_id] = {
                    'status': 'completed',
                    'progress': 100,
                    'filename': result['filename'],
                    'title': result['title'],
                    'duration': result['duration'],
                    'error': None
                }
                print(f"Download completed successfully: {result['filename']}")
                
                # Add to download history and save persistently
                download_entry = {
                    'filename': result['filename'],
                    'title': result['title'],
                    'url': self.url,
                    'timestamp': time.time(),
                    'duration': result['duration'],
                    'file_size': self.get_file_size(result['filename'])
                }
                download_history.append(download_entry)
                save_download_history(download_history)
                
            else:
                download_progress[self.download_id] = {
                    'status': 'error',
                    'progress': 0,
                    'filename': None,
                    'error': result['error']
                }
                print(f"Download failed: {result['error']}")
                
        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            download_progress[self.download_id] = {
                'status': 'error',
                'progress': 0,
                'filename': None,
                'error': str(e)
            }

    def progress_hook(self, d):
        if d['status'] == 'downloading':
            if '_percent_str' in d:
                percent = d['_percent_str'].strip().replace('%', '')
                try:
                    progress = float(percent)
                    download_progress[self.download_id]['progress'] = progress
                    print(f"Download progress: {progress}%")
                except ValueError:
                    pass
        elif d['status'] == 'finished':
            download_progress[self.download_id]['progress'] = 100
            print("Download finished, converting to MP3...")

    def get_file_size(self, filename):
        """Get file size in bytes"""
        try:
            filepath = os.path.join(app.config['DOWNLOAD_FOLDER'], filename)
            return os.path.getsize(filepath)
        except:
            return 0

def list_downloads_internal():
    """Internal function to list all MP3 files with enhanced info"""
    downloads = []
    download_folder = app.config['DOWNLOAD_FOLDER']
    
    if os.path.exists(download_folder):
        files = os.listdir(download_folder)
        
        for filename in files:
            if filename.endswith('.mp3'):
                filepath = os.path.join(download_folder, filename)
                try:
                    stats = os.stat(filepath)
                    
                    # Find matching history entry for additional info
                    history_entry = None
                    for entry in download_history:
                        if entry.get('filename') == filename:
                            history_entry = entry
                            break
                    
                    download_info = {
                        'filename': filename,
                        'name': filename.replace('.mp3', ''),
                        'size': stats.st_size,
                        'size_formatted': format_file_size(stats.st_size),
                        'modified': stats.st_mtime,
                        'modified_formatted': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stats.st_mtime)),
                        'url': f'/download-file/{filename}',
                        'play_url': f'/play-audio/{filename}',
                        'source_url': history_entry.get('url', '') if history_entry else '',
                        'duration': history_entry.get('duration', 0) if history_entry else 0,
                        'duration_formatted': format_duration(history_entry.get('duration', 0)) if history_entry else 'Unknown'
                    }
                    downloads.append(download_info)
                    print(f"Added to downloads list: {filename}")
                    
                except Exception as e:
                    print(f"Error processing file {filename}: {e}")
    
    # Sort by modification time (newest first)
    downloads.sort(key=lambda x: x['modified'], reverse=True)
    return downloads

def format_file_size(size_bytes):
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0 Bytes"
    
    size_names = ["Bytes", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
        
    return f"{size_bytes:.2f} {size_names[i]}"

def format_duration(seconds):
    """Format duration in seconds to HH:MM:SS"""
    if not seconds:
        return "00:00"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download_audio():
    try:
        data = request.get_json()
        url = data.get('url')
        
        if not url:
            return jsonify({'success': False, 'error': 'No URL provided'})
        
        # Check if this video is already downloaded
        existing_downloads = list_downloads_internal()
        for download in existing_downloads:
            if download.get('source_url') == url:
                return jsonify({
                    'success': False, 
                    'error': 'This video has already been downloaded!',
                    'existing_file': download['filename']
                })
        
        # Generate unique download ID
        download_id = str(int(time.time() * 1000))
        
        # Start download in background thread
        download_thread = DownloadThread(url, download_id)
        download_thread.start()
        
        return jsonify({
            'success': True, 
            'download_id': download_id,
            'message': 'Download started'
        })
        
    except Exception as e:
        logger.error(f"Error starting download: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/progress/<download_id>')
def get_progress(download_id):
    progress = download_progress.get(download_id, {
        'status': 'unknown',
        'progress': 0,
        'filename': None,
        'error': None
    })
    return jsonify(progress)

@app.route('/downloads')
def list_downloads():
    try:
        downloads = list_downloads_internal()
        print(f"Found {len(downloads)} MP3 files in download folder")
        return jsonify({'success': True, 'downloads': downloads})
        
    except Exception as e:
        print(f"Error in list_downloads: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/download-file/<filename>')
def download_file(filename):
    try:
        # Sanitize filename for security
        filename = os.path.basename(filename)
        filepath = os.path.join(app.config['DOWNLOAD_FOLDER'], filename)
        
        print(f"Looking for file: {filepath}")
        
        if not os.path.exists(filepath):
            print(f"File not found: {filepath}")
            return jsonify({'success': False, 'error': 'File not found'})
        
        print(f"File found, sending: {filename}")
        return send_file(filepath, as_attachment=True, download_name=filename)
        
    except Exception as e:
        print(f"Error in download_file: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/play-audio/<filename>')
def play_audio(filename):
    """Serve audio file for playback in browser"""
    try:
        # Sanitize filename for security
        filename = os.path.basename(filename)
        filepath = os.path.join(app.config['DOWNLOAD_FOLDER'], filename)
        
        print(f"Looking for audio file to play: {filepath}")
        
        if not os.path.exists(filepath):
            print(f"Audio file not found: {filepath}")
            return jsonify({'success': False, 'error': 'Audio file not found'})
        
        print(f"Audio file found, serving for playback: {filename}")
        return send_file(filepath, mimetype='audio/mpeg')
        
    except Exception as e:
        print(f"Error serving audio file: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/info', methods=['POST'])
def get_video_info():
    try:
        data = request.get_json()
        url = data.get('url')
        
        if not url:
            return jsonify({'success': False, 'error': 'No URL provided'})
        
        # Check if already downloaded
        existing_downloads = list_downloads_internal()
        for download in existing_downloads:
            if download.get('source_url') == url:
                return jsonify({
                    'success': True,
                    'title': download['name'],
                    'duration': download['duration_formatted'],
                    'thumbnail': '',
                    'uploader': 'Already Downloaded',
                    'view_count': 0,
                    'already_downloaded': True,
                    'existing_file': download['filename']
                })
        
        downloader = YouTubeDownloader(app.config['DOWNLOAD_FOLDER'])
        info = downloader.get_video_info(url)
        
        return jsonify(info)
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/delete/<filename>', methods=['DELETE'])
def delete_file(filename):
    try:
        filename = os.path.basename(filename)
        filepath = os.path.join(app.config['DOWNLOAD_FOLDER'], filename)
        
        print(f"Attempting to delete: {filepath}")
        
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"File deleted: {filename}")
            
            # Remove from history
            global download_history
            download_history = [entry for entry in download_history if entry.get('filename') != filename]
            save_download_history(download_history)
            
            return jsonify({'success': True, 'message': 'File deleted'})
        else:
            print(f"File not found for deletion: {filepath}")
            return jsonify({'success': False, 'error': 'File not found'})
            
    except Exception as e:
        print(f"Error deleting file: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/stats')
def get_stats():
    """Get download statistics"""
    downloads = list_downloads_internal()
    total_size = sum(d['size'] for d in downloads)
    
    return jsonify({
        'success': True,
        'stats': {
            'total_downloads': len(downloads),
            'total_size': total_size,
            'total_size_formatted': format_file_size(total_size),
            'history_entries': len(download_history)
        }
    })

if __name__ == '__main__':
    # Show existing downloads on startup
    existing_downloads = list_downloads_internal()
    print(f"Found {len(existing_downloads)} existing MP3 files")
    for download in existing_downloads[:5]:  # Show first 5
        print(f"  - {download['name']} ({download['size_formatted']})")
    if len(existing_downloads) > 5:
        print(f"  ... and {len(existing_downloads) - 5} more files")
    
    print("Server starting on http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)