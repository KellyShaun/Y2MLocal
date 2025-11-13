print("Python is working!")
print("Testing basic imports...")

try:
    import flask
    print("✓ Flask imported successfully")
except ImportError as e:
    print(f"✗ Flask import failed: {e}")

try:
    import yt_dlp
    print("✓ yt-dlp imported successfully")
except ImportError as e:
    print(f"✗ yt-dlp import failed: {e}")

try:
    import ffmpeg
    print("✓ ffmpeg-python imported successfully")
except ImportError as e:
    print(f"✗ ffmpeg-python import failed: {e}")

print("Test completed!")