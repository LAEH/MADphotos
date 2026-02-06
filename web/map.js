/* map.js — La Carte: GPS-tagged photos on a dark map */

let mapInitialized = false;

function initMap() {
    if (mapInitialized) return;
    mapInitialized = true;

    const container = document.getElementById('view-map');
    container.innerHTML = '';

    const wrap = document.createElement('div');
    wrap.className = 'map-container';

    // Get GPS photos
    const gpsPhotos = APP.data.photos.filter(p => p.gps && p.thumb);

    const header = document.createElement('div');
    header.className = 'map-header';
    header.textContent = gpsPhotos.length + ' GPS-tagged photographs';
    wrap.appendChild(header);

    // Canvas-based dot map
    const canvas = document.createElement('canvas');
    canvas.className = 'map-canvas';
    canvas.id = 'map-canvas';
    canvas.width = 1200;
    canvas.height = 600;
    wrap.appendChild(canvas);

    // Photo strip below map
    const strip = document.createElement('div');
    strip.className = 'map-strip';
    strip.id = 'map-strip';
    wrap.appendChild(strip);

    container.appendChild(wrap);

    renderMapDots(canvas, gpsPhotos);
}

function renderMapDots(canvas, photos) {
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;

    // Dark background
    ctx.fillStyle = '#0a0a0a';
    ctx.fillRect(0, 0, w, h);

    // Draw coastlines hint (simple world outline)
    ctx.strokeStyle = 'rgba(255,255,255,0.06)';
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    ctx.rect(w * 0.01, h * 0.05, w * 0.98, h * 0.9);
    ctx.stroke();

    // Grid lines
    ctx.strokeStyle = 'rgba(255,255,255,0.03)';
    for (let i = 1; i < 6; i++) {
        ctx.beginPath();
        ctx.moveTo(0, h * i / 6);
        ctx.lineTo(w, h * i / 6);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(w * i / 6, 0);
        ctx.lineTo(w * i / 6, h);
        ctx.stroke();
    }

    // Plot photos as luminous dots
    for (const photo of photos) {
        const [lat, lon] = photo.gps;
        // Mercator-ish projection
        const x = ((lon + 180) / 360) * w;
        const y = ((90 - lat) / 180) * h;

        // Color from dominant hue
        const hue = photo.hue || 0;
        ctx.fillStyle = `hsla(${hue}, 70%, 60%, 0.7)`;
        ctx.beginPath();
        ctx.arc(x, y, 2.5, 0, Math.PI * 2);
        ctx.fill();

        // Glow
        ctx.fillStyle = `hsla(${hue}, 70%, 60%, 0.15)`;
        ctx.beginPath();
        ctx.arc(x, y, 6, 0, Math.PI * 2);
        ctx.fill();
    }

    // Click handler
    canvas.addEventListener('click', (e) => {
        const rect = canvas.getBoundingClientRect();
        const scaleX = w / rect.width;
        const scaleY = h / rect.height;
        const cx = (e.clientX - rect.left) * scaleX;
        const cy = (e.clientY - rect.top) * scaleY;

        // Find nearby photos
        const nearby = photos.filter(p => {
            const [lat, lon] = p.gps;
            const x = ((lon + 180) / 360) * w;
            const y = ((90 - lat) / 180) * h;
            return Math.hypot(x - cx, y - cy) < 20;
        });

        renderMapStrip(nearby);
    });
}

function renderMapStrip(photos) {
    const strip = document.getElementById('map-strip');
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
