import os
import platform
import tempfile
import subprocess
import uuid
from flask import Flask, request, send_file, jsonify
import yt_dlp
import threading

app = Flask(__name__)

# ----------------------------
# Load cookies from environment
# ----------------------------
def write_cookiefile():
    cookie_env = os.getenv("YOUTUBE_COOKIES")   # <-- Render environment variable
    if cookie_env:
        with open("cookies.txt", "w", encoding="utf8") as f:
            f.write(cookie_env)
        return "cookies.txt"
    return None


# ----------------------------
# In-memory progress tracking
# ----------------------------
downloads_progress = {}

# ----------------------------
# Utility functions
# ----------------------------
def detect_ffmpeg_path():
    system = platform.system().lower()
    if system.startswith("win"):
        return r"C:\ffmpeg\bin\ffmpeg.exe"
    elif os.path.exists("/usr/bin/ffmpeg"):
        return "/usr/bin/ffmpeg"
    elif os.path.exists("/usr/local/bin/ffmpeg"):
        return "/usr/local/bin/ffmpeg"
    else:
        print("⚠️ FFmpeg not found — using PATH")
        return "ffmpeg"

def sanitize_filename(filename):
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '')
    filename = filename.replace("'", "").replace('"', "")
    if len(filename) > 100:
        name, ext = os.path.splitext(filename)
        filename = name[:100 - len(ext)] + ext
    return filename

def create_progress_hook(download_id):
    def hook(d):
        if d["status"] == "downloading":
            percent = d.get("_percent_str", "0%").strip()
            downloads_progress[download_id]["progress"] = percent

        elif d["status"] == "finished":
            downloads_progress[download_id]["progress"] = "100%"
            downloads_progress[download_id]["finished"] = True

    return hook

def extract_audio_info(url, cookie_path=None):
    ydl_opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "noplaylist": True,
    }

    if cookie_path:
        ydl_opts["cookiefile"] = cookie_path

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return {
            "title": info.get("title", "unknown_title"),
            "ext": info.get("ext", "m4a"),
        }

def download_to_mp3(url, download_id, cookie_path):
    try:
        info = extract_audio_info(url, cookie_path)
        title = sanitize_filename(info["title"])
        ext = info["ext"]

        # Temporary working folder
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = os.path.join(tmpdir, f"{title}.{ext}")
            mp3_path = os.path.join(tmpdir, f"{title}.mp3")

            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": audio_path,
                "quiet": True,
                "noplaylist": True,
                "progress_hooks": [create_progress_hook(download_id)],
            }

            if cookie_path:
                ydl_opts["cookiefile"] = cookie_path

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            # Convert to MP3
            ffmpeg = detect_ffmpeg_path()
            subprocess.run([
                ffmpeg, "-y", "-i", audio_path,
                "-vn", "-ab", "192k", "-ar", "44100", mp3_path
            ])

            downloads_progress[download_id]["file"] = mp3_path
            downloads_progress[download_id]["finished"] = True

    except Exception as e:
        downloads_progress[download_id]["error"] = str(e)
        downloads_progress[download_id]["finished"] = True


# ----------------------------
# Flask Routes
# ----------------------------

@app.route("/download-mp3", methods=["POST"])
def download_mp3():
    data = request.get_json()
    url = data.get("url")

    if not url:
        return jsonify({"success": False, "error": "No URL provided"}), 400

    # Load YouTube cookies ONCE here
    cookie_path = write_cookiefile()

    # Create download ID
    download_id = str(uuid.uuid4())
    downloads_progress[download_id] = {
        "progress": "0%",
        "finished": False,
        "file": None
    }

    # Run the download in background
    threading.Thread(
        target=download_to_mp3,
        args=(url, download_id, cookie_path),
        daemon=True
    ).start()

    return jsonify({"success": True, "download_id": download_id})


@app.route("/progress/<download_id>")
def progress(download_id):
    info = downloads_progress.get(download_id)
    if not info:
        return jsonify({"success": False, "error": "Invalid ID"}), 404
    return jsonify(info)


@app.route("/get-file/<download_id>")
def get_file(download_id):
    info = downloads_progress.get(download_id)
    if not info or not info.get("finished") or not info.get("file"):
        return jsonify({"success": False, "error": "File not ready"}), 400
    return send_file(
        info["file"],
        as_attachment=True,
        download_name=os.path.basename(info["file"])
    )


@app.route("/")
def home():
    return "🎵 YouTube → MP3 service running!"


# ----------------------------
# Main
# ----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

