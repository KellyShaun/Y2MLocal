import yt_dlp
import os
import re

class SimpleYouTubeDownloader:
    def __init__(self, download_folder):
        self.download_folder = download_folder
        # Simpler options that work better
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(download_folder, '%(title)s.%(ext)s'),
            'postprocessors': [],
        }
        print(f"SimpleYouTubeDownloader initialized")

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
            opts = self.ydl_opts.copy()
            if progress_hook:
                opts['progress_hooks'] = [progress_hook]

            # Download as m4a (usually works better)
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
            }]

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                original_title = info['title']
                
                # Download
                ydl.download([url])
                
                # Look for m4a file
                for file in os.listdir(self.download_folder):
                    if file.endswith('.m4a'):
                        return {
                            'success': True,
                            'filename': file,
                            'title': original_title,
                            'duration': info.get('duration', 0)
                        }
                
                return {'success': False, 'error': 'Download completed but no audio file found'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def format_duration(self, seconds):
        if not seconds:
            return "00:00"
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes:02d}:{secs:02d}"