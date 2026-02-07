/* darkroom.js — La Chambre Noire: All signals for one image */

let darkroomCurrentPhoto = null;
let darkroomLayers = { colors: true, depth: false, objects: false, faces: false, ocr: false, meta: true };

function initDarkroom() {

    const container = document.getElementById('view-darkroom');
    container.innerHTML = '';
    container.className = 'view active darkroom-view';

    const inner = document.createElement('div');
    inner.className = 'darkroom-container';
    inner.id = 'darkroom-inner';
    container.appendChild(inner);

    // Pick a random photo with rich signals
    const rich = APP.data.photos.filter(p => p.vibes.length > 0 && p.thumb);
    const photo = randomFrom(rich.length ? rich : APP.data.photos);
    renderDarkroom(photo);

    document.addEventListener('keydown', darkroomKeyHandler);
}

function darkroomKeyHandler(e) {
    if (APP.currentView !== 'darkroom') return;
    const keyMap = { '1': 'colors', '2': 'depth', '3': 'objects', '4': 'faces', '5': 'ocr', '6': 'meta' };
    if (keyMap[e.key]) {
        e.preventDefault();
        darkroomLayers[keyMap[e.key]] = !darkroomLayers[keyMap[e.key]];
        if (darkroomCurrentPhoto) renderDarkroom(darkroomCurrentPhoto);
    }
    if (e.key === 'n' || e.key === 'N') {
        e.preventDefault();
        const photos = APP.data.photos.filter(p => p.thumb);
        renderDarkroom(randomFrom(photos));
    }
}

function renderDarkroom(photo) {
    darkroomCurrentPhoto = photo;
    const container = document.getElementById('darkroom-inner');
    container.innerHTML = '';

    // Main image area
    const imageArea = document.createElement('div');
    imageArea.className = 'darkroom-image-area';

    const img = document.createElement('img');
    img.className = 'darkroom-main-img';
    img.src = photo.display || photo.mobile || photo.thumb;
    img.alt = photo.alt || photo.caption || '';
    imageArea.appendChild(img);

    // Overlay layers
    if (darkroomLayers.colors && photo.palette) {
        const colorBar = document.createElement('div');
        colorBar.className = 'darkroom-layer darkroom-colors';
        for (const hex of photo.palette) {
            const swatch = document.createElement('div');
            swatch.className = 'darkroom-swatch';
            swatch.style.background = hex;
            colorBar.appendChild(swatch);
        }
        imageArea.appendChild(colorBar);
    }

    if (darkroomLayers.depth && photo.depth_complexity != null) {
        const depthLayer = document.createElement('div');
        depthLayer.className = 'darkroom-layer darkroom-depth-overlay';
        depthLayer.innerHTML = `
            <div class="darkroom-depth-bar">
                <div class="dd" style="width:${photo.near_pct || 0}%;background:var(--depth-near)">Near</div>
                <div class="dd" style="width:${photo.mid_pct || 0}%;background:var(--depth-mid)">Mid</div>
                <div class="dd" style="width:${photo.far_pct || 0}%;background:var(--depth-far)">Far</div>
            </div>
        `;
        imageArea.appendChild(depthLayer);
    }

    if (darkroomLayers.objects && photo.objects.length > 0) {
        const objLayer = document.createElement('div');
        objLayer.className = 'darkroom-layer darkroom-objects';
        for (const obj of photo.objects) {
            const pill = document.createElement('span');
            pill.className = 'glass-tag tag-scene';
            pill.textContent = titleCase(obj);
            objLayer.appendChild(pill);
        }
        imageArea.appendChild(objLayer);
    }

    if (darkroomLayers.faces && photo.face_count > 0) {
        const faceLayer = document.createElement('div');
        faceLayer.className = 'darkroom-layer darkroom-faces';
        const label = document.createElement('span');
        label.className = 'glass-tag tag-emotion';
        label.textContent = photo.face_count + ' face' + (photo.face_count > 1 ? 's' : '') +
            (photo.emotion ? ' \u2014 ' + titleCase(photo.emotion) : '');
        faceLayer.appendChild(label);
        imageArea.appendChild(faceLayer);
    }

    container.appendChild(imageArea);

    // Signal console
    const console_ = document.createElement('div');
    console_.className = 'darkroom-console';

    // Layer toggles
    const toggles = document.createElement('div');
    toggles.className = 'darkroom-toggles';
    const layerNames = [
        ['1', 'colors', 'Colors'],
        ['2', 'depth', 'Depth'],
        ['3', 'objects', 'Objects'],
        ['4', 'faces', 'Faces'],
        ['5', 'ocr', 'OCR'],
        ['6', 'meta', 'Meta'],
    ];
    for (const [key, layer, label] of layerNames) {
        const btn = document.createElement('button');
        btn.className = 'darkroom-toggle' + (darkroomLayers[layer] ? ' active' : '');
        btn.innerHTML = `<span class="darkroom-key">${key}</span> ${label}`;
        btn.addEventListener('click', () => {
            darkroomLayers[layer] = !darkroomLayers[layer];
            renderDarkroom(photo);
        });
        toggles.appendChild(btn);
    }

    const nextBtn = document.createElement('button');
    nextBtn.className = 'darkroom-toggle';
    nextBtn.innerHTML = '<span class="darkroom-key">N</span> Next';
    nextBtn.addEventListener('click', () => {
        const photos = APP.data.photos.filter(p => p.thumb);
        renderDarkroom(randomFrom(photos));
    });
    toggles.appendChild(nextBtn);

    console_.appendChild(toggles);

    // Meta info
    if (darkroomLayers.meta) {
        const metaGrid = document.createElement('div');
        metaGrid.className = 'darkroom-meta-grid';

        const fields = [
            ['Caption', photo.caption || photo.alt || '\u2014'],
            ['Camera', photo.camera || '\u2014'],
            ['Style', titleCase(photo.style) || '\u2014'],
            ['Scene', titleCase(photo.scene) || '\u2014'],
            ['Aesthetic', photo.aesthetic != null ? photo.aesthetic + '/10' : '\u2014'],
            ['Brightness', photo.brightness != null ? Math.round(photo.brightness) : '\u2014'],
            ['Contrast', photo.contrast != null ? photo.contrast + 'x' : '\u2014'],
            ['Depth', titleCase(photo.depth) || '\u2014'],
            ['Exposure', titleCase(photo.exposure) || '\u2014'],
            ['Composition', titleCase(photo.composition) || '\u2014'],
            ['Faces', photo.face_count || '0'],
            ['Objects', photo.object_count || '0'],
            ['Text', photo.has_text ? 'Yes' : 'No'],
            ['Vibes', (photo.vibes || []).map(v => titleCase(v)).join(', ') || '\u2014'],
        ];

        for (const [label, value] of fields) {
            const row = document.createElement('div');
            row.className = 'darkroom-meta-row';
            row.innerHTML = `<span class="darkroom-meta-label">${label}</span><span class="darkroom-meta-value">${value}</span>`;
            metaGrid.appendChild(row);
        }

        console_.appendChild(metaGrid);
    }

    container.appendChild(console_);
}
