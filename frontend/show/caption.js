/* caption.js — Caption: A typographic tapestry of photograph descriptions.
   Dense flowing text wall. Hover reveals image preview, click opens lightbox.
   Captions sized by aesthetic score — the best photos speak loudest. */

let captionPhotos = [];
let captionPreviewEl = null;
let captionPreviewTimer = null;

const CAPTION_COUNT_DESKTOP = 200;
const CAPTION_COUNT_TABLET = 120;
const CAPTION_COUNT_PHONE = 60;

function initCaption() {
    const container = document.getElementById('view-caption');
    container.innerHTML = '';

    /* Clean up any stale preview from previous visit */
    if (captionPreviewEl) { captionPreviewEl.remove(); captionPreviewEl = null; }

    const w = window.innerWidth;
    const count = w <= 480 ? CAPTION_COUNT_PHONE
                : w <= 768 ? CAPTION_COUNT_TABLET
                : CAPTION_COUNT_DESKTOP;

    /* Select photos that have captions, sorted by aesthetic */
    const pool = APP.data.photos.filter(p => p.caption && p.caption.length > 8 && p.thumb);
    const sorted = [...pool].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0));

    /* Take top N, then shuffle for visual variety */
    captionPhotos = shuffleArray(sorted.slice(0, count));

    renderCaptionWall(container);
}

function renderCaptionWall(container) {
    /* Scroll wrapper */
    const wrap = document.createElement('div');
    wrap.className = 'caption-wrap';

    /* The flowing text block */
    const wall = document.createElement('div');
    wall.className = 'caption-wall';
    wall.id = 'caption-wall';

    /* Aesthetic range for sizing */
    const scores = captionPhotos.map(p => p.aesthetic || 5);
    const minScore = Math.min(...scores);
    const maxScore = Math.max(...scores);
    const range = maxScore - minScore || 1;

    for (let i = 0; i < captionPhotos.length; i++) {
        const photo = captionPhotos[i];

        /* Normalized 0–1 from aesthetic score */
        const t = ((photo.aesthetic || 5) - minScore) / range;

        /* Size tier: 5 tiers from the type scale */
        const tier = Math.min(4, Math.floor(t * 5));

        const span = document.createElement('span');
        span.className = 'caption-phrase';
        span.dataset.idx = i;
        span.dataset.tier = tier;

        /* Opacity: lower-scored captions are dimmer */
        span.style.opacity = (0.3 + t * 0.7).toFixed(2);

        span.textContent = cleanCaption(photo.caption);

        /* Hover: show preview */
        span.addEventListener('mouseenter', (e) => showCaptionPreview(photo, e));
        span.addEventListener('mousemove', (e) => moveCaptionPreview(e));
        span.addEventListener('mouseleave', hideCaptionPreview);

        /* Touch: tap to preview, second tap opens lightbox */
        span.addEventListener('click', (e) => {
            if ('ontouchstart' in window) {
                if (span.classList.contains('caption-touched')) {
                    openLightbox(photo, captionPhotos);
                } else {
                    document.querySelectorAll('.caption-touched').forEach(el => el.classList.remove('caption-touched'));
                    span.classList.add('caption-touched');
                    showCaptionPreview(photo, e);
                }
            } else {
                openLightbox(photo, captionPhotos);
            }
        });

        wall.appendChild(span);

        /* Separator — thin interpunct between phrases */
        if (i < captionPhotos.length - 1) {
            const sep = document.createElement('span');
            sep.className = 'caption-sep';
            sep.textContent = '\u2009\u00B7\u2009';
            wall.appendChild(sep);
        }
    }

    wrap.appendChild(wall);
    container.appendChild(wrap);

    /* Create the floating preview element once */
    if (captionPreviewEl) captionPreviewEl.remove();
    captionPreviewEl = document.createElement('div');
    captionPreviewEl.className = 'caption-preview';
    captionPreviewEl.id = 'caption-preview';
    const previewImg = document.createElement('img');
    previewImg.className = 'caption-preview-img';
    captionPreviewEl.appendChild(previewImg);
    document.body.appendChild(captionPreviewEl);

    /* Stagger-fade the phrases in */
    requestAnimationFrame(() => {
        const phrases = wall.querySelectorAll('.caption-phrase');
        phrases.forEach((p, i) => {
            p.style.setProperty('--caption-delay', Math.min(i * 8, 1500) + 'ms');
        });
        requestAnimationFrame(() => wall.classList.add('revealed'));
    });
}

function cleanCaption(text) {
    if (!text) return '';
    /* Strip leading "A/An/The" + trim to keep it punchy, capitalize first */
    let s = text.trim();
    /* Remove trailing period */
    if (s.endsWith('.')) s = s.slice(0, -1);
    return s;
}

/* ===== Floating Preview ===== */
function showCaptionPreview(photo, e) {
    if (!captionPreviewEl) return;
    clearTimeout(captionPreviewTimer);

    const img = captionPreviewEl.querySelector('.caption-preview-img');
    loadProgressive(img, photo, 'thumb');
    img.alt = '';

    captionPreviewEl.classList.add('visible');
    positionPreview(e);
}

function moveCaptionPreview(e) {
    positionPreview(e);
}

function positionPreview(e) {
    if (!captionPreviewEl) return;
    const pad = 20;
    const pw = 180;
    const ph = 130;

    let x = e.clientX + pad;
    let y = e.clientY - ph - pad;

    /* Keep within viewport */
    if (x + pw > window.innerWidth) x = e.clientX - pw - pad;
    if (y < 0) y = e.clientY + pad;

    captionPreviewEl.style.left = x + 'px';
    captionPreviewEl.style.top = y + 'px';
}

function hideCaptionPreview() {
    if (!captionPreviewEl) return;
    captionPreviewEl.classList.remove('visible');
}
