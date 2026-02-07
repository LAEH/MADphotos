/* game.js — Le Terrain de Jeu: The connection game */

let gameState = null;

function initGame() {
    const container = document.getElementById('view-game');
    container.innerHTML = '<div class="loading">Loading game rounds</div>';

    loadGameRounds().then(() => {
        renderGameStart(container);
    });
}

function renderGameStart(container) {
    container.innerHTML = '';

    const wrap = document.createElement('div');
    wrap.className = 'game-container';
    wrap.id = 'game-inner';

    const title = document.createElement('h2');
    title.className = 'game-title';
    title.textContent = 'Le Terrain de Jeu';
    wrap.appendChild(title);

    const desc = document.createElement('p');
    desc.className = 'game-desc';
    desc.textContent = 'Two photographs share a hidden connection. Find it before time runs out.';
    wrap.appendChild(desc);

    const startBtn = document.createElement('button');
    startBtn.className = 'game-start-btn';
    startBtn.textContent = 'Start';
    startBtn.addEventListener('click', startGame);
    wrap.appendChild(startBtn);

    container.appendChild(wrap);
}

function startGame() {
    const rounds = APP.gameRounds || [];
    if (rounds.length === 0) {
        alert('No game rounds available. Run export_gallery_data.py first.');
        return;
    }

    gameState = {
        rounds: shuffleArray([...rounds]).slice(0, 20),
        current: 0,
        score: 0,
        streak: 0,
        maxStreak: 0,
        rafId: null,
        timerStart: 0,
        timerDuration: 8000, /* ms */
        answered: false,
    };

    renderRound();
}

function renderRound() {
    const container = document.getElementById('game-inner');
    container.innerHTML = '';

    const gs = gameState;
    if (gs.current >= gs.rounds.length) {
        renderGameEnd(container);
        return;
    }

    const round = gs.rounds[gs.current];
    const photoA = APP.photoMap[round.a];
    const photoB = APP.photoMap[round.b];

    if (!photoA || !photoB) {
        gs.current++;
        renderRound();
        return;
    }

    /* Header: round counter + score + streak */
    const header = document.createElement('div');
    header.className = 'game-header';
    header.innerHTML = `
        <span class="game-round-num">Round ${gs.current + 1}/${gs.rounds.length}</span>
        <span class="game-score">Score: ${gs.score}</span>
        <span class="game-streak">${gs.streak > 1 ? gs.streak + 'x streak' : ''}</span>
    `;
    container.appendChild(header);

    /* Timer bar — animated via rAF for 60fps */
    const timerBar = document.createElement('div');
    timerBar.className = 'game-timer-bar';
    const timerFill = document.createElement('div');
    timerFill.className = 'game-timer-fill';
    timerFill.id = 'game-timer-fill';
    timerBar.appendChild(timerFill);
    container.appendChild(timerBar);

    /* Two images side by side */
    const pair = document.createElement('div');
    pair.className = 'game-pair';

    for (const photo of [photoA, photoB]) {
        const card = document.createElement('div');
        card.className = 'game-photo-card';
        const img = document.createElement('img');
        loadProgressive(img, photo, 'mobile');
        img.alt = '';
        card.appendChild(img);
        pair.appendChild(card);
    }
    container.appendChild(pair);

    /* Question */
    const question = document.createElement('p');
    question.className = 'game-question';
    question.textContent = 'What do these photographs have in common?';
    container.appendChild(question);

    /* Answer buttons: 1 correct + 5 wrong, shuffled */
    const answers = shuffleArray([
        { text: round.answer, correct: true },
        ...round.wrong.slice(0, 5).map(w => ({ text: w, correct: false })),
    ]);

    const grid = document.createElement('div');
    grid.className = 'game-answers';

    for (const ans of answers) {
        const btn = document.createElement('button');
        btn.className = 'game-answer-btn';
        btn.textContent = titleCase(ans.text);
        btn.addEventListener('click', () => handleAnswer(btn, ans.correct, round.answer, grid));
        grid.appendChild(btn);
    }
    container.appendChild(grid);

    /* Start rAF timer */
    gs.answered = false;
    gs.timerStart = performance.now();

    function tickTimer(now) {
        if (gs.answered) return;

        const elapsed = now - gs.timerStart;
        const remaining = Math.max(0, 1 - elapsed / gs.timerDuration);
        const fill = document.getElementById('game-timer-fill');
        if (fill) fill.style.width = (remaining * 100) + '%';

        if (remaining <= 0) {
            /* Time's up */
            gs.streak = 0;
            gs.answered = true;
            highlightCorrect(grid, round.answer);
            grid.querySelectorAll('.game-answer-btn').forEach(b => b.disabled = true);
            setTimeout(() => { gs.current++; renderRound(); }, 1500);
            return;
        }

        gs.rafId = requestAnimationFrame(tickTimer);
    }

    gs.rafId = requestAnimationFrame(tickTimer);
    registerTimer(gs.rafId);
}

function handleAnswer(btn, correct, correctAnswer, grid) {
    const gs = gameState;
    if (gs.answered) return;
    gs.answered = true;

    /* Cancel timer animation */
    if (gs.rafId) cancelAnimationFrame(gs.rafId);

    /* Disable all buttons */
    grid.querySelectorAll('.game-answer-btn').forEach(b => b.disabled = true);

    if (correct) {
        btn.classList.add('correct');
        const elapsed = performance.now() - gs.timerStart;
        const timeLeft = Math.max(0, gs.timerDuration - elapsed) / 1000;
        const points = Math.ceil(timeLeft) * (gs.streak + 1);
        gs.score += points;
        gs.streak++;
        gs.maxStreak = Math.max(gs.maxStreak, gs.streak);
    } else {
        btn.classList.add('wrong');
        gs.streak = 0;
        highlightCorrect(grid, correctAnswer);
    }

    setTimeout(() => { gs.current++; renderRound(); }, 1500);
}

function highlightCorrect(grid, answer) {
    grid.querySelectorAll('.game-answer-btn').forEach(b => {
        if (b.textContent === titleCase(answer)) {
            b.classList.add('correct');
        }
    });
}

function renderGameEnd(container) {
    container.innerHTML = '';

    const end = document.createElement('div');
    end.className = 'game-end';

    const scoreEl = document.createElement('div');
    scoreEl.className = 'game-final-score';
    scoreEl.textContent = gameState.score;
    end.appendChild(scoreEl);

    const label = document.createElement('div');
    label.className = 'game-final-label';
    label.textContent = 'points';
    end.appendChild(label);

    const stats = document.createElement('div');
    stats.className = 'game-stats';
    stats.innerHTML = `
        <div>Best streak: ${gameState.maxStreak}x</div>
        <div>Rounds: ${gameState.rounds.length}</div>
    `;
    end.appendChild(stats);

    const again = document.createElement('button');
    again.className = 'game-start-btn';
    again.textContent = 'Play Again';
    again.addEventListener('click', startGame);
    end.appendChild(again);

    container.appendChild(end);
}
