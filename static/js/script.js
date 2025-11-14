class YouTubeDownloader {
    constructor() {
        this.currentDownloadId = null;
        this.progressInterval = null;
        this.init();
    }

    init() {
        this.bindEvents();
        this.loadDownloads();
        this.checkClipboard();
        this.checkCookieStatus();
    }

    bindEvents() {
        const urlInput = document.getElementById('youtubeUrl');
        urlInput.addEventListener('paste', this.handlePaste.bind(this));
        urlInput.addEventListener('input', this.handleUrlInput.bind(this));
        urlInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.startDownload();
        });
    }

    async handlePaste(e) {
        const pastedText = e.clipboardData.getData('text');
        if (this.isValidYouTubeUrl(pastedText)) {
            setTimeout(() => this.getVideoInfo(pastedText), 100);
        }
    }

    async handleUrlInput(e) {
        const url = e.target.value.trim();
        if (this.isValidYouTubeUrl(url)) {
            await this.getVideoInfo(url);
        } else {
            this.hideVideoInfo();
        }
    }

    isValidYouTubeUrl(url) {
        const patterns = [
            /^(https?:\/\/)?(www\.)?(youtube\.com|youtu\.?be)\/.+$/,
            /^https?:\/\/(youtu\.be\/|(www\.)?youtube\.com\/(watch|embed|v)\/)/,
            /^https?:\/\/music\.youtube\.com\/watch\?v=/
        ];
        return patterns.some(p => p.test(url));
    }

    async checkCookieStatus() {
        try {
            const res = await fetch('/cookie-status');
            const data = await res.json();
            if (data.success && data.cookies_available) {
                this.showNotification('Cookies loaded - authentication enabled', 'success');
            }
        } catch (err) {
            // Ignore errors for cookie status check
        }
    }

    async getVideoInfo(url) {
        try {
            this.showLoading();
            const res = await fetch('/info', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ url })
            });
            const data = await res.json();
            this.hideLoading();

            if (data.success) {
                this.displayVideoInfo(data);
                document.getElementById('alreadyDownloaded').classList.toggle('hidden', !data.already_downloaded);
            } else {
                let errorMsg = data.error;
                if (errorMsg.includes('authentication') || errorMsg.includes('Sign in') || errorMsg.includes('bot')) {
                    if (data.cookie_status === 'available') {
                        errorMsg = 'YouTube is requiring authentication. The app is using cookies but this video may still be restricted.';
                    } else {
                        errorMsg = 'YouTube is requiring authentication. Some videos may not be accessible without cookies.';
                    }
                } else if (errorMsg.includes('Private') || errorMsg.includes('unavailable')) {
                    errorMsg = 'This video is private or unavailable.';
                } else if (errorMsg.includes('Invalid YouTube URL')) {
                    errorMsg = 'Please enter a valid YouTube URL.';
                } else if (errorMsg.includes('already been downloaded')) {
                    errorMsg = data.error;
                }
                this.showError(errorMsg);
            }
        } catch (err) {
            this.hideLoading();
            this.showError('Network error. Please check your connection and try again.');
        }
    }

    displayVideoInfo(info) {
        const videoInfo = document.getElementById('videoInfo');
        document.getElementById('videoThumbnail').src = info.thumbnail;
        document.getElementById('videoTitle').textContent = info.title;
        document.getElementById('videoUploader').textContent = info.uploader;
        document.getElementById('videoDuration').textContent = info.duration;
        document.getElementById('videoViews').textContent = this.formatViews(info.view_count);
        videoInfo.classList.remove('hidden');
    }

    hideVideoInfo() {
        document.getElementById('videoInfo').classList.add('hidden');
    }

    async startDownload() {
        const url = document.getElementById('youtubeUrl').value.trim();
        if (!url || !this.isValidYouTubeUrl(url)) return this.showError('Please enter a valid YouTube URL');

        try {
            this.showLoading();
            const downloadBtn = document.getElementById('downloadBtn');
            downloadBtn.disabled = true;
            downloadBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Downloading...';

            const res = await fetch('/download-mp3', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });
            const data = await res.json();
            this.hideLoading();

            if (data.success) {
                this.currentDownloadId = data.download_id;
                this.monitorProgress();
                this.showSuccess('Download started successfully!');
            } else {
                let errorMsg = data.error;
                if (errorMsg.includes('authentication') || errorMsg.includes('Sign in') || errorMsg.includes('bot')) {
                    if (data.cookie_status === 'available') {
                        errorMsg = 'YouTube is requiring authentication for this video. The app is using cookies but this video may be restricted.';
                    } else {
                        errorMsg = 'YouTube is requiring authentication for this video. Some videos require cookies to download.';
                    }
                } else if (errorMsg.includes('already been downloaded')) {
                    this.showAlreadyDownloaded(data.existing_file);
                }
                this.showError(errorMsg);
                downloadBtn.disabled = false;
                downloadBtn.innerHTML = '<i class="fas fa-download"></i> Download';
            }
        } catch (err) {
            this.hideLoading();
            this.showError('Network error. Please check your connection and try again.');
            document.getElementById('downloadBtn').disabled = false;
            document.getElementById('downloadBtn').innerHTML = '<i class="fas fa-download"></i> Download';
        }
    }

    showAlreadyDownloaded(filename) {
        const notification = document.createElement('div');
        notification.className = 'already-downloaded-notification';
        notification.innerHTML = `
            <div class="notification-content">
                <i class="fas fa-info-circle"></i>
                <span>This video was already downloaded!</span>
                <button onclick="playFile('${filename}', '${this.escapeHtml(filename.replace('.mp3', ''))}')" class="play-existing-btn">
                    <i class="fas fa-play"></i> Play
                </button>
                <button onclick="downloadFile('${filename}')" class="download-existing-btn">
                    <i class="fas fa-download"></i> Download
                </button>
            </div>
        `;
        
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #e3f2fd;
            border: 2px solid #2196f3;
            border-radius: 8px;
            padding: 15px;
            z-index: 1000;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        `;
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 8000);
    }

    async monitorProgress() {
        this.showProgressSection();
        this.progressInterval = setInterval(async () => {
            try {
                const res = await fetch(`/progress/${this.currentDownloadId}`);
                const progress = await res.json();
                
                if (progress.finished !== undefined) {
                    this.updateProgress({
                        progress: progress.progress || 0,
                        status: progress.finished ? (progress.error ? 'error' : 'completed') : 'downloading',
                        error: progress.error
                    });

                    if (progress.finished) {
                        clearInterval(this.progressInterval);
                        if (progress.error) {
                            this.showError('Download failed: ' + progress.error);
                        } else {
                            this.showSuccess('Download completed!');
                            this.loadDownloads();
                        }
                        document.getElementById('downloadBtn').disabled = false;
                        document.getElementById('downloadBtn').innerHTML = '<i class="fas fa-download"></i> Download';
                        setTimeout(() => {
                            this.hideProgressSection();
                            this.currentDownloadId = null;
                        }, 3000);
                    }
                } else {
                    this.updateProgress(progress);

                    if (progress.status === 'completed' || progress.status === 'error') {
                        clearInterval(this.progressInterval);
                        if (progress.status === 'completed') {
                            this.showSuccess('Download completed!');
                            this.loadDownloads();
                        } else {
                            this.showError('Download failed: ' + progress.error);
                        }
                        document.getElementById('downloadBtn').disabled = false;
                        document.getElementById('downloadBtn').innerHTML = '<i class="fas fa-download"></i> Download';
                        setTimeout(() => {
                            this.hideProgressSection();
                            this.currentDownloadId = null;
                        }, 3000);
                    }
                }
            } catch (err) {
                console.error('Error monitoring progress:', err);
            }
        }, 1000);
    }

    updateProgress(progress) {
        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');
        const progressStatus = document.getElementById('progressStatus');
        
        if (progressFill) {
            progressFill.style.width = `${progress.progress}%`;
        }
        if (progressText) {
            progressText.textContent = `${Math.round(progress.progress)}%`;
        }
        if (progressStatus) {
            progressStatus.textContent = progress.status === 'downloading' ? 'Downloading...' :
                                       progress.status === 'completed' ? 'Completed!' :
                                       progress.status === 'error' ? 'Error occurred' : 'Processing...';
        }
    }

    showProgressSection() {
        const progressSection = document.getElementById('progressSection');
        if (progressSection) {
            progressSection.classList.remove('hidden');
        }
    }

    hideProgressSection() {
        const progressSection = document.getElementById('progressSection');
        if (progressSection) {
            progressSection.classList.add('hidden');
        }
    }

    async loadDownloads() {
        try {
            const res = await fetch('/downloads-list');
            const data = await res.json();
            if (data.success) {
                this.displayDownloads(data.downloads);
            } else {
                console.error('Failed to load downloads:', data.error);
            }
        } catch (err) {
            console.error('Error loading downloads:', err);
        }
    }

    displayDownloads(downloads) {
        const list = document.getElementById('downloadsList');
        if (!list) return;

        if (!downloads || !downloads.length) {
            list.innerHTML = `<div class="empty-state"><i class="fas fa-music"></i><p>No downloads yet.</p></div>`;
            return;
        }
        
        list.innerHTML = downloads.map(d => `
            <div class="download-item">
                <div class="download-info">
                    <h4>${this.escapeHtml(d.name)}</h4>
                    <div class="download-meta">
                        <span><i class="fas fa-hdd"></i> ${d.size_formatted || this.formatFileSize(d.size)}</span>
                        <span><i class="fas fa-calendar"></i> ${d.modified_formatted || this.formatDate(d.modified)}</span>
                    </div>
                </div>
                <div class="download-actions">
                    <button class="action-btn play-btn" onclick="playFile('${d.filename}', '${this.escapeHtml(d.name)}')">
                        <i class="fas fa-play"></i> Play
                    </button>
                    <button class="action-btn download-btn" onclick="downloadFile('${d.filename}')">
                        <i class="fas fa-download"></i> Download
                    </button>
                    <button class="action-btn delete-btn" onclick="deleteFile('${d.filename}')">
                        <i class="fas fa-trash"></i> Delete
                    </button>
                </div>
            </div>
        `).join('');
    }

    playAudio(filename, title) {
        const audioPlayer = document.getElementById('audioPlayer');
        const nowPlaying = document.getElementById('nowPlayingTitle');
        const section = document.getElementById('audioPlayerSection');
        
        if (!audioPlayer || !nowPlaying || !section) return;

        audioPlayer.src = `/play-audio/${filename}`;
        nowPlaying.textContent = title;
        section.classList.remove('hidden');
        
        audioPlayer.play().catch((err) => {
            console.error('Error playing audio:', err);
            this.showError('Error playing audio. Please try downloading the file instead.');
        });
        
        this.showSuccess(`Now playing: ${title}`);
    }

    stopAudio() {
        const audioPlayer = document.getElementById('audioPlayer');
        const section = document.getElementById('audioPlayerSection');
        
        if (audioPlayer) {
            audioPlayer.pause();
            audioPlayer.currentTime = 0;
        }
        if (section) {
            section.classList.add('hidden');
        }
    }

    async downloadFile(filename) {
        try {
            const res = await fetch(`/get-file/${filename}`);
            if (res.ok) {
                const blob = await res.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                this.showSuccess('Download started!');
            } else {
                const err = await res.json();
                this.showError(err.error || 'Failed to download file');
            }
        } catch (err) {
            this.showError('Network error downloading file');
        }
    }

    async deleteFile(filename) {
        if (!confirm('Are you sure you want to delete this file?')) return;
        
        try {
            const res = await fetch(`/delete/${filename}`, { method: 'DELETE' });
            const data = await res.json();
            if (data.success) {
                this.showSuccess('File deleted successfully!');
                this.loadDownloads();
                const audioPlayer = document.getElementById('audioPlayer');
                if (audioPlayer && audioPlayer.src.includes(filename)) {
                    this.stopAudio();
                }
            } else {
                this.showError(data.error || 'Failed to delete file');
            }
        } catch (err) {
            this.showError('Network error deleting file');
        }
    }

    // Utility methods
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        return (bytes / Math.pow(1024, i)).toFixed(2) + ' ' + sizes[i];
    }

    formatDate(ts) {
        return new Date(ts * 1000).toLocaleDateString();
    }

    formatViews(v) {
        if (v >= 1e9) return (v / 1e9).toFixed(1) + 'B';
        if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M';
        if (v >= 1e3) return (v / 1e3).toFixed(1) + 'K';
        return v;
    }

    escapeHtml(s) {
        const div = document.createElement('div');
        div.textContent = s;
        return div.innerHTML;
    }

    showLoading() {
        const loadingSpinner = document.getElementById('loadingSpinner');
        if (loadingSpinner) {
            loadingSpinner.classList.remove('hidden');
        }
    }

    hideLoading() {
        const loadingSpinner = document.getElementById('loadingSpinner');
        if (loadingSpinner) {
            loadingSpinner.classList.add('hidden');
        }
    }

    showError(msg) {
        this.showNotification(msg, 'error');
    }

    showSuccess(msg) {
        this.showNotification(msg, 'success');
    }

    showNotification(msg, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.innerHTML = `
            <div class="notification-content">
                <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}"></i>
                <span>${msg}</span>
                <button class="notification-close" onclick="this.parentElement.parentElement.remove()">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;
        
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${type === 'success' ? '#d4edda' : type === 'error' ? '#f8d7da' : '#d1ecf1'};
            border: 2px solid ${type === 'success' ? '#c3e6cb' : type === 'error' ? '#f5c6cb' : '#bee5eb'};
            color: ${type === 'success' ? '#155724' : type === 'error' ? '#721c24' : '#0c5460'};
            border-radius: 8px;
            padding: 15px;
            z-index: 1000;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            max-width: 400px;
            animation: slideInRight 0.3s ease-out;
        `;
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 5000);
    }

    async checkClipboard() {
        try {
            const text = await navigator.clipboard.readText();
            if (this.isValidYouTubeUrl(text)) {
                document.getElementById('youtubeUrl').value = text;
                this.getVideoInfo(text);
            }
        } catch (err) {
            // Clipboard access not available, ignore
        }
    }
}

// Global helper functions
function startDownload() { 
    downloader.startDownload(); 
}

function refreshDownloads() { 
    downloader.loadDownloads(); 
}

function playFile(filename, title) { 
    downloader.playAudio(filename, title); 
}

function stopAudio() { 
    downloader.stopAudio(); 
}

function downloadFile(filename) { 
    downloader.downloadFile(filename); 
}

function deleteFile(filename) { 
    downloader.deleteFile(filename); 
}

// Add CSS for notifications
const notificationStyles = `
@keyframes slideInRight {
    from {
        transform: translateX(100%);
        opacity: 0;
    }
    to {
        transform: translateX(0);
        opacity: 1;
    }
}

.notification-content {
    display: flex;
    align-items: center;
    gap: 10px;
}

.notification-close {
    background: none;
    border: none;
    cursor: pointer;
    padding: 4px;
    margin-left: auto;
    opacity: 0.7;
}

.notification-close:hover {
    opacity: 1;
}

.already-downloaded-notification .notification-content {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
}

.play-existing-btn, .download-existing-btn {
    background: #2196f3;
    color: white;
    border: none;
    padding: 6px 12px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 12px;
}

.play-existing-btn:hover, .download-existing-btn:hover {
    background: #1976d2;
}
`;

// Inject styles
const styleSheet = document.createElement('style');
styleSheet.textContent = notificationStyles;
document.head.appendChild(styleSheet);

// Initialize the downloader when DOM is loaded
let downloader;
document.addEventListener('DOMContentLoaded', () => {
    downloader = new YouTubeDownloader();
    
    // Auto-refresh downloads every 30 seconds
    setInterval(() => downloader.loadDownloads(), 30000);
});
