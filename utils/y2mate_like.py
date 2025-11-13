# utils/y2mate_like.py
import os
import certifi
import platform
import requests
import yt_dlp
from http.cookiejar import MozillaCookieJar
from urllib.parse import urlparse

DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), '..', 'static', 'downloads')
PIPED_INSTANCE = 'https://piped.video'  # change if you prefer another instance
DESKTOP_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
              'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36')


def detect_ffmpeg_path():
    system = platform.system().lower()
    if system.startswith('win'):
        return r'C:\ffmpeg\bin\ffmpeg.exe'
    if os.path.exists('/usr/bin/ffmpeg'):
        return '/usr/bin/ffmpeg'
    if os.path.exists('/usr/local/bin/ffmpeg'):
        return '/usr/local/bin/ffmpeg'
    return 'ffmpeg'


def load_cookies_for_requests(cookie_path):
    """Load a Netscape cookies.txt into a requests.Session cookie jar."""
    if not cookie_path or not os.path.exists(cookie_path):
        return None
    jar = MozillaCookieJar(cookie_path)
    jar.load(ignore_discard=True, ignore_expires=True)
    session = requests.Session()
    session.cookies = jar
    return session


def extract_best_audio_info(url, cookie_path=None, piped_fallback=True, ffmpeg_path=None):
    """
    Use yt-dlp to extract metadata and a direct audio stream URL.
    Returns dict: {success, title, thumbnail, duration, format_id, ext, stream_url}
    """
    ffmpeg_path = ffmpeg_path or detect_ffmpeg_path()
    base_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'force_generic_extractor': True,  # attempt web extraction (avoid iOS/mobile APIs)
        'youtube_include_dash_manifest': False,
        'user_agent': DESKTOP_UA,
        'ca_certs': certifi.where(),
    }
    if cookie_path and os.path.exists(cookie_path):
        base_opts['cookiefile'] = cookie_path

    try:
        with yt_dlp.YoutubeDL(base_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            # choose best audio-only format (acodec not 'none' and high abr or filesize)
            formats = info.get('formats', []) or []
            audio_formats = [f for f in formats if f.get('acodec') and f.get('acodec') != 'none']
            if not audio_formats:
                # fallback: any format
                audio_formats = formats

            # pick by abr (audio bitrate) then filesize then preference for m4a/webm
            def score(f):
                abr = f.get('abr') or 0
                size = f.get('filesize') or f.get('filesize_approx') or 0
                ext = f.get('ext') or ''
                ext_pref = 1 if ext in ('m4a', 'mp4') else (0.9 if ext in ('webm',) else 0.5)
                return (abr * 1000) + size * 0.001 + (ext_pref * 10)

            best = max(audio_formats, key=score)
            stream_url = best.get('url')
            # some URLs are fragment/need headers; provide format id for reference
            return {
                'success': True,
                'extractor': info.get('extractor'),
                'id': info.get('id'),
                'title': info.get('title'),
                'thumbnail': info.get('thumbnail'),
                'duration': info.get('duration'),
                'format_id': best.get('format_id'),
                'ext': best.get('ext'),
                'abr': best.get('abr'),
                'filesize': best.get('filesize') or best.get('filesize_approx'),
                'stream_url': stream_url,
            }
    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        # detect typical YouTube bot checks and optionally fallback to piped
        if piped_fallback and ('Sign in to confirm' in msg or 'Precondition check failed' in msg or 'Unable to download API page' in msg or 'HTTP Error 400' in msg):
            # try using piped service as extractor
            extra = {
                'extractor_args': {'youtube': {'service_url': PIPED_INSTANCE}},
                'force_generic_extractor': False,
                'user_agent': DESKTOP_UA,
                'ca_certs': certifi.where(),
            }
            if cookie_path and os.path.exists(cookie_path):
                extra['cookiefile'] = cookie_path
            try:
                with yt_dlp.YoutubeDL({**base_opts, **extra}) as ydl:
                    info = ydl.extract_info(url, download=False)
                    formats = info.get('formats', []) or []
                    audio_formats = [f for f in formats if f.get('acodec') and f.get('acodec') != 'none']
                    if not audio_formats:
                        audio_formats = formats
                    best = max(audio_formats, key=lambda f: (f.get('abr') or 0))
                    return {
                        'success': True,
                        'extractor': info.get('extractor'),
                        'id': info.get('id'),
                        'title': info.get('title'),
                        'thumbnail': info.get('thumbnail'),
                        'duration': info.get('duration'),
                        'format_id': best.get('format_id'),
                        'ext': best.get('ext'),
                        'abr': best.get('abr'),
                        'filesize': best.get('filesize') or best.get('filesize_approx'),
                        'stream_url': best.get('url'),
                    }
            except Exception as e2:
                return {'success': False, 'error': f'Extractor failed: {e2}'}
        return {'success': False, 'error': msg}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def download_stream_to_file(stream_url, out_path, referer=None, cookie_path=None, chunk_size=1 << 20):
    """
    Download a stream URL using requests, save to out_path (streamed).
    If cookie_path provided, use those cookies for the requests.Session.
    """
    session = load_cookies_for_requests(cookie_path) or requests.Session()
    headers = {
        'User-Agent': DESKTOP_UA,
    }
    if referer:
        headers['Referer'] = referer

    # For some streams, signature or range headers needed; we just stream GET
    with session.get(stream_url, headers=headers, stream=True, timeout=30, verify=certifi.where()) as r:
        r.raise_for_status()
        # try to infer content-length
        total = int(r.headers.get('Content-Length') or 0)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'wb') as f:
            downloaded = 0
            for chunk in r.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
    return {'success': True, 'path': out_path, 'size': os.path.getsize(out_path), 'content_length': total}


# ---------- Example helper wrapper ----------
def fetch_and_save_audio(youtube_url, out_dir=None, cookie_path=None, convert_to_mp3=False, ffmpeg_path=None):
    out_dir = out_dir or os.path.abspath(DEFAULT_DOWNLOAD_DIR)
    os.makedirs(out_dir, exist_ok=True)

    info = extract_best_audio_info(youtube_url, cookie_path=cookie_path)
    if not info.get('success'):
        return info

    title = info['title'] or info['id'] or 'audio'
    safe_title = "".join(c for c in title if c not in '<>:"/\\|?*')[:120]
    ext = info.get('ext') or 'm4a'
    filename = f"{safe_title}.{ext}"
    out_path = os.path.join(out_dir, filename)

    # download stream
    stream_url = info.get('stream_url')
    if not stream_url:
        return {'success': False, 'error': 'No stream URL available'}

    res = download_stream_to_file(stream_url, out_path, referer=youtube_url, cookie_path=cookie_path)
    if not res.get('success'):
        return res

    # Optional: convert to mp3 using ffmpeg (if requested)
    if convert_to_mp3:
        fp = ffmpeg_path or detect_ffmpeg_path()
        mp3_path = os.path.splitext(out_path)[0] + '.mp3'
        # run ffmpeg (blocking)
        import subprocess
        cmd = [fp, '-y', '-i', out_path, '-vn', '-ab', '192k', '-ar', '44100', mp3_path]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            # optionally remove original
            try:
                os.remove(out_path)
            except:
                pass
            return {'success': True, 'path': mp3_path, 'title': title, 'duration': info.get('duration')}
        else:
            return {'success': False, 'error': 'ffmpeg failed', 'stderr': proc.stderr}

    return {'success': True, 'path': out_path, 'title': title, 'duration': info.get('duration')}
