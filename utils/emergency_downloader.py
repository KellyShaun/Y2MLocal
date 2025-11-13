import yt_dlp
import os
import re

class EmergencyYouTubeDownloader:
    def __init__(self, download_folder):
        self.download_folder = download_folder
        print(f"Emergency downloader initialized")

    def get_video_info(self, url):
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                return {
                    'success': True,
                    'title': info.get('title', 'Unknown'),
                    'duration': self.format_duration(info.get('duration', 0)),
                    'thumbnail': info.get('thumbnail', ''),
                    'uploader': info.get('uploader', 'Unknown'),
                    'view_count': info.get('view_count', 0)
                }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def download_audio(self, url, progress_hook=None):
        try:
            # SUPER SIMPLE configuration that should work
            ydl_opts = {
                # Let yt-dlp choose the best approach
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(self.download_folder, '%(title)s.%(ext)s'),
                
                # Force MP3 conversion
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                
                # Basic settings
                'no_warnings': False,
                'ignoreerrors': False,
                'extractaudio': True,
                'audioformat': 'mp3',
            }
            
            if progress_hook:
                ydl_opts['progress_hooks'] = [progress_hook]

            print(f"EMERGENCY: Downloading {url}")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                original_title = info['title']
                
                # Wait a moment for file to be created
                import time
                time.sleep(2)
                
                # Find the MP3 file
                for file in os.listdir(self.download_folder):
                    if file.endswith('.mp3'):
                        print(f"✓ EMERGENCY SUCCESS: {file}")
                        return {
                            'success': True,
                            'filename': file,
                            'title': original_title,
                            'duration': info.get('duration', 0)
                        }
                
                return {'success': False, 'error': 'Emergency download completed but no MP3 found'}
                
        except Exception as e:
            print(f"Emergency download error: {str(e)}")
            return {'success': False, 'error': str(e)}

    def format_duration(self, seconds):
        if not seconds:
            return "00:00"
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes:02d}:{secs:02d}"