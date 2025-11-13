class YouTubeDownloader {
    constructor() {
        this.currentDownloadId = null;
        this.progressInterval = null;
        this.init();
    }

    init() {
        this.bindEvents();
        this.loadDownloads();
        
        // Check for URL in clipboard on page load
        this.checkClipboard();
    }

    bindEvents() {
        // URL input events
        const urlInput = document.getElementById('youtubeUrl');
        urlInput.addEventListener('paste', this.handlePaste.bind(this));
        urlInput.addEventListener('input', this.handleUrlInput.bind(this));
        
        // Enter key support
        urlInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.startDownload();
            }
        });
    }

    async handlePaste(e) {
        const pastedText = e.clipboardData.getData('text');
        if (this.isValidYouTubeUrl(pastedText)) {
            setTimeout(() => {
                this.getVideoInfo(pastedText);
            }, 100);
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
        return patterns.some(pattern => pattern.test(url));
    }

    async getVideoInfo(url) {
        try {
            this.showLoading();
            
            const response = await fetch('/info', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ url: url })
            });

            const data = await response.json();
            this.hideLoading();

            if (data.success) {
                this.displayVideoInfo(data);
                
                // Show already downloaded message if applicable
                if (data.already_downloaded) {
                    document.getElementById('alreadyDownloaded').classList.remove('hidden');
                } else {
                    document.getElementById('alreadyDownloaded').classList.add('hidden');
                }
            } else {
                this.showError('Could not fetch video information: ' + data.error);
            }
        } catch (error) {
            this.hideLoading();
            this.showError('Error fetching video information: ' + error.message);
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
        const urlInput = document.getElementById('youtubeUrl');
        const url = urlInput.value.trim();

        if (!url) {
            this.showError('Please enter a YouTube URL');
            return;
        }

        if (!this.isValidYouTubeUrl(url)) {
            this.showError('Please enter a valid YouTube URL');
            return;
        }

        try {
            this.showLoading();
            const downloadBtn = document.getElementById('downloadBtn');
            downloadBtn.disabled = true;
            downloadBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Downloading...';

            const response = await fetch('/download', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ url: url })
            });

            const data = await response.json();
            this.hideLoading();

            if (data.success) {
                this.currentDownloadId = data.download_id;
                this.monitorProgress();
                this.showSuccess('Download started successfully!');
            } else {
                if (data.error.includes('already been downloaded')) {
                    this.showError(data.error);
                    // Optionally, play the existing file
                    if (data.existing_file) {
                        const existingDownloads = await this.getDownloads();
                        const existingFile = existingDownloads.find(d => d.filename === data.existing_file);
                        if (existingFile) {
                            this.playAudio(existingFile.filename, existingFile.name);
                        }
                    }
                } else {
                    this.showError('Download failed: ' + data.error);
                }
                downloadBtn.disabled = false;
                downloadBtn.innerHTML = '<i class="fas fa-download"></i> Download';
            }
        } catch (error) {
            this.hideLoading();
            this.showError('Error starting download: ' + error.message);
            document.getElementById('downloadBtn').disabled = false;
            document.getElementById('downloadBtn').innerHTML = '<i class="fas fa-download"></i> Download';
        }
    }

    async monitorProgress() {
        this.showProgressSection();
        
        this.progressInterval = setInterval(async () => {
            try {
                const response = await fetch(`/progress/${this.currentDownloadId}`);
                const progress = await response.json();

                this.updateProgress(progress);

                if (progress.status === 'completed' || progress.status === 'error') {
                    clearInterval(this.progressInterval);
                    
                    if (progress.status === 'completed') {
                        this.showSuccess('Download completed successfully!');
                        // Refresh downloads list
                        setTimeout(() => {
                            this.loadDownloads();
                        }, 1000);
                    } else {
                        this.showError('Download failed: ' + progress.error);
                    }
                    
                    // Reset download button
                    document.getElementById('downloadBtn').disabled = false;
                    document.getElementById('downloadBtn').innerHTML = '<i class="fas fa-download"></i> Download';
                    
                    setTimeout(() => {
                        this.hideProgressSection();
                        this.currentDownloadId = null;
                    }, 5000);
                }
            } catch (error) {
                console.error('Error monitoring progress:', error);
            }
        }, 1000);
    }

    updateProgress(progress) {
        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');
        const progressStatus = document.getElementById('progressStatus');

        progressFill.style.width = `${progress.progress}%`;
        progressText.textContent = `${Math.round(progress.progress)}%`;
        
        switch (progress.status) {
            case 'downloading':
                progressStatus.textContent = 'Downloading...';
                break;
            case 'completed':
                progressStatus.textContent = 'Completed!';
                break;
            case 'error':
                progressStatus.textContent = 'Error occurred';
                break;
            default:
                progressStatus.textContent = 'Processing...';
        }
    }

    showProgressSection() {
        document.getElementById('progressSection').classList.remove('hidden');
    }

    hideProgressSection() {
        document.getElementById('progressSection').classList.add('hidden');
    }

    async getDownloads() {
        try {
            const response = await fetch('/downloads');
            const data = await response.json();
            return data.success ? data.downloads : [];
        } catch (error) {
            console.error('Error getting downloads:', error);
            return [];
        }
    }

    async loadDownloads() {
        try {
            console.log('Loading downloads list...');
            const response = await fetch('/downloads');
            const data = await response.json();

            console.log('Downloads response:', data);

            if (data.success) {
                this.displayDownloads(data.downloads);
            } else {
                this.showError('Error loading downloads: ' + data.error);
            }
        } catch (error) {
            console.error('Error loading downloads:', error);
            this.showError('Error loading downloads: ' + error.message);
        }
    }

    displayDownloads(downloads) {
        const downloadsList = document.getElementById('downloadsList');
        
        console.log('Displaying downloads:', downloads);
        
        if (downloads.length === 0) {
            downloadsList.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-music"></i>
                    <p>No downloads yet. Convert your first YouTube video above!</p>
                </div>
            `;
            return;
        }

        downloadsList.innerHTML = downloads.map(download => `
            <div class="download-item">
                <div class="download-info">
                    <h4>${this.escapeHtml(download.name)}</h4>
                    <div class="download-meta">
                        <span><i class="fas fa-hdd"></i> ${download.size_formatted || this.formatFileSize(download.size)}</span>
                        <span><i class="fas fa-clock"></i> ${download.duration_formatted || 'Unknown'}</span>
                        <span><i class="fas fa-calendar"></i> ${download.modified_formatted || this.formatDate(download.modified)}</span>
                    </div>
                </div>
                <div class="download-actions">
                    <button class="action-btn play-btn" onclick="playFile('${download.filename}', '${this.escapeHtml(download.name)}')">
                        <i class="fas fa-play"></i> Play
                    </button>
                    <button class="action-btn download-btn" onclick="downloadFile('${download.filename}')">
                        <i class="fas fa-download"></i> Download
                    </button>
                    <button class="action-btn delete-btn" onclick="deleteFile('${download.filename}')">
                        <i class="fas fa-trash"></i> Delete
                    </button>
                </div>
            </div>
        `).join('');
    }

    playAudio(filename, title) {
        try {
            const audioPlayer = document.getElementById('audioPlayer');
            const nowPlayingTitle = document.getElementById('nowPlayingTitle');
            const audioPlayerSection = document.getElementById('audioPlayerSection');
            
            // Set audio source
            const audioUrl = `/play-audio/${filename}`;
            audioPlayer.src = audioUrl;
            
            // Update now playing title
            nowPlayingTitle.textContent = title;
            
            // Show audio player
            audioPlayerSection.classList.remove('hidden');
            
            // Try to play
            audioPlayer.play().catch(e => {
                console.log('Auto-play prevented:', e);
                // User interaction required for autoplay in some browsers
            });
            
            this.showSuccess(`Now playing: ${title}`);
            
        } catch (error) {
            this.showError('Error playing audio: ' + error.message);
        }
    }

    stopAudio() {
        const audioPlayer = document.getElementById('audioPlayer');
        audioPlayer.pause();
        audioPlayer.currentTime = 0;
    }

    async downloadFile(filename) {
        try {
            console.log('Downloading file:', filename);
            const response = await fetch(`/download-file/${filename}`);
            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
                this.showSuccess('File download started!');
            } else {
                const error = await response.json();
                this.showError('Download failed: ' + error.error);
            }
        } catch (error) {
            this.showError('Error downloading file: ' + error.message);
        }
    }

    async deleteFile(filename) {
        if (!confirm('Are you sure you want to delete this file?')) {
            return;
        }

        try {
            console.log('Deleting file:', filename);
            const response = await fetch(`/delete/${filename}`, {
                method: 'DELETE'
            });

            const data = await response.json();

            if (data.success) {
                this.showSuccess('File deleted successfully!');
                this.loadDownloads();
                
                // Stop audio if the deleted file was playing
                const audioPlayer = document.getElementById('audioPlayer');
                if (audioPlayer.src.includes(filename)) {
                    this.stopAudio();
                    document.getElementById('audioPlayerSection').classList.add('hidden');
                }
            } else {
                this.showError('Delete failed: ' + data.error);
            }
        } catch (error) {
            this.showError('Error deleting file: ' + error.message);
        }
    }

    // Utility functions
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    formatDate(timestamp) {
        return new Date(timestamp * 1000).toLocaleDateString();
    }

    formatViews(views) {
        if (views >= 1000000) {
            return (views / 1000000).toFixed(1) + 'M';
        } else if (views >= 1000) {
            return (views / 1000).toFixed(1) + 'K';
        }
        return views;
    }

    escapeHtml(unsafe) {
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    showLoading() {
        document.getElementById('loadingSpinner').classList.remove('hidden');
    }

    hideLoading() {
        document.getElementById('loadingSpinner').classList.add('hidden');
    }

    showError(message) {
        alert('Error: ' + message);
    }

    showSuccess(message) {
        alert('Success: ' + message);
    }

    async checkClipboard() {
        try {
            const text = await navigator.clipboard.readText();
            if (this.isValidYouTubeUrl(text)) {
                document.getElementById('youtubeUrl').value = text;
                this.getVideoInfo(text);
            }
        } catch (err) {
            // Clipboard access not available or denied
        }
    }
}

// Global functions for HTML onclick handlers
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

// Initialize the application
const downloader = new YouTubeDownloader();

// Auto-refresh downloads list every 30 seconds
setInterval(() => {
    downloader.loadDownloads();

}, 30000);
