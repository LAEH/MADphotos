/* stream.js — Le Flot: Infinite curated visual stream */

let streamIndex = 0;
let streamLoading = false;
const STREAM_BATCH = 20;

function initStream() {

    const container = document.getElementById('view-stream');
    container.innerHTML = '<div class="loading">Loading stream</div>';

    loadStreamSequence().then(() => {
        container.innerHTML = '';
        const inner = document.createElement('div');
        inner.className = 'stream-container';
        inner.id = 'stream-inner';
        container.appendChild(inner);

        streamIndex = 0;
        loadStreamBatch();

        // Infinite scroll
        const observer = new IntersectionObserver((entries) => {
            if (entries[0].isIntersecting && !streamLoading) {
                loadStreamBatch();
            }
        }, { rootMargin: '600px' });

        const sentinel = document.createElement('div');
        sentinel.id = 'stream-sentinel';
        sentinel.style.height = '1px';
        container.appendChild(sentinel);
        observer.observe(sentinel);
    });
}

function loadStreamBatch() {
    const sequence = APP.streamSequence || [];
    if (streamIndex >= sequence.length) return;
    streamLoading = true;

    const container = document.getElementById('stream-inner');
    const end = Math.min(streamIndex + STREAM_BATCH, sequence.length);

    for (let i = streamIndex; i < end; i++) {
        const photoId = sequence[i];
        const photo = APP.photoMap[photoId];
        if (!photo) continue;

        const isBreather = photo.mono;
        const item = document.createElement('div');
        item.className = 'stream-item' + (isBreather ? ' stream-breather' : '');

        const img = document.createElement('img');
        img.className = 'stream-img';
        img.loading = 'lazy';
        if (photo.micro) img.src = photo.micro;
        img.dataset.src = photo.display || photo.mobile || photo.thumb;
        lazyObserver.observe(img);
        item.appendChild(img);

        if (isBreather && (photo.caption || photo.alt)) {
            const overlay = document.createElement('div');
            overlay.className = 'stream-breather-text';
            overlay.textContent = photo.caption || photo.alt;
            item.appendChild(overlay);
        }

        item.addEventListener('click', () => openLightbox(photo));
        container.appendChild(item);
    }

    streamIndex = end;
    streamLoading = false;
}
