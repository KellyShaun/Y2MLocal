from flask import Flask, render_template, request, jsonify
import os
import time

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    data = request.get_json()
    url = data.get('url', '')
    
    print(f"Download request for: {url}")
    
    # Simulate processing
    time.sleep(2)
    
    return jsonify({
        'success': True,
        'message': 'Download started (simulated)',
        'download_id': str(int(time.time()))
    })

@app.route('/progress/<download_id>')
def progress(download_id):
    return jsonify({
        'status': 'completed',
        'progress': 100,
        'filename': 'test_video.mp3'
    })

@app.route('/downloads')
def downloads():
    return jsonify({
        'success': True,
        'downloads': [
            {
                'filename': 'test_video.mp3',
                'name': 'Test Video',
                'size': 1024,
                'modified': time.time(),
                'url': '/download-file/test_video.mp3'
            }
        ]
    })

if __name__ == '__main__':
    print("Simple YouTube MP3 Downloader starting...")
    print("Open: http://localhost:5000")
    app.run(debug=True, port=5000)