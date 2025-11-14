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
                this.showError('Could not fetch video info: ' + data.error);
            }
        } catch (err) {
            this.hideLoading();
            this.showError('Error fetching video info: ' + err.message);
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
                this.showError(data.error);
                downloadBtn.disabled = false;
                downloadBtn.innerHTML = '<i class="fas fa-download"></i> Download';
            }
        } catch (err) {
            this.hideLoading();
            this.showError('Error starting download: ' + err.message);
            document.getElementById('downloadBtn').disabled = false;
            document.getElementById('downloadBtn').innerHTML = '<i class="fas fa-download"></i> Download';
        }
    }

    async monitorProgress() {
        this.showProgressSection();
        this.progressInterval = setInterval(async () => {
            try {
                const res = await fetch(`/progress/${this.currentDownloadId}`);
                const progress = await res.json();
                this.updateProgress(progress);

                if (progress.status === 'completed' || progress.status === 'error') {
                    clearInterval(this.progressInterval);
                    if (progress.status === 'completed') {
                        this.showSuccess('Download completed!');
                        this.loadDownloads(); // refresh downloads
                    } else {
                        this.showError('Download failed: ' + progress.error);
                    }
                    document.getElementById('downloadBtn').disabled = false;
                    document.getElementById('downloadBtn').innerHTML = '<i class="fas fa-download"></i> Download';
                    setTimeout(() => {
                        this.hideProgressSection();
                        this.currentDownloadId = null;
                    }, 2000);
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
        progressFill.style.width = `${progress.progress}%`;
        progressText.textContent = `${Math.round(progress.progress)}%`;
        progressStatus.textContent = progress.status === 'downloading' ? 'Downloading...' :
                                     progress.status === 'completed' ? 'Completed!' :
                                     progress.status === 'error' ? 'Error occurred' : 'Processing...';
    }

    showProgressSection() {
        document.getElementById('progressSection').classList.remove('hidden');
    }

    hideProgressSection() {
        document.getElementById('progressSection').classList.add('hidden');
    }

    async loadDownloads() {
        try {
            const res = await fetch('/downloads-list'); // <- new endpoint you need in Flask
            const data = await res.json();
            if (data.success) this.displayDownloads(data.downloads);
        } catch (err) {
            console.error('Error loading downloads:', err);
        }
    }

    displayDownloads(downloads) {
        const list = document.getElementById('downloadsList');
        if (!downloads.length) {
            list.innerHTML = `<div class="empty-state"><i class="fas fa-music"></i><p>No downloads yet.</p></div>`;
            return;
        }
        list.innerHTML = downloads.map(d => `
            <div class="download-item">
                <div class="download-info">
                    <h4>${this.escapeHtml(d.name)}</h4>
                    <div class="download-meta">
                        <span><i class="fas fa-hdd"></i> ${d.size_formatted || this.formatFileSize(d.size)}</span>
                        <span><i class="fas fa-clock"></i> ${d.duration_formatted || 'Unknown'}</span>
                        <span><i class="fas fa-calendar"></i> ${d.modified_formatted || this.formatDate(d.modified)}</span>
                    </div>
                </div>
                <div class="download-actions">
                    <button class="action-btn play-btn" onclick="playFile('${d.filename}', '${this.escapeHtml(d.name)}')"><i class="fas fa-play"></i> Play</button>
                    <button class="action-btn download-btn" onclick="downloadFile('${d.filename}')"><i class="fas fa-download"></i> Download</button>
                    <button class="action-btn delete-btn" onclick="deleteFile('${d.filename}')"><i class="fas fa-trash"></i> Delete</button>
                </div>
            </div>
        `).join('');
    }

    playAudio(filename, title) {
        const audioPlayer = document.getElementById('audioPlayer');
        const nowPlaying = document.getElementById('nowPlayingTitle');
        const section = document.getElementById('audioPlayerSection');
        audioPlayer.src = `/play-audio/${filename}`;
        nowPlaying.textContent = title;
        section.classList.remove('hidden');
        audioPlayer.play().catch(() => {});
        this.showSuccess(`Now playing: ${title}`);
    }

    stopAudio() {
        const audioPlayer = document.getElementById('audioPlayer');
        audioPlayer.pause();
        audioPlayer.currentTime = 0;
    }

    async downloadFile(filename) {
        const res = await fetch(`/get-file/${filename}`);
        if (res.ok) {
            const blob = await res.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url; a.download = filename; a.click();
            window.URL.revokeObjectURL(url);
            this.showSuccess('File download started!');
        } else {
            const err = await res.json();
            this.showError(err.error);
        }
    }

    async deleteFile(filename) {
        if (!confirm('Are you sure?')) return;
        const res = await fetch(`/delete/${filename}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
            this.showSuccess('Deleted successfully!');
            this.loadDownloads();
            if (document.getElementById('audioPlayer').src.includes(filename)) {
                this.stopAudio();
                document.getElementById('audioPlayerSection').classList.add('hidden');
            }
        } else this.showError(data.error);
    }

    formatFileSize(bytes) { const sizes = ['Bytes','KB','MB','GB']; if(bytes===0) return '0 Bytes'; const i=Math.floor(Math.log(bytes)/Math.log(1024)); return (bytes/Math.pow(1024,i)).toFixed(2)+' '+sizes[i]; }
    formatDate(ts) { return new Date(ts*1000).toLocaleDateString(); }
    formatViews(v) { return v>=1e6 ? (v/1e6).toFixed(1)+'M' : v>=1e3 ? (v/1e3).toFixed(1)+'K' : v; }
    escapeHtml(s) { return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#039;"); }
    showLoading() { document.getElementById('loadingSpinner').classList.remove('hidden'); }
    hideLoading() { document.getElementById('loadingSpinner').classList.add('hidden'); }
    showError(msg) { alert('Error: '+msg); }
    showSuccess(msg) { alert('Success: '+msg); }

    async checkClipboard() {
        try {
            const text = await navigator.clipboard.readText();
            if (this.isValidYouTubeUrl(text)) {
                document.getElementById('youtubeUrl').value = text;
                this.getVideoInfo(text);
            }
        } catch {}
    }
}

// Global helpers
function startDownload() { downloader.startDownload(); }
function refreshDownloads() { downloader.loadDownloads(); }
function playFile(filename, title) { downloader.playAudio(filename, title); }
function stopAudio() { downloader.stopAudio(); }
function downloadFile(filename) { downloader.downloadFile(filename); }
function deleteFile(filename) { downloader.deleteFile(filename); }

// Initialize
const downloader = new YouTubeDownloader();
setInterval(() => downloader.loadDownloads(), 30000);
