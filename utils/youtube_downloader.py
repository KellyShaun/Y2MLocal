import yt_dlp
import os
import re
import platform


class YouTubeDownloader:
    def __init__(self, download_folder, ffmpeg_path=None, cookie_path=None):
        self.download_folder = download_folder
        self.ffmpeg_location = ffmpeg_path or self.detect_ffmpeg_path()
        self.cookie_path = cookie_path if cookie_path and os.path.exists(cookie_path) else None

        print(f"YouTubeDownloader initialized with folder: {download_folder}")
        print(f"FFmpeg location: {self.ffmpeg_location}")
        if self.cookie_path:
            print(f"Using cookies from: {self.cookie_path}")
        else:
            print("No cookies file found — proceeding anonymously")

    def detect_ffmpeg_path(self):
        """Detects FFmpeg location based on OS/environment."""
        system = platform.system().lower()
        if system.startswith("win"):
            return r"C:\ffmpeg\bin"
        elif os.path.exists("/usr/bin/ffmpeg"):
            return "/usr/bin/ffmpeg"
        elif os.path.exists("/usr/local/bin/ffmpeg"):
            return "/usr/local/bin/ffmpeg"
        else:
            print("⚠️ FFmpeg not found in standard locations; relying on PATH")
            return "ffmpeg"

    def get_video_info(self, url):
        """Get video information without downloading"""
        try:
            print(f"Getting video info for: {url}")
            ydl_opts = {
                'quiet': True,
                'no_warnings': False,
                'ffmpeg_location': self.ffmpeg_location,
            }
            if self.cookie_path:
                ydl_opts['cookiefile'] = self.cookie_path

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
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(self.download_folder, '%(title)s.%(ext)s'),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'ffmpeg_location': self.ffmpeg_location,
                'writethumbnail': False,
                'embedthumbnail': False,
                'addmetadata': True,
                'socket_timeout': 30,
                'retries': 10,
                'extractaudio': True,
                'audioformat': 'mp3',
            }

            if self.cookie_path:
                ydl_opts['cookiefile'] = self.cookie_path

            if progress_hook:
                ydl_opts['progress_hooks'] = [progress_hook]

            print(f"Starting download for: {url}")
            print(f"Using FFmpeg at: {self.ffmpeg_location}")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                original_title = info.get('title', 'unknown_title')
                expected_filename = self.sanitize_filename(f"{original_title}.mp3")
                expected_path = os.path.join(self.download_folder, expected_filename)

                print(f"Expected output: {expected_filename}")
                ydl.download([url])
                print("Download complete")

            if os.path.exists(expected_path):
                print(f"✓ MP3 created: {expected_filename}")
                return {
                    'success': True,
                    'filename': expected_filename,
                    'title': original_title,
                    'duration': info.get('duration', 0)
                }

            # fallback: find the newest MP3 file
            print("Checking for MP3 files in folder...")
            mp3_files = [f for f in os.listdir(self.download_folder) if f.endswith('.mp3')]
            if mp3_files:
                latest = max(mp3_files, key=lambda f: os.path.getctime(os.path.join(self.download_folder, f)))
                print(f"✓ Using fallback file: {latest}")
                return {
                    'success': True,
                    'filename': latest,
                    'title': original_title,
                    'duration': info.get('duration', 0)
                }

            return {'success': False, 'error': 'No MP3 file was created'}

        except Exception as e:
            print(f"Download error: {str(e)}")
            return {'success': False, 'error': str(e)}

    def sanitize_filename(self, filename):
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '')
        filename = filename.replace("'", '').replace('"', '')
        if len(filename) > 100:
            name, ext = os.path.splitext(filename)
            filename = name[:100 - len(ext)] + ext
        return filename

    def format_duration(self, seconds):
        if not seconds:
            return "00:00"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"
