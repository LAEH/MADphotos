/* observatory.js — L'Observatoire: Data visualization panels */

function initObservatory() {

    const container = document.getElementById('view-observatory');
    container.innerHTML = '';

    const wrap = document.createElement('div');
    wrap.className = 'observatory-container';

    // Panel 1: Camera distribution
    wrap.appendChild(createObsPanel('Camera Fleet', renderCameraPanel));
    // Panel 2: Aesthetic distribution
    wrap.appendChild(createObsPanel('Aesthetic Scores', renderAestheticPanel));
    // Panel 3: Time of day
    wrap.appendChild(createObsPanel('Time of Day', renderTimePanel));
    // Panel 4: Style distribution
    wrap.appendChild(createObsPanel('Styles', renderStylePanel));
    // Panel 5: Emotion spectrum
    wrap.appendChild(createObsPanel('Emotions', renderEmotionPanel));
    // Panel 6: Outliers
    wrap.appendChild(createObsPanel('Outliers', renderOutlierPanel));

    container.appendChild(wrap);
}

function createObsPanel(title, renderFn) {
    const panel = document.createElement('div');
    panel.className = 'obs-panel';

    const header = document.createElement('h3');
    header.className = 'obs-panel-title';
    header.textContent = title;
    panel.appendChild(header);

    const content = document.createElement('div');
    content.className = 'obs-panel-content';
    renderFn(content);
    panel.appendChild(content);

    return panel;
}

function renderCameraPanel(el) {
    const cameras = APP.data.cameras || [];
    const counts = {};
    for (const p of APP.data.photos) {
        const cam = p.camera || 'Unknown';
        counts[cam] = (counts[cam] || 0) + 1;
    }
    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    const max = sorted[0] ? sorted[0][1] : 1;

    for (const [cam, count] of sorted) {
        const row = document.createElement('div');
        row.className = 'obs-bar-row';
        const bar = document.createElement('div');
        bar.className = 'obs-bar';
        bar.style.width = (count / max * 100) + '%';
        row.innerHTML = `<span class="obs-bar-label">${cam}</span>`;
        row.appendChild(bar);
        const countEl = document.createElement('span');
        countEl.className = 'obs-bar-count';
        countEl.textContent = count;
        row.appendChild(countEl);
        el.appendChild(row);
    }
}

function renderAestheticPanel(el) {
    // Histogram of aesthetic scores (0-10 in 0.5 buckets)
    const buckets = new Array(20).fill(0);
    for (const p of APP.data.photos) {
        if (p.aesthetic != null) {
            const idx = Math.min(19, Math.floor(p.aesthetic / 0.5));
            buckets[idx]++;
        }
    }
    const max = Math.max(...buckets, 1);

    const chart = document.createElement('div');
    chart.className = 'obs-histogram';
    for (let i = 0; i < buckets.length; i++) {
        const bar = document.createElement('div');
        bar.className = 'obs-hist-bar';
        bar.style.height = (buckets[i] / max * 100) + '%';
        bar.title = `${(i * 0.5).toFixed(1)}-${((i + 1) * 0.5).toFixed(1)}: ${buckets[i]}`;
        chart.appendChild(bar);
    }
    el.appendChild(chart);
}

function renderTimePanel(el) {
    const times = APP.data.times || [];
    const counts = {};
    for (const p of APP.data.photos) {
        if (p.time) counts[p.time] = (counts[p.time] || 0) + 1;
    }

    for (const [time, count] of Object.entries(counts).sort((a, b) => b[1] - a[1])) {
        const tag = createGlassTag(time, { category: 'time' });
        const countSpan = document.createElement('span');
        countSpan.className = 'obs-inline-count';
        countSpan.textContent = ' ' + count;
        tag.appendChild(countSpan);
        el.appendChild(tag);
    }
}

function renderStylePanel(el) {
    const counts = {};
    for (const p of APP.data.photos) {
        if (p.style) counts[p.style] = (counts[p.style] || 0) + 1;
    }
    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    const max = sorted[0] ? sorted[0][1] : 1;

    for (const [style, count] of sorted) {
        const row = document.createElement('div');
        row.className = 'obs-bar-row';
        const bar = document.createElement('div');
        bar.className = 'obs-bar obs-bar-style';
        bar.style.width = (count / max * 100) + '%';
        row.innerHTML = `<span class="obs-bar-label">${titleCase(style)}</span>`;
        row.appendChild(bar);
        const countEl = document.createElement('span');
        countEl.className = 'obs-bar-count';
        countEl.textContent = count;
        row.appendChild(countEl);
        el.appendChild(row);
    }
}

function renderEmotionPanel(el) {
    const counts = {};
    for (const p of APP.data.photos) {
        if (p.emotion) counts[p.emotion] = (counts[p.emotion] || 0) + 1;
    }
    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);

    for (const [emo, count] of sorted) {
        const tag = createGlassTag(emo, { category: 'emotion' });
        const c = document.createElement('span');
        c.className = 'obs-inline-count';
        c.textContent = ' ' + count;
        tag.appendChild(c);
        el.appendChild(tag);
    }
}

function renderOutlierPanel(el) {
    const photos = APP.data.photos;

    // Highest aesthetic
    const byAesthetic = [...photos].filter(p => p.aesthetic != null).sort((a, b) => b.aesthetic - a.aesthetic);
    if (byAesthetic.length) {
        const row = createOutlierRow('Highest aesthetic', byAesthetic[0]);
        el.appendChild(row);
    }

    // Most objects
    const byObjects = [...photos].sort((a, b) => b.object_count - a.object_count);
    if (byObjects[0] && byObjects[0].object_count > 0) {
        el.appendChild(createOutlierRow('Most objects (' + byObjects[0].object_count + ')', byObjects[0]));
    }

    // Most faces
    const byFaces = [...photos].sort((a, b) => b.face_count - a.face_count);
    if (byFaces[0] && byFaces[0].face_count > 0) {
        el.appendChild(createOutlierRow('Most faces (' + byFaces[0].face_count + ')', byFaces[0]));
    }

    // Deepest (highest depth complexity)
    const byDepth = [...photos].filter(p => p.depth_complexity != null).sort((a, b) => b.depth_complexity - a.depth_complexity);
    if (byDepth.length) {
        el.appendChild(createOutlierRow('Deepest', byDepth[0]));
    }
}

function createOutlierRow(label, photo) {
    const row = document.createElement('div');
    row.className = 'obs-outlier-row clickable-img';

    const thumb = document.createElement('img');
    thumb.src = photo.micro || photo.thumb;
    thumb.className = 'obs-outlier-thumb';
    row.appendChild(thumb);

    const text = document.createElement('span');
    text.className = 'obs-outlier-label';
    text.textContent = label;
    row.appendChild(text);

    row.addEventListener('click', () => openLightbox(photo));
    return row;
}
