/* caption.js — Caption: A typographic tapestry with auto-cycling spotlight.
   Dense flowing text wall. Every 2.5s a caption lights up and its image appears
   in a large panel. Click to spotlight + open lightbox. */

let captionPhotos = [];
let captionPreviewEl = null;
let captionSpotlightIdx = -1;
let captionCycleTimer = null;
let captionPaused = false;

const CAPTION_COUNT_DESKTOP = 150;
const CAPTION_COUNT_TABLET = 100;
const CAPTION_COUNT_PHONE = 60;
const CAPTION_CYCLE_MS = 2500;

function initCaption() {
    const container = document.getElementById('view-caption');
    container.innerHTML = '';

    /* Clean up timers + stale elements */
    clearInterval(captionCycleTimer);
    captionCycleTimer = null;
    captionPaused = false;
    captionSpotlightIdx = -1;
    if (captionPreviewEl) { captionPreviewEl.remove(); captionPreviewEl = null; }

    const w = window.innerWidth;
    const count = w <= 480 ? CAPTION_COUNT_PHONE
                : w <= 768 ? CAPTION_COUNT_TABLET
                : CAPTION_COUNT_DESKTOP;

    /* Select photos with good captions — prefer florence, fall back to BLIP */
    const pool = APP.data.photos.filter(p => {
        const cap = p.florence || p.caption || '';
        return cap.length > 12 && p.thumb;
    });
    const sorted = [...pool].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0));
    captionPhotos = shuffleArray(sorted.slice(0, count));

    renderCaptionWall(container);
}

function getCaptionText(photo) {
    /* Prefer Florence detailed caption, fall back to BLIP */
    return photo.florence || photo.caption || '';
}

function renderCaptionWall(container) {
    /* Main layout: image panel + text wall */
    const layout = document.createElement('div');
    layout.className = 'caption-layout';

    /* Image panel — large, prominent */
    const panel = document.createElement('div');
    panel.className = 'caption-panel';
    panel.id = 'caption-panel';

    const panelImg = document.createElement('img');
    panelImg.className = 'caption-panel-img';
    panelImg.id = 'caption-panel-img';
    panel.appendChild(panelImg);

    const panelCaption = document.createElement('div');
    panelCaption.className = 'caption-panel-text';
    panelCaption.id = 'caption-panel-text';
    panel.appendChild(panelCaption);

    layout.appendChild(panel);

    /* Text wall side */
    const wallWrap = document.createElement('div');
    wallWrap.className = 'caption-wall-wrap';

    const wall = document.createElement('div');
    wall.className = 'caption-wall';
    wall.id = 'caption-wall';

    for (let i = 0; i < captionPhotos.length; i++) {
        const photo = captionPhotos[i];

        const span = document.createElement('span');
        span.className = 'caption-phrase';
        span.dataset.idx = i;

        span.textContent = cleanCaption(getCaptionText(photo));

        /* Click: spotlight this one, second click opens lightbox */
        span.addEventListener('click', () => {
            if (captionSpotlightIdx === i) {
                openLightbox(photo, captionPhotos);
            } else {
                captionPaused = true;
                spotlightCaption(i);
            }
        });

        wall.appendChild(span);

        if (i < captionPhotos.length - 1) {
            const sep = document.createElement('span');
            sep.className = 'caption-sep';
            sep.textContent = '\u2009\u00B7\u2009';
            wall.appendChild(sep);
        }
    }

    wallWrap.appendChild(wall);
    layout.appendChild(wallWrap);
    container.appendChild(layout);

    /* Stagger-reveal the text */
    requestAnimationFrame(() => {
        const phrases = wall.querySelectorAll('.caption-phrase');
        phrases.forEach((p, i) => {
            p.style.setProperty('--caption-delay', Math.min(i * 6, 800) + 'ms');
        });
        requestAnimationFrame(() => {
            wall.classList.add('revealed');
            /* Start auto-cycle after reveal animation settles */
            setTimeout(() => {
                spotlightCaption(0);
                captionCycleTimer = setInterval(() => {
                    if (captionPaused) return;
                    const next = (captionSpotlightIdx + 1) % captionPhotos.length;
                    spotlightCaption(next);
                }, CAPTION_CYCLE_MS);
                APP._activeTimers.push(captionCycleTimer);
            }, 1200);
        });
    });

    /* Unpause on wall click (not on a phrase) */
    wall.addEventListener('click', (e) => {
        if (e.target === wall || e.target.classList.contains('caption-sep')) {
            captionPaused = false;
        }
    });
}

function spotlightCaption(idx) {
    captionSpotlightIdx = idx;
    const photo = captionPhotos[idx];
    const wall = document.getElementById('caption-wall');
    if (!wall) return;

    /* Highlight active phrase */
    wall.querySelectorAll('.caption-phrase').forEach((el, i) => {
        el.classList.toggle('caption-active', i === idx);
    });

    /* Scroll the active phrase into view (smooth, centered) */
    const activeEl = wall.querySelector(`.caption-phrase[data-idx="${idx}"]`);
    if (activeEl) {
        const wallWrap = wall.parentElement;
        const elRect = activeEl.getBoundingClientRect();
        const wrapRect = wallWrap.getBoundingClientRect();
        const scrollTarget = wallWrap.scrollTop + (elRect.top - wrapRect.top) - wrapRect.height / 2 + elRect.height / 2;
        wallWrap.scrollTo({ top: Math.max(0, scrollTarget), behavior: 'smooth' });
    }

    /* Update image panel */
    const panelImg = document.getElementById('caption-panel-img');
    const panelText = document.getElementById('caption-panel-text');
    const panel = document.getElementById('caption-panel');
    if (!panelImg || !panel) return;

    panel.classList.remove('caption-panel-visible');

    /* Short delay for crossfade */
    setTimeout(() => {
        loadProgressive(panelImg, photo, 'display');
        panelImg.alt = getCaptionText(photo);
        if (panelText) panelText.textContent = cleanCaption(getCaptionText(photo));
        panel.classList.add('caption-panel-visible');
    }, 150);
}

function cleanCaption(text) {
    if (!text) return '';
    let s = text.trim();
    if (s.endsWith('.')) s = s.slice(0, -1);
    return s;
}
