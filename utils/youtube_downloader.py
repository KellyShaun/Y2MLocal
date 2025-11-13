import yt_dlp
import os
import re

class YouTubeDownloader:
    def __init__(self, download_folder):
        self.download_folder = download_folder
        # Direct path to FFmpeg - use the same path that worked in the manual test
        self.ffmpeg_location = r"C:\ffmpeg\bin"
        print(f"YouTubeDownloader initialized with folder: {download_folder}")
        print(f"FFmpeg location: {self.ffmpeg_location}")

    def get_video_info(self, url):
        """Get video information without downloading"""
        try:
            print(f"Getting video info for: {url}")
            ydl_opts = {
                'quiet': True,
                'no_warnings': False,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                print(f"Video info retrieved: {info.get('title', 'Unknown')}")
                return {
                    'success': True,
                    'title': info.get('title', 'Unknown'),
                    'duration': self.format_duration(info.get('duration', 0)),
                    'thumbnail': info.get('thumbnail', ''),
                    'uploader': info.get('uploader', 'Unknown'),
                    'view_count': info.get('view_count', 0)
                }
        except Exception as e:
            print(f"Error getting video info: {str(e)}")
            return {'success': False, 'error': str(e)}

    def download_audio(self, url, progress_hook=None):
        """Download audio from YouTube URL"""
        try:
            # YouTube downloader options - using the same settings that worked in manual test
            ydl_opts = {
                # Format selection
                'format': 'bestaudio/best',
                
                # Output template
                'outtmpl': os.path.join(self.download_folder, '%(title)s.%(ext)s'),
                
                # Post-processing to convert to MP3 - EXACT SAME as manual test
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                
                # FFmpeg location - EXACT SAME as manual test
                'ffmpeg_location': self.ffmpeg_location,
                
                # Basic settings
                'writethumbnail': False,
                'embedthumbnail': False,
                'addmetadata': True,
                
                # Network settings
                'socket_timeout': 30,
                'retries': 10,
                
                # Additional settings to match manual test
                'extractaudio': True,
                'audioformat': 'mp3',
            }

            # Add progress hook if provided
            if progress_hook:
                ydl_opts['progress_hooks'] = [progress_hook]

            print(f"Starting download process for: {url}")
            print(f"Using FFmpeg at: {self.ffmpeg_location}")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Get info first
                info = ydl.extract_info(url, download=False)
                original_title = info['title']
                expected_filename = self.sanitize_filename(f"{original_title}.mp3")
                expected_path = os.path.join(self.download_folder, expected_filename)
                
                print(f"Expected output: {expected_filename}")
                
                # Download the audio
                print("Starting download and conversion...")
                ydl.download([url])
                print("Download process completed")
            
            # Check if MP3 file was created
            if os.path.exists(expected_path):
                print(f"✓ MP3 file created successfully: {expected_filename}")
                return {
                    'success': True,
                    'filename': expected_filename,
                    'title': original_title,
                    'duration': info.get('duration', 0)
                }
            
            # If expected file doesn't exist, look for any MP3 files
            print("Checking for MP3 files in download folder...")
            mp3_files = []
            for file in os.listdir(self.download_folder):
                if file.endswith('.mp3'):
                    mp3_files.append(file)
                    print(f"Found MP3 file: {file}")
            
            if mp3_files:
                latest_file = max(mp3_files, key=lambda f: os.path.getctime(os.path.join(self.download_folder, f)))
                print(f"✓ Using MP3 file: {latest_file}")
                return {
                    'success': True,
                    'filename': latest_file,
                    'title': original_title,
                    'duration': info.get('duration', 0)
                }
            
            return {'success': False, 'error': 'No MP3 files were created'}
                
        except Exception as e:
            print(f"Download error: {str(e)}")
            return {'success': False, 'error': str(e)}

    def sanitize_filename(self, filename):
        """Remove invalid characters from filename"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '')
        filename = filename.replace('\'', '').replace('"', '')
        
        if len(filename) > 100:
            name, ext = os.path.splitext(filename)
            filename = name[:100-len(ext)] + ext
            
        return filename

    def format_duration(self, seconds):
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