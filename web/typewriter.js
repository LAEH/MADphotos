/* typewriter.js — La Machine à Écrire: Semantic text search */

let typewriterInitialized = false;

function initTypewriter() {
    if (typewriterInitialized) return;
    typewriterInitialized = true;

    const container = document.getElementById('view-typewriter');
    container.innerHTML = '';

    const wrap = document.createElement('div');
    wrap.className = 'typewriter-container';

    // Input area
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

    // Results
    const results = document.createElement('div');
    results.className = 'typewriter-results';
    results.id = 'typewriter-results';
    wrap.appendChild(results);

    container.appendChild(wrap);

    // Search on typing (debounced)
    let timeout = null;
    input.addEventListener('input', () => {
        clearTimeout(timeout);
        timeout = setTimeout(() => typewriterSearch(input.value), 600);
    });

    input.focus();
}

function typewriterSearch(query) {
    const results = document.getElementById('typewriter-results');
    if (!query || query.length < 2) {
        results.innerHTML = '';
        return;
    }

    const q = query.toLowerCase();

    // Search across captions, alt text, vibes, objects, scenes, settings
    const scored = [];
    for (const photo of APP.data.photos) {
        if (!photo.thumb) continue;
        let score = 0;

        // Caption match (strongest)
        if (photo.caption && photo.caption.toLowerCase().includes(q)) score += 10;
        // Alt text match
        if (photo.alt && photo.alt.toLowerCase().includes(q)) score += 8;
        // Vibe match
        for (const v of (photo.vibes || [])) {
            if (v.toLowerCase().includes(q)) score += 6;
        }
        // Object match
        for (const obj of (photo.objects || [])) {
            if (obj.toLowerCase().includes(q)) score += 7;
        }
        // Scene match
        if (photo.scene && photo.scene.toLowerCase().includes(q)) score += 5;
        // Setting match
        if (photo.setting && photo.setting.toLowerCase().includes(q)) score += 4;
        // Style match
        if (photo.style && photo.style.toLowerCase().includes(q)) score += 3;
        // Camera match
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

    // Grid of matches
    const grid = document.createElement('div');
    grid.className = 'typewriter-grid';

    for (const { photo } of scored.slice(0, 60)) {
        const card = document.createElement('div');
        card.className = 'typewriter-card';

        const img = createLazyImg(photo, 'thumb');
        lazyObserver.observe(img);
        card.appendChild(img);

        // Caption below
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
