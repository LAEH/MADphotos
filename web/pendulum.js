/* pendulum.js — Le Pendule: Original vs Enhanced taste test */

let pendulumInitialized = false;
let pendulumState = null;

function initPendulum() {
    if (pendulumInitialized) return;
    pendulumInitialized = true;

    const container = document.getElementById('view-pendulum');
    container.innerHTML = '';

    const wrap = document.createElement('div');
    wrap.className = 'pendulum-container';
    wrap.id = 'pendulum-inner';

    // Start screen
    const title = document.createElement('h2');
    title.className = 'game-title';
    title.textContent = 'Le Pendule';
    wrap.appendChild(title);

    const desc = document.createElement('p');
    desc.className = 'game-desc';
    desc.textContent = 'Two versions of the same photograph. Pick the one you prefer. Discover your taste.';
    wrap.appendChild(desc);

    const info = document.createElement('p');
    info.className = 'game-desc';
    info.style.color = 'var(--text-muted)';
    info.textContent = 'Coming soon — requires enhanced image variants to be synced to GCS.';
    wrap.appendChild(info);

    // For now, show a comparison between high/low aesthetic photos
    const startBtn = document.createElement('button');
    startBtn.className = 'game-start-btn';
    startBtn.textContent = 'Preview Mode';
    startBtn.addEventListener('click', startPendulumPreview);
    wrap.appendChild(startBtn);

    container.appendChild(wrap);
}

function startPendulumPreview() {
    // Preview: pick pairs of photos and ask which one the user prefers
    const photos = APP.data.photos.filter(p => p.thumb && p.aesthetic != null);
    if (photos.length < 40) return;

    pendulumState = {
        rounds: [],
        current: 0,
        choices: [],
    };

    // Generate 10 pairs: pick photos with different aesthetics
    const sorted = [...photos].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0));
    for (let i = 0; i < 10; i++) {
        const high = sorted[i * 5 + Math.floor(Math.random() * 5)];
        const low = sorted[sorted.length - 1 - i * 5 - Math.floor(Math.random() * 5)];
        if (high && low) {
            // Randomize order
            const pair = Math.random() > 0.5 ? [high, low] : [low, high];
            pendulumState.rounds.push(pair);
        }
    }

    renderPendulumRound();
}

function renderPendulumRound() {
    const container = document.getElementById('pendulum-inner');
    container.innerHTML = '';
    const ps = pendulumState;

    if (ps.current >= ps.rounds.length) {
        renderPendulumResults(container);
        return;
    }

    const [photoA, photoB] = ps.rounds[ps.current];

    const header = document.createElement('div');
    header.className = 'game-header';
    header.innerHTML = `<span class="game-round-num">Round ${ps.current + 1}/${ps.rounds.length}</span>`;
    container.appendChild(header);

    const question = document.createElement('p');
    question.className = 'pendulum-question';
    question.textContent = 'Which do you prefer?';
    container.appendChild(question);

    const pair = document.createElement('div');
    pair.className = 'pendulum-pair';

    for (const [idx, photo] of [photoA, photoB].entries()) {
        const card = document.createElement('div');
        card.className = 'pendulum-choice';

        const img = document.createElement('img');
        img.src = photo.mobile || photo.thumb;
        img.alt = '';
        card.appendChild(img);

        card.addEventListener('click', () => {
            ps.choices.push({ chosen: photo.id, other: idx === 0 ? photoB.id : photoA.id });
            ps.current++;
            renderPendulumRound();
        });

        pair.appendChild(card);
    }

    container.appendChild(pair);
}

function renderPendulumResults(container) {
    container.innerHTML = '';

    const end = document.createElement('div');
    end.className = 'game-end';

    const title = document.createElement('div');
    title.className = 'game-final-score';
    title.textContent = 'Your Taste';
    title.style.fontSize = '28px';
    end.appendChild(title);

    // Analyze choices
    let higherAestheticChosen = 0;
    for (const choice of pendulumState.choices) {
        const chosen = APP.photoMap[choice.chosen];
        const other = APP.photoMap[choice.other];
        if (chosen && other && (chosen.aesthetic || 0) > (other.aesthetic || 0)) {
            higherAestheticChosen++;
        }
    }

    const pct = Math.round(higherAestheticChosen / pendulumState.choices.length * 100);

    const result = document.createElement('p');
    result.className = 'game-desc';
    result.textContent = `You chose the higher-rated image ${pct}% of the time.`;
    end.appendChild(result);

    const taste = document.createElement('p');
    taste.className = 'game-desc';
    taste.style.color = 'var(--text)';
    if (pct > 70) {
        taste.textContent = 'You have a refined eye — you gravitate toward technically excellent images.';
    } else if (pct > 40) {
        taste.textContent = 'You balance technical quality with raw emotion. Interesting.';
    } else {
        taste.textContent = 'You prefer the unconventional. The imperfect. The surprising.';
    }
    end.appendChild(taste);

    const again = document.createElement('button');
    again.className = 'game-start-btn';
    again.textContent = 'Play Again';
    again.addEventListener('click', startPendulumPreview);
    end.appendChild(again);

    container.appendChild(end);
}
