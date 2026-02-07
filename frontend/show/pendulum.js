/* pendulum.js — Le Pendule: Original vs Enhanced taste test.
   Same photo shown twice — one original, one enhanced.
   Pick which you prefer. Discover your taste. */

let pendulumState = null;

function initPendulum() {
    startPendulum();
}

function startPendulum() {
    /* Filter to photos that have both original and enhanced versions */
    const eligible = APP.data.photos.filter(p =>
        p.thumb && (p.e_thumb || p.e_display) && (p.display || p.mobile)
    );
    if (eligible.length < 10) return;

    const pool = shuffleArray([...eligible]).slice(0, 10);

    pendulumState = {
        rounds: pool.map(photo => {
            /* Randomize left/right placement */
            const enhancedLeft = Math.random() > 0.5;
            return { photo, enhancedLeft };
        }),
        current: 0,
        choices: [], /* { photoId, choseEnhanced } */
    };

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

    const round = ps.rounds[ps.current];
    const photo = round.photo;

    const header = document.createElement('div');
    header.className = 'game-header';
    header.innerHTML = `<span class="game-round-num">Round ${ps.current + 1}/${ps.rounds.length}</span>`;
    container.appendChild(header);

    const question = document.createElement('p');
    question.className = 'pendulum-question';
    question.textContent = 'Which version do you prefer?';
    container.appendChild(question);

    const pair = document.createElement('div');
    pair.className = 'pendulum-pair';

    /* Original version */
    const originalSrc = photo.display || photo.mobile || photo.thumb;
    /* Enhanced version */
    const enhancedSrc = photo.e_display || photo.e_thumb;

    const sides = round.enhancedLeft
        ? [{ src: enhancedSrc, isEnhanced: true }, { src: originalSrc, isEnhanced: false }]
        : [{ src: originalSrc, isEnhanced: false }, { src: enhancedSrc, isEnhanced: true }];

    for (const side of sides) {
        const card = document.createElement('div');
        card.className = 'pendulum-choice';

        const img = document.createElement('img');
        img.className = 'img-loading';
        img.alt = '';
        const preload = new Image();
        preload.onload = () => {
            img.src = side.src;
            if (typeof revealImg === 'function') revealImg(img);
        };
        preload.src = side.src;
        card.appendChild(img);

        card.addEventListener('click', () => {
            ps.choices.push({ photoId: photo.id, choseEnhanced: side.isEnhanced });
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
    title.className = 'game-final-score pendulum-results-title';
    title.textContent = 'Your Taste';
    end.appendChild(title);

    const enhancedCount = pendulumState.choices.filter(c => c.choseEnhanced).length;
    const total = pendulumState.choices.length;
    const pct = Math.round(enhancedCount / total * 100);

    const score = document.createElement('div');
    score.className = 'game-final-score';
    score.style.fontSize = '48px';
    score.textContent = `${pct}%`;
    end.appendChild(score);

    const label = document.createElement('p');
    label.className = 'game-final-label';
    label.textContent = `Enhanced chosen ${enhancedCount} of ${total} times`;
    end.appendChild(label);

    const taste = document.createElement('p');
    taste.className = 'game-desc';
    taste.style.color = 'var(--text)';
    if (pct > 70) {
        taste.textContent = 'You prefer the polished version — you gravitate toward enhanced clarity and color.';
    } else if (pct > 40) {
        taste.textContent = 'You weigh both equally. Sometimes raw, sometimes refined.';
    } else {
        taste.textContent = 'You prefer the original capture. The unprocessed. The authentic.';
    }
    end.appendChild(taste);

    const again = document.createElement('button');
    again.className = 'game-start-btn';
    again.textContent = 'Play Again';
    again.addEventListener('click', startPendulum);
    end.appendChild(again);

    container.appendChild(end);
}
