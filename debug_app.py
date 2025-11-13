import traceback
import sys

print("Starting debug...")

try:
    print("1. Testing Flask import...")
    from flask import Flask, render_template, request, jsonify, send_file, after_this_request
    from flask_cors import CORS
    print("✓ Flask imports successful")
    
    print("2. Testing other imports...")
    import os
    import threading
    import json
    import time
    import logging
    print("✓ Standard imports successful")
    
    print("3. Testing YouTube downloader import...")
    # Try to import the YouTube downloader
    try:
        from utils.youtube_downloader import YouTubeDownloader
        print("✓ YouTubeDownloader import successful")
    except ImportError as e:
        print(f"✗ YouTubeDownloader import failed: {e}")
        # Create a simple mock for testing
        class YouTubeDownloader:
            def __init__(self, folder):
                self.download_folder = folder
            def download_audio(self, url, progress_hook=None):
                return {'success': False, 'error': 'Mock downloader'}
            def get_video_info(self, url):
                return {'success': False, 'error': 'Mock info'}
    
    print("4. Initializing Flask app...")
    # Get the absolute path to the project directory
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    app = Flask(__name__)
    CORS(app)
    app.config['SECRET_KEY'] = 'your-secret-key-here'
    app.config['DOWNLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'downloads')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

    print(f"Download folder path: {app.config['DOWNLOAD_FOLDER']}")

    # Ensure download directory exists
    os.makedirs(app.config['DOWNLOAD_FOLDER'], exist_ok=True)
    
    print("5. Setting up routes...")
    
    @app.route('/')
    def index():
        return "Debug app is working! If you see this, the basic setup works."
    
    @app.route('/test')
    def test():
        return jsonify({'status': 'success', 'message': 'Test route working'})
    
    print("6. All setup complete, starting server...")
    
    if __name__ == '__main__':
        print("Server starting on http://localhost:5000")
        print("Press CTRL+C to stop the server")
        app.run(debug=True, host='0.0.0.0', port=5000)
        
except Exception as e:
    print(f"ERROR: {e}")
    print("FULL TRACEBACK:")
    traceback.print_exc()
    input("Press Enter to exit...")