# Test basic Python syntax
print("Python is working")

# Test Flask import
try:
    from flask import Flask
    print("Flask import works")
except ImportError as e:
    print(f"Flask import failed: {e}")

# Test the YouTube downloader import
try:
    from utils.youtube_downloader import YouTubeDownloader
    print("YouTubeDownloader import works")
    
    # Test creating an instance
    downloader = YouTubeDownloader("test_folder")
    print("YouTubeDownloader instance created")
    
except ImportError as e:
    print(f"YouTubeDownloader import failed: {e}")
except Exception as e:
    print(f"YouTubeDownloader creation failed: {e}")

print("All tests completed")