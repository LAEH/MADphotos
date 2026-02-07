/* typewriter.js — La Machine a Ecrire: Semantic text search */

const debouncedTypewriterSearch = debounce(typewriterSearch, 500);

function initTypewriter() {
    const container = document.getElementById('view-typewriter');
    container.innerHTML = '';

    const wrap = document.createElement('div');
    wrap.className = 'typewriter-container';

    /* Input area */
    const inputArea = document.createElement('div');
    inputArea.className = 'typewriter-input-area';

    const input = document.createElement('input');
    input.className = 'typewriter-input';
    input.type = 'text';
    input.placeholder = 'Type anything...';
    input.id = 'typewriter-field';
    inputArea.appendChild(input);

    const cursor = document.createElement('span');
    cursor.className = 'typewriter-cursor';
    inputArea.appendChild(cursor);

    wrap.appendChild(inputArea);

    /* Results */
    const results = document.createElement('div');
    results.className = 'typewriter-results';
    results.id = 'typewriter-results';
    wrap.appendChild(results);

    container.appendChild(wrap);

    /* Search on typing — uses shared debounce utility */
    input.addEventListener('input', () => {
        debouncedTypewriterSearch(input.value);
    });

    input.focus();
}

function typewriterSearch(query) {
    const results = document.getElementById('typewriter-results');
    if (!results) return;
    if (!query || query.length < 2) {
        results.innerHTML = '';
        return;
    }

    const q = query.toLowerCase();

    /* Search across captions, alt text, vibes, objects, scenes, settings */
    const scored = [];
    for (const photo of APP.data.photos) {
        if (!photo.thumb) continue;
        let score = 0;

        if (photo.caption && photo.caption.toLowerCase().includes(q)) score += 10;
        if (photo.alt && photo.alt.toLowerCase().includes(q)) score += 8;
        for (const v of (photo.vibes || [])) {
            if (v.toLowerCase().includes(q)) score += 6;
        }
        for (const obj of (photo.objects || [])) {
            if (obj.toLowerCase().includes(q)) score += 7;
        }
        if (photo.scene && photo.scene.toLowerCase().includes(q)) score += 5;
        if (photo.setting && photo.setting.toLowerCase().includes(q)) score += 4;
        if (photo.style && photo.style.toLowerCase().includes(q)) score += 3;
        if (photo.camera && photo.camera.toLowerCase().includes(q)) score += 2;

        if (score > 0) scored.push({ photo, score });
    }

    scored.sort((a, b) => b.score - a.score);

    results.innerHTML = '';

    if (scored.length === 0) {
        results.innerHTML = '<div class="typewriter-empty">No matches</div>';
        return;
    }

    const countLabel = document.createElement('div');
    countLabel.className = 'typewriter-count';
    countLabel.textContent = scored.length + ' matches';
    results.appendChild(countLabel);

    /* Grid of matches */
    const grid = document.createElement('div');
    grid.className = 'typewriter-grid';

    for (const { photo } of scored.slice(0, 60)) {
        const card = document.createElement('div');
        card.className = 'typewriter-card';

        const img = createLazyImg(photo, 'thumb');
        lazyObserver.observe(img);
        card.appendChild(img);

        if (photo.caption) {
            const cap = document.createElement('div');
            cap.className = 'typewriter-card-caption';
            cap.textContent = photo.caption;
            card.appendChild(cap);
        }

        card.addEventListener('click', () => openLightbox(photo));
        grid.appendChild(card);
    }

    results.appendChild(grid);
}
