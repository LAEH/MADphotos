/* caption.js — Caption: Cinematic photo storytelling.
   Full-screen image with word-by-word story reveal using Gemma analysis.
   No text on the image. Story appears beside (desktop) or below (mobile).
   Auto-advances after reading time. */

let captionPhotos = [];
let captionGemma = null;
let captionIdx = -1;
let captionTimer = null;
let captionWordTimer = null;
let captionPaused = false;

/* ms per word for the typewriter reveal */
const WORD_DELAY = 120;
/* Extra reading time after all words revealed (ms) */
const READ_PAUSE = 3000;

function initCaption() {
    const container = document.getElementById('view-caption');
    container.innerHTML = '';
    clearTimeout(captionTimer);
    clearTimeout(captionWordTimer);
    captionTimer = null;
    captionWordTimer = null;
    captionPaused = false;
    captionIdx = -1;

    /* Load Gemma data, then start */
    if (captionGemma) {
        _startCaption(container);
    } else {
        fetch('data/gemma_picks.json?v=' + Date.now())
            .then(r => r.json())
            .then(data => { captionGemma = data; _startCaption(container); })
            .catch(() => { captionGemma = {}; _startCaption(container); });
    }
}

function _startCaption(container) {
    /* Filter to photos that have Gemma story data */
    const pool = APP.data.photos.filter(p => {
        if (!p.thumb || !p.display) return false;
        const g = captionGemma[p.id];
        return g && (g.story || g.description);
    });

    if (pool.length === 0) {
        container.innerHTML = '<div class="loading">No stories available yet.</div>';
        return;
    }

    const sorted = [...pool].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0));
    captionPhotos = shuffleArray(sorted.slice(0, 80));

    renderCaptionView(container);
    showNextStory();
}

function buildStoryText(photo) {
    const g = captionGemma[photo.id];
    if (!g) return '';

    const parts = [];
    if (g.description) parts.push(g.description);
    if (g.story && g.story !== g.description) parts.push(g.story);
    if (g.mood) parts.push(g.mood + '.');
    return parts.join(' ').replace(/\s+/g, ' ').trim();
}

function renderCaptionView(container) {
    const layout = document.createElement('div');
    layout.className = 'caption-layout';

    /* Image side — clean, no overlay text */
    const imgWrap = document.createElement('div');
    imgWrap.className = 'caption-img-wrap';
    imgWrap.id = 'caption-img-wrap';
    const img = document.createElement('img');
    img.className = 'caption-img';
    img.id = 'caption-img';
    imgWrap.appendChild(img);
    layout.appendChild(imgWrap);

    /* Story side */
    const storyWrap = document.createElement('div');
    storyWrap.className = 'caption-story-wrap';
    storyWrap.id = 'caption-story-wrap';

    const storyText = document.createElement('div');
    storyText.className = 'caption-story-text';
    storyText.id = 'caption-story-text';
    storyWrap.appendChild(storyText);

    /* Counter */
    const counter = document.createElement('div');
    counter.className = 'caption-counter';
    counter.id = 'caption-counter';
    storyWrap.appendChild(counter);

    layout.appendChild(storyWrap);
    container.appendChild(layout);

    /* Click story area to pause/unpause */
    storyWrap.addEventListener('click', () => {
        captionPaused = !captionPaused;
        if (!captionPaused) scheduleNext();
    });

    /* Click image to open lightbox */
    imgWrap.addEventListener('click', () => {
        if (captionIdx >= 0) openLightbox(captionPhotos[captionIdx], captionPhotos);
    });
}

function showNextStory() {
    captionIdx = (captionIdx + 1) % captionPhotos.length;
    const photo = captionPhotos[captionIdx];
    const story = buildStoryText(photo);
    const words = story.split(/\s+/).filter(Boolean);

    const imgWrap = document.getElementById('caption-img-wrap');
    const img = document.getElementById('caption-img');
    const textEl = document.getElementById('caption-story-text');
    const counter = document.getElementById('caption-counter');
    if (!imgWrap || !img || !textEl) return;

    /* Fade out current */
    imgWrap.classList.remove('caption-visible');
    textEl.classList.remove('caption-visible');

    setTimeout(() => {
        /* Set dominant color bg */
        if (photo.palette && photo.palette[0]) {
            imgWrap.style.backgroundColor = photo.palette[0] + '40';
        }

        /* Load image */
        loadProgressive(img, photo, 'display');
        img.alt = '';

        /* Update counter */
        if (counter) counter.textContent = (captionIdx + 1) + ' / ' + captionPhotos.length;

        /* Clear old words */
        textEl.innerHTML = '';

        /* Create word spans */
        for (let i = 0; i < words.length; i++) {
            const span = document.createElement('span');
            span.className = 'caption-word';
            span.textContent = words[i];
            textEl.appendChild(span);
            if (i < words.length - 1) textEl.appendChild(document.createTextNode(' '));
        }

        /* Fade in image */
        requestAnimationFrame(() => {
            imgWrap.classList.add('caption-visible');
            textEl.classList.add('caption-visible');
        });

        /* Reveal words one by one */
        const wordSpans = textEl.querySelectorAll('.caption-word');
        let wi = 0;
        clearTimeout(captionWordTimer);

        function revealNext() {
            if (wi < wordSpans.length) {
                wordSpans[wi].classList.add('caption-word-visible');
                wi++;
                captionWordTimer = setTimeout(revealNext, WORD_DELAY);
            } else {
                /* All words revealed — wait for reading, then advance */
                scheduleNext();
            }
        }
        /* Start word reveal after image fades in */
        captionWordTimer = setTimeout(revealNext, 500);
    }, 400);
}

function scheduleNext() {
    clearTimeout(captionTimer);
    if (captionPaused) return;
    captionTimer = setTimeout(() => {
        if (APP.currentView !== 'caption') return;
        showNextStory();
    }, READ_PAUSE);
    APP._activeTimers.push(captionTimer);
}
