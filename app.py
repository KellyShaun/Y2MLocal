import os
import time
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

@app.route('/')
def home():
    return render_template("index.html")

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
            # Create a safe filename
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
    # Sort by modification time (newest first)
    files.sort(key=lambda x: x['modified'], reverse=True)
    return jsonify({'success': True, 'downloads': files})

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'timestamp': time.time()})

if __name__ == "__main__":
    print("🚀 YouTube MP3 Manager started")
    print("💡 Users download externally and upload files here")
    print(f"📁 Download folder: {DOWNLOAD_FOLDER}")
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
