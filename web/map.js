/* map.js — La Carte: GPS-tagged photos on a dark map */

function initMap() {
    const container = document.getElementById('view-map');
    container.innerHTML = '';

    const wrap = document.createElement('div');
    wrap.className = 'map-container';

    const gpsPhotos = APP.data.photos.filter(p => p.gps && p.thumb);

    const header = document.createElement('div');
    header.className = 'map-header';
    header.textContent = gpsPhotos.length + ' GPS-tagged photographs';
    wrap.appendChild(header);

    /* Retina-aware canvas */
    const dpr = window.devicePixelRatio || 1;
    const cssW = 1200, cssH = 600;
    const canvas = document.createElement('canvas');
    canvas.className = 'map-canvas';
    canvas.id = 'map-canvas';
    canvas.width = cssW * dpr;
    canvas.height = cssH * dpr;
    canvas.style.width = cssW + 'px';
    canvas.style.height = cssH + 'px';
    wrap.appendChild(canvas);

    const strip = document.createElement('div');
    strip.className = 'map-strip';
    strip.id = 'map-strip';
    wrap.appendChild(strip);

    container.appendChild(wrap);

    renderMapDots(canvas, gpsPhotos, dpr);
}

function renderMapDots(canvas, photos, dpr) {
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;

    ctx.scale(dpr, dpr);
    const lw = w / dpr;
    const lh = h / dpr;

    /* Dark background — read from immersive view container (forced dark) */
    const mapEl = document.getElementById('view-map');
    const mapStyle = getComputedStyle(mapEl);
    ctx.fillStyle = mapStyle.getPropertyValue('--bg').trim() || '#000';
    ctx.fillRect(0, 0, lw, lh);

    /* World outline hint */
    ctx.strokeStyle = mapStyle.getPropertyValue('--glass-border').trim() || 'rgba(255,255,255,0.06)';
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    ctx.rect(lw * 0.01, lh * 0.05, lw * 0.98, lh * 0.9);
    ctx.stroke();

    /* Grid lines */
    ctx.strokeStyle = 'rgba(255,255,255,0.03)';
    for (let i = 1; i < 6; i++) {
        ctx.beginPath();
        ctx.moveTo(0, lh * i / 6);
        ctx.lineTo(lw, lh * i / 6);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(lw * i / 6, 0);
        ctx.lineTo(lw * i / 6, lh);
        ctx.stroke();
    }

    /* Plot photos as luminous dots */
    for (const photo of photos) {
        const [lat, lon] = photo.gps;
        const x = ((lon + 180) / 360) * lw;
        const y = ((90 - lat) / 180) * lh;

        const hue = photo.hue || 0;

        /* Glow first (behind dot) */
        ctx.fillStyle = `hsla(${hue}, 70%, 60%, 0.15)`;
        ctx.beginPath();
        ctx.arc(x, y, 6, 0, Math.PI * 2);
        ctx.fill();

        /* Dot */
        ctx.fillStyle = `hsla(${hue}, 70%, 60%, 0.7)`;
        ctx.beginPath();
        ctx.arc(x, y, 2.5, 0, Math.PI * 2);
        ctx.fill();
    }

    /* Click handler — uses logical (CSS) coordinates */
    canvas.addEventListener('click', (e) => {
        const rect = canvas.getBoundingClientRect();
        const cx = (e.clientX - rect.left) * (lw / rect.width);
        const cy = (e.clientY - rect.top) * (lh / rect.height);

        const nearby = photos.filter(p => {
            const [lat, lon] = p.gps;
            const x = ((lon + 180) / 360) * lw;
            const y = ((90 - lat) / 180) * lh;
            return Math.hypot(x - cx, y - cy) < 20;
        });

        renderMapStrip(nearby);
    });
}

function renderMapStrip(photos) {
    const strip = document.getElementById('map-strip');
    if (!strip) return;
    strip.innerHTML = '';

    for (const photo of photos.slice(0, 20)) {
        const card = document.createElement('div');
        card.className = 'map-strip-card';

        const img = createLazyImg(photo, 'thumb');
        lazyObserver.observe(img);
        card.appendChild(img);

        card.addEventListener('click', () => openLightbox(photo));
        strip.appendChild(card);
    }
}
