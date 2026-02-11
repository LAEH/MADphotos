/* tinder.js — Mobile validation: swipe portrait (mobile) / landscape (desktop)
   Two-card stack: next card always rendered underneath so swipe reveals instantly.
   rAF-throttled touch, compositor-only animations, 10-image preload buffer.
   v2: velocity-aware exit, spring-back, grab micro-interaction, eased overlays. */

const TINDER_PRELOAD_AHEAD = 10;
const TINDER_SWIPE_THRESHOLD = 80;
const TINDER_ROTATION_FACTOR = 0.03; /* subtler than 0.04 — less mechanical */
const TINDER_GRAB_SCALE = 0.985; /* micro scale-down on touch */
const TINDER_MIN_EXIT_V = 0.8; /* px/ms — minimum exit velocity */

let tinderState = {
  photos: [],
  index: 0,
  isMobile: false /* screen ≤ 768px — controls orientation + image tier */,
  hasTouch: false /* touch device — controls swipe handlers */,
  hasHover: false /* cursor/trackpad — controls hover zones */,
  votes: {},
  animating: false,
  _keyHandler: null,
  _cache: {},
  gemmaData: null /* Gemma analysis data for tags */,
  labelsData: null /* Camera + unified labels data */,
};

/* ===== Viewport lock ===== */

function tinderLockViewport() {
  document.documentElement.style.overflow = "hidden";
  document.body.style.overflow = "hidden";
  document.documentElement.style.position = "fixed";
  document.documentElement.style.inset = "0";
  document.documentElement.style.width = "100%";
}

function tinderUnlockViewport() {
  document.body.classList.remove("picks-bg-reject", "picks-bg-accept");
  document.documentElement.style.overflow = "";
  document.body.style.overflow = "";
  document.documentElement.style.position = "";
  document.documentElement.style.inset = "";
  document.documentElement.style.width = "";
}

/* ===== Fullscreen ===== */

function tinderEnterFullscreen() {
  const el = document.documentElement;
  if (el.requestFullscreen) el.requestFullscreen().catch(() => {});
  else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
}

/* ===== Init ===== */

function initTinder() {
  const container = document.getElementById("view-tinder");
  if (!container || !APP.data) return;

  tinderState.isMobile = window.innerWidth <= 768;
  tinderState.hasTouch = "ontouchstart" in window;
  tinderState.hasHover = window.matchMedia("(any-hover: hover)").matches;

  /* Load labels data (camera + unified labels) - wait for it to complete */
  const loadLabelsPromise = !tinderState.labelsData
    ? fetch("data/photo_labels.json?v=" + Date.now())
        .then((r) => r.json())
        .then((data) => {
          tinderState.labelsData = data;
        })
        .catch(() => {
          tinderState.labelsData = {};
        })
    : Promise.resolve();

  try {
    tinderState.votes = JSON.parse(
      localStorage.getItem("tinder-votes") || "{}",
    );
  } catch {
    tinderState.votes = {};
  }

  /* Hydrate with server-side votes so cross-device votes are reflected */
  if (APP.votedData) {
    let merged = 0;
    for (const [photo, vote] of Object.entries(APP.votedData)) {
      if (!tinderState.votes[photo]) {
        tinderState.votes[photo] = vote;
        merged++;
      }
    }
    if (merged > 0) {
      localStorage.setItem("tinder-votes", JSON.stringify(tinderState.votes));
    }
  }

  const orientation = tinderState.isMobile ? "portrait" : "landscape";
  tinderState.photos = shuffleArray(
    APP.allPhotos.filter(
      (p) => p.orientation === orientation && !tinderState.votes[p.id],
    ),
  );
  tinderState.index = 0;
  tinderState.animating = false;
  tinderState._cache = {};

  tinderLockViewport();
  if (tinderState.isMobile && !tinderState.hasHover) tinderEnterFullscreen();

  container.innerHTML = "";

  const wrapper = document.createElement("div");
  wrapper.className = "tinder-container";

  const stack = document.createElement("div");
  stack.className = "tinder-stack";
  stack.id = "tinder-stack";

  const counter = document.createElement("div");
  counter.className = "tinder-counter";
  counter.id = "tinder-counter";

  const minimap = document.createElement("div");
  minimap.className = "tinder-minimap";
  minimap.id = "tinder-minimap";

  wrapper.appendChild(stack);
  wrapper.appendChild(counter);
  wrapper.appendChild(minimap);
  container.appendChild(wrapper);

  if (tinderState._keyHandler) {
    document.removeEventListener("keydown", tinderState._keyHandler);
  }
  const keyHandler = (e) => {
    if (APP.currentView !== "tinder") return;
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      voteTinder("reject");
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      voteTinder("accept");
    }
  };
  document.addEventListener("keydown", keyHandler);
  tinderState._keyHandler = keyHandler;

  /* Wait for labels data to load before rendering */
  loadLabelsPromise.then(() => {
    tinderPreloadBuffer();
    tinderRenderStack();
    updateTinderCounter();
    renderTinderMinimap();
  });
}

function updateTinderCounter() {
  const el = document.getElementById("tinder-counter");
  if (!el) return;
  const total = tinderState.photos.length;
  const current = Math.min(tinderState.index + 1, total);
  el.textContent = total === 0 ? "All done" : current + " / " + total;
}

/* ===== Preload buffer ===== */

function tinderPreloadBuffer() {
  const tier = cardImageTier();
  const end = Math.min(
    tinderState.index + 1 + TINDER_PRELOAD_AHEAD,
    tinderState.photos.length,
  );
  for (let i = tinderState.index + 1; i < end; i++) {
    const photo = tinderState.photos[i];
    if (tinderState._cache[photo.id]) continue;
    const src = photo[tier] || photo.mobile || photo.thumb;
    if (!src) continue;
    const img = new Image();
    img.decoding = "async";
    img.src = src;
    if (typeof img.decode === "function") {
      img
        .decode()
        .then(() => {
          if (tinderState._cache[photo.id])
            tinderState._cache[photo.id].decoded = true;
        })
        .catch(() => {});
    }
    tinderState._cache[photo.id] = { src, img, decoded: false };
  }
}

/* ===== Two-card stack ===== */
/* The stack always has two cards: back (next) underneath, front (current) on top.
   On swipe, the front flies away revealing the back instantly.
   Then we promote back→front and build a new back card. */

function tinderBuildCard(photo, isFront) {
  const card = document.createElement("div");
  card.className =
    "tinder-card" + (isFront ? " tinder-card-front" : " tinder-card-back");
  card.dataset.photoId = photo.id;

  /* Image Container: holds image + overlays, provides radius & clipping */
  const imageContainer = document.createElement("div");
  imageContainer.className = "tinder-image-container";

  const overlayAccept = document.createElement("div");
  overlayAccept.className = "tinder-overlay tinder-overlay-accept";
  const overlayReject = document.createElement("div");
  overlayReject.className = "tinder-overlay tinder-overlay-reject";
  imageContainer.appendChild(overlayAccept);
  imageContainer.appendChild(overlayReject);
  /* Removed background color to prevent "grey layer" bleeding */
  // if (photo.palette && photo.palette[0])
  //   imageContainer.style.backgroundColor = photo.palette[0] + "55";

  const img = document.createElement("img");
  img.alt = photo.alt || photo.caption || "";
  img.draggable = false;
  if (photo.focus)
    img.style.objectPosition = photo.focus[0] + "% " + photo.focus[1] + "%";

  /* Thumb-first: show thumb immediately (visible), upgrade to full-res when decoded.
       No opacity:0 / img-loading — the thumb IS the instant placeholder. */
  const cached = tinderState._cache[photo.id];
  if (cached && cached.decoded) {
    /* Full-res already decoded in preload buffer — use it directly */
    img.src = cached.src;
  } else {
    /* Show thumb immediately */
    if (photo.thumb) img.src = photo.thumb;

    /* Upgrade to full-res in background */
    const tier = cardImageTier();
    const fullSrc = cached
      ? cached.src
      : photo[tier] || photo.mobile || photo.thumb;
    if (fullSrc && fullSrc !== photo.thumb) {
      const pre = cached ? cached.img : new Image();
      if (!cached) {
        pre.decoding = "async";
        pre.src = fullSrc;
      }
      const doUpgrade = () => {
        if (img.isConnected !== false) img.src = fullSrc;
      };
      if (cached && cached.img && typeof cached.img.decode === "function") {
        cached.img.decode().then(doUpgrade).catch(doUpgrade);
      } else if (typeof pre.decode === "function") {
        pre.decode().then(doUpgrade).catch(doUpgrade);
      } else {
        pre.onload = doUpgrade;
      }
    }
  }
  /* Priority hint: front card loads first */
  if (isFront) img.fetchPriority = "high";

  imageContainer.appendChild(img);

  /* Wrap image container and pills in the content wrapper */
  const contentWrap = document.createElement("div");
  contentWrap.className = "tinder-card-content";
  contentWrap.appendChild(imageContainer);

  /* Gorgeous pills — camera + top 4 unified labels on front card */
  if (isFront && tinderState.labelsData && tinderState.labelsData[photo.id]) {
    const pillsContainer = createGorgeousPills(photo);
    if (pillsContainer) contentWrap.appendChild(pillsContainer);
  }

  card.appendChild(contentWrap);

  /* Hover zones on front card for any device with cursor/trackpad */
  if (isFront && tinderState.hasHover) {
    setupTinderHoverZones(card);
  }

  return card;
}

/* ===== Create gorgeous pills: camera + top 4 labels ===== */

function createGorgeousPills(photo) {
  // Debug: Force mock data if missing to verify UI
  const data = tinderState.labelsData[photo.id] || {
    camera: "Leica Debug",
    labels: [
      { label: "Contrast", category: "style" },
      { label: "Portrait", category: "technique" }
    ]
  };
  if (!data) return null;

  const pills = [];

  /* Pill 1: Camera (if available) */
  if (data.camera) {
    pills.push({ text: data.camera, category: "camera", primary: true });
  }

  /* Pills 2-5: Top 4 unified labels */
  if (data.labels && data.labels.length > 0) {
    data.labels.slice(0, 4).forEach((label) => {
      pills.push({
        text: label.label,
        category: label.category,
        primary: false,
      });
    });
  }

  if (pills.length === 0) return null;

  const container = document.createElement("div");
  container.className = "tinder-gorgeous-pills";

  pills.forEach((pill) => {
    const el = document.createElement("span");
    el.className = "gorgeous-pill" + (pill.primary ? " primary" : "");
    el.setAttribute("data-category", pill.category);
    el.textContent = pill.text.charAt(0).toUpperCase() + pill.text.slice(1);
    container.appendChild(el);
  });

  return container;
}

/* ===== Desktop hover zones ===== */

function setupTinderHoverZones(card) {
  const zoneReject = document.createElement("div");
  zoneReject.className = "tinder-hover-zone tinder-hover-left";
  const iconReject = document.createElement("div");
  iconReject.className = "tinder-hover-icon tinder-hover-icon-reject";
  iconReject.innerHTML =
    '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>';
  zoneReject.appendChild(iconReject);

  const zoneAccept = document.createElement("div");
  zoneAccept.className = "tinder-hover-zone tinder-hover-right";
  const iconAccept = document.createElement("div");
  iconAccept.className = "tinder-hover-icon tinder-hover-icon-accept";
  iconAccept.innerHTML =
    '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>';
  zoneAccept.appendChild(iconAccept);

  const body = document.body;
  function clearBgTint() {
    body.classList.remove("picks-bg-reject", "picks-bg-accept");
  }

  zoneReject.addEventListener("pointerenter", () => {
    zoneReject.classList.add("hovered");
    clearBgTint();
    body.classList.add("picks-bg-reject");
  });
  zoneReject.addEventListener("pointerleave", () => {
    zoneReject.classList.remove("hovered");
    clearBgTint();
  });
  zoneReject.addEventListener("click", (e) => {
    e.stopPropagation();
    zoneReject.classList.remove("hovered");
    clearBgTint();
    voteTinder("reject");
  });

  zoneAccept.addEventListener("pointerenter", () => {
    zoneAccept.classList.add("hovered");
    clearBgTint();
    body.classList.add("picks-bg-accept");
  });
  zoneAccept.addEventListener("pointerleave", () => {
    zoneAccept.classList.remove("hovered");
    clearBgTint();
  });
  zoneAccept.addEventListener("click", (e) => {
    e.stopPropagation();
    zoneAccept.classList.remove("hovered");
    clearBgTint();
    voteTinder("accept");
  });

  card.appendChild(zoneReject);
  card.appendChild(zoneAccept);
}

function tinderRenderStack() {
  const stack = document.getElementById("tinder-stack");
  if (!stack) return;

  const idx = tinderState.index;
  const photos = tinderState.photos;

  if (idx >= photos.length) {
    stack.innerHTML =
      '<div class="tinder-empty">No more photos to review</div>';

    updateTinderCounter();
    return;
  }

  stack.innerHTML = "";

  /* Back card (next photo) — rendered first, sits behind */
  if (idx + 1 < photos.length) {
    stack.appendChild(tinderBuildCard(photos[idx + 1], false));
  }

  /* Front card (current photo) — on top */
  const front = tinderBuildCard(photos[idx], true);
  stack.appendChild(front);

  if (tinderState.hasTouch) {
    const oa = front.querySelector(".tinder-overlay-accept");
    const or = front.querySelector(".tinder-overlay-reject");
    setupTinderSwipe(front, oa, or);
  }

  tinderPreloadBuffer();
}

/* After a vote animation completes, advance and rebuild the stack */
function tinderAdvance() {
  tinderState.index++;
  tinderState.animating = false;

  const stack = document.getElementById("tinder-stack");
  if (!stack) return;

  const idx = tinderState.index;
  const photos = tinderState.photos;

  if (idx >= photos.length) {
    stack.innerHTML =
      '<div class="tinder-empty">No more photos to review</div>';

    updateTinderCounter();
    renderTinderMinimap();
    return;
  }

  /* Remove the old front card (already animated off-screen) */
  const oldFront = stack.querySelector(".tinder-card-front");
  if (oldFront) oldFront.remove();

  /* Promote back card to front with smooth scale-up */
  const backCard = stack.querySelector(".tinder-card-back");
  if (backCard) {
    /* Enable transition for the promotion scale-up (0.97 → 1.0) */
    backCard.classList.add("tinder-card-promoting");
    backCard.classList.remove("tinder-card-back");
    backCard.classList.add("tinder-card-front");
    /* Remove promotion class after transition completes (280ms + margin) */
    setTimeout(() => backCard.classList.remove("tinder-card-promoting"), 320);
    const oa = backCard.querySelector(".tinder-overlay-accept");
    const or = backCard.querySelector(".tinder-overlay-reject");
    if (tinderState.hasTouch) setupTinderSwipe(backCard, oa, or);
    if (tinderState.hasHover) setupTinderHoverZones(backCard);
  }

  /* Build new back card for the one after */
  if (idx + 1 < photos.length) {
    const newBack = tinderBuildCard(photos[idx + 1], false);
    /* Insert before the front card so it renders behind */
    if (backCard) {
      stack.insertBefore(newBack, backCard);
    } else {
      stack.appendChild(newBack);
    }
  }

  tinderPreloadBuffer();
  updateTinderCounter();
  renderTinderMinimap();
}

/* ===== Swipe ===== */

function setupTinderSwipe(card, overlayAccept, overlayReject) {
  let startX = 0,
    startY = 0,
    deltaX = 0;
  let tracking = false,
    rafId = 0;
  let dirLocked = false,
    swipeDir = null;
  /* Velocity tracking: last 3 move samples */
  let vSamples = [];

  function resetSwipe() {
    tracking = false;
    if (rafId) {
      cancelAnimationFrame(rafId);
      rafId = 0;
    }
  }

  card.addEventListener(
    "touchstart",
    (e) => {
      if (tinderState.animating) return;
      startX = e.touches[0].clientX;
      startY = e.touches[0].clientY;
      deltaX = 0;
      tracking = true;
      dirLocked = false;
      swipeDir = null;
      vSamples = [{ x: startX, t: performance.now() }];
      card.style.transition = "none";
      overlayAccept.style.transition = "none";
      overlayReject.style.transition = "none";
      /* Micro grab feedback — tiny scale-down */
      card.style.transform =
        "translate3d(0,0,0) scale(" + TINDER_GRAB_SCALE + ")";
    },
    { passive: false },
  );

  card.addEventListener(
    "touchmove",
    (e) => {
      if (!tracking) return;
      const cx = e.touches[0].clientX;
      const dx = cx - startX;
      const dy = e.touches[0].clientY - startY;

      if (!dirLocked && (Math.abs(dx) > 8 || Math.abs(dy) > 8)) {
        dirLocked = true;
        swipeDir = Math.abs(dx) >= Math.abs(dy) ? "h" : "v";
      }
      if (swipeDir === "v") return;
      e.preventDefault();
      deltaX = dx;

      /* Keep last 3 samples for velocity calc */
      const now = performance.now();
      vSamples.push({ x: cx, t: now });
      if (vSamples.length > 3) vSamples.shift();

      if (!rafId) {
        rafId = requestAnimationFrame(() => {
          rafId = 0;
          const rot = deltaX * TINDER_ROTATION_FACTOR;
          card.style.transform =
            "translate3d(" + deltaX + "px,0,0) rotate(" + rot + "deg)";
          /* Eased overlay: quadratic ramp — feels more intentional */
          const t = Math.min(Math.abs(deltaX) / 160, 1);
          const intensity = t * t * 0.5;
          if (deltaX > 0) {
            overlayAccept.style.opacity = intensity;
            overlayReject.style.opacity = "0";
          } else {
            overlayReject.style.opacity = intensity;
            overlayAccept.style.opacity = "0";
          }
        });
      }
    },
    { passive: false },
  );

  function endTouch() {
    if (!tracking) return;
    resetSwipe();

    if (swipeDir === "h" && Math.abs(deltaX) > TINDER_SWIPE_THRESHOLD) {
      /* Calculate exit velocity from last samples */
      let vel = 0;
      if (vSamples.length >= 2) {
        const a = vSamples[0],
          b = vSamples[vSamples.length - 1];
        const dt = b.t - a.t;
        if (dt > 0) vel = Math.abs(b.x - a.x) / dt; /* px/ms */
      }
      voteTinder(deltaX > 0 ? "accept" : "reject", vel);
    } else {
      /* Spring back — custom spring curve */
      card.style.transition = "transform .35s cubic-bezier(.175,.885,.32,1.1)";
      overlayAccept.style.transition = "opacity .25s ease-out";
      overlayReject.style.transition = "opacity .25s ease-out";
      card.style.transform = "";
      overlayAccept.style.opacity = "0";
      overlayReject.style.opacity = "0";
    }
  }

  card.addEventListener("touchend", endTouch, { passive: true });
  card.addEventListener("touchcancel", endTouch, { passive: true });
}

/* ===== Vote ===== */

function voteTinder(vote, swipeVelocity) {
  if (tinderState.animating) return;
  if (tinderState.index >= tinderState.photos.length) return;

  tinderState.animating = true;
  const photo = tinderState.photos[tinderState.index];
  const card = document.querySelector("#tinder-stack .tinder-card-front");

  tinderState.votes[photo.id] = vote;
  try {
    localStorage.setItem("tinder-votes", JSON.stringify(tinderState.votes));
  } catch {}

  try {
    if (typeof db !== "undefined") {
      db.collection("tinder-votes").add({
        photo: photo.id,
        vote: vote,
        device: tinderState.isMobile ? "mobile" : "desktop",
        ts: firebase.firestore.FieldValue.serverTimestamp(),
      });
    }
  } catch (e) {}

  if (card) {
    const dir = vote === "accept" ? 1 : -1;
    const ov = card.querySelector(
      vote === "accept" ? ".tinder-overlay-accept" : ".tinder-overlay-reject",
    );
    if (ov) {
      ov.style.transition = "none";
      ov.style.opacity = "0.4";
    }

    /* Velocity-aware exit: faster swipes fly farther and faster */
    const vel = Math.max(swipeVelocity || 0, TINDER_MIN_EXIT_V);
    const dist = Math.min(180 + vel * 250, 500);
    const dur = Math.max(0.15, Math.min(0.32, 180 / (vel * 1000)));
    const rot = dir * Math.min(8 + vel * 6, 18);

    card.style.transition =
      "transform " +
      dur +
      "s cubic-bezier(.2,.6,.3,1), opacity " +
      dur +
      "s ease-out";
    card.style.transform =
      "translate3d(" + dir * dist + "px,0,0) rotate(" + rot + "deg)";
    card.style.opacity = "0";
    card.style.pointerEvents = "none";

    /* Use transitionend for precise timing instead of setTimeout */
    let advanced = false;
    const onEnd = () => {
      if (advanced) return;
      advanced = true;
      card.removeEventListener("transitionend", onEnd);
      tinderAdvance();
    };
    card.addEventListener("transitionend", onEnd);
    /* Safety fallback in case transitionend doesn't fire (iOS edge case) */
    setTimeout(onEnd, dur * 1000 + 50);
  } else {
    tinderAdvance();
  }
}

/* ===== Minimap ===== */

function renderTinderMinimap() {
  const el = document.getElementById("tinder-minimap");
  if (!el) return;
  el.innerHTML = "";

  const idx = tinderState.index;
  const photos = tinderState.photos;
  const total = photos.length;
  if (total === 0) return;

  for (let i = idx - 3; i <= idx + 3; i++) {
    const slot = document.createElement("div");
    slot.className = "tinder-mini-slot";

    if (i < 0 || i >= total) {
      slot.classList.add("tinder-mini-empty");
      el.appendChild(slot);
      continue;
    }

    const photo = photos[i];
    const img = document.createElement("img");
    img.draggable = false;
    const src = photo.thumb || photo.mobile || "";
    if (src) img.src = src;
    if (photo.focus)
      img.style.objectPosition = photo.focus[0] + "% " + photo.focus[1] + "%";
    slot.appendChild(img);

    if (i === idx) {
      slot.classList.add("tinder-mini-current");
    } else if (i < idx) {
      const vote = tinderState.votes[photo.id];
      const tint = document.createElement("div");
      tint.className = "tinder-mini-tint";
      tint.classList.add(
        vote === "accept" ? "tinder-mini-accept" : "tinder-mini-reject",
      );
      slot.appendChild(tint);
      slot.style.cursor = "pointer";
      slot.addEventListener("click", () => {
        if (tinderState.animating) return;
        tinderGoBack(i);
      });
    } else {
      slot.classList.add("tinder-mini-future");
    }

    el.appendChild(slot);
  }
}

function tinderGoBack(targetIndex) {
  const photo = tinderState.photos[targetIndex];
  if (!photo) return;

  delete tinderState.votes[photo.id];
  try {
    localStorage.setItem("tinder-votes", JSON.stringify(tinderState.votes));
  } catch {}

  tinderState.index = targetIndex;
  tinderState.animating = false;
  tinderRenderStack();
  updateTinderCounter();
  renderTinderMinimap();
}
