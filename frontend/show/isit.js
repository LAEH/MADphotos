/* isit.js — Clean card swipe for photo curation.
   Two-card stack: next card always rendered underneath so swipe reveals instantly.
   rAF-throttled touch, compositor-only animations, 10-image preload buffer.
   Velocity-aware exit, spring-back, grab micro-interaction, eased overlays.

   Architecture fix: single clipping container (isit-image-wrap) owns
   border-radius + overflow:hidden + box-shadow. Card element is a pure
   transform target with NO overflow/radius/background. */

const ISIT_PRELOAD_AHEAD = 10;
const ISIT_SWIPE_THRESHOLD = 80;
const ISIT_ROTATION_FACTOR = 0.03;
const ISIT_GRAB_SCALE = 0.985;
const ISIT_MIN_EXIT_V = 0.8;

let isitState = {
  photos: [],
  index: 0,
  isMobile: false,
  hasTouch: false,
  hasHover: false,
  votes: {},
  animating: false,
  _keyHandler: null,
  _cache: {},
  labelsData: null,
};

/* ===== Viewport lock ===== */

function isitLockViewport() {
  document.documentElement.style.overflow = "hidden";
  document.body.style.overflow = "hidden";
  document.documentElement.style.position = "fixed";
  document.documentElement.style.inset = "0";
  document.documentElement.style.width = "100%";
}

function isitUnlockViewport() {
  document.body.classList.remove("picks-bg-reject", "picks-bg-accept");
  document.documentElement.style.overflow = "";
  document.body.style.overflow = "";
  document.documentElement.style.position = "";
  document.documentElement.style.inset = "";
  document.documentElement.style.width = "";
}

/* ===== Fullscreen ===== */

function isitEnterFullscreen() {
  const el = document.documentElement;
  if (el.requestFullscreen) el.requestFullscreen().catch(() => {});
  else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
}

/* ===== Init ===== */

function initIsit() {
  const container = document.getElementById("view-isit");
  if (!container || !APP.data) return;

  isitState.isMobile = window.innerWidth <= 768;
  isitState.hasTouch = "ontouchstart" in window;
  isitState.hasHover = window.matchMedia("(any-hover: hover)").matches;

  /* Load labels data (camera + unified labels) */
  const loadLabelsPromise = !isitState.labelsData
    ? fetch("data/photo_labels.json?v=" + Date.now())
        .then((r) => r.json())
        .then((data) => {
          isitState.labelsData = data;
        })
        .catch(() => {
          isitState.labelsData = {};
        })
    : Promise.resolve();

  try {
    isitState.votes = JSON.parse(
      localStorage.getItem("isit-votes") || "{}",
    );
  } catch {
    isitState.votes = {};
  }

  /* Hydrate with server-side votes so cross-device votes are reflected */
  if (APP.votedData) {
    let merged = 0;
    for (const [photo, vote] of Object.entries(APP.votedData)) {
      if (!isitState.votes[photo]) {
        isitState.votes[photo] = vote;
        merged++;
      }
    }
    if (merged > 0) {
      localStorage.setItem("isit-votes", JSON.stringify(isitState.votes));
    }
  }

  const orientation = isitState.isMobile ? "portrait" : "landscape";
  isitState.photos = shuffleArray(
    APP.allPhotos.filter(
      (p) => p.orientation === orientation && !isitState.votes[p.id],
    ),
  );
  isitState.index = 0;
  isitState.animating = false;
  isitState._cache = {};

  isitLockViewport();
  if (isitState.isMobile && !isitState.hasHover) isitEnterFullscreen();

  container.innerHTML = "";

  const wrapper = document.createElement("div");
  wrapper.className = "isit-container";

  const stack = document.createElement("div");
  stack.className = "isit-stack";
  stack.id = "isit-stack";

  const counter = document.createElement("div");
  counter.className = "isit-counter";
  counter.id = "isit-counter";

  const minimap = document.createElement("div");
  minimap.className = "isit-minimap";
  minimap.id = "isit-minimap";

  const subbar = document.createElement("div");
  subbar.className = "isit-subbar";
  subbar.appendChild(counter);
  subbar.appendChild(minimap);

  wrapper.appendChild(stack);
  wrapper.appendChild(subbar);
  container.appendChild(wrapper);

  if (isitState._keyHandler) {
    document.removeEventListener("keydown", isitState._keyHandler);
  }
  const keyHandler = (e) => {
    if (APP.currentView !== "isit") return;
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      voteIsit("reject");
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      voteIsit("accept");
    }
  };
  document.addEventListener("keydown", keyHandler);
  isitState._keyHandler = keyHandler;

  /* Wait for labels data to load before rendering */
  loadLabelsPromise.then(() => {
    isitPreloadBuffer();
    isitRenderStack();
    updateIsitCounter();
    renderIsitMinimap();
  });
}

function updateIsitCounter() {
  const el = document.getElementById("isit-counter");
  if (!el) return;
  const total = isitState.photos.length;
  const current = Math.min(isitState.index + 1, total);
  el.textContent = total === 0 ? "All done" : current + " / " + total;
}

/* ===== Preload buffer ===== */

function isitPreloadBuffer() {
  const tier = cardImageTier();
  const end = Math.min(
    isitState.index + 1 + ISIT_PRELOAD_AHEAD,
    isitState.photos.length,
  );
  for (let i = isitState.index + 1; i < end; i++) {
    const photo = isitState.photos[i];
    if (isitState._cache[photo.id]) continue;
    const src = photo[tier] || photo.mobile || photo.thumb;
    if (!src) continue;
    const img = new Image();
    img.decoding = "async";
    img.src = src;
    if (typeof img.decode === "function") {
      img
        .decode()
        .then(() => {
          if (isitState._cache[photo.id])
            isitState._cache[photo.id].decoded = true;
        })
        .catch(() => {});
    }
    isitState._cache[photo.id] = { src, img, decoded: false };
  }
}

/* ===== Two-card stack ===== */

function isitBuildCard(photo, isFront) {
  /* Card: pure transform target — NO overflow, NO border-radius, NO background */
  const card = document.createElement("div");
  card.className =
    "isit-card" + (isFront ? " isit-card-front" : " isit-card-back");
  card.dataset.photoId = photo.id;

  /* Image wrap: THE single clipping container.
     Owns border-radius, overflow:hidden, box-shadow.
     Everything visual lives inside here. */
  const wrap = document.createElement("div");
  wrap.className = "isit-image-wrap";


  const img = document.createElement("img");
  img.alt = photo.alt || photo.caption || "";
  img.draggable = false;
  if (photo.focus)
    img.style.objectPosition = photo.focus[0] + "% " + photo.focus[1] + "%";

  /* Thumb-first: show thumb immediately, upgrade to full-res when decoded */
  const cached = isitState._cache[photo.id];
  if (cached && cached.decoded) {
    img.src = cached.src;
  } else {
    if (photo.thumb) img.src = photo.thumb;

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
  if (isFront) img.fetchPriority = "high";

  wrap.appendChild(img);

  /* Hover zones on front card — INSIDE the wrap so they clip with the image */
  if (isFront && isitState.hasHover) {
    setupIsitHoverZones(wrap, card);
  }

  card.appendChild(wrap);

  /* Gorgeous pills — camera + top 4 unified labels on front card.
     Placed BELOW the wrap inside the card. Card has no overflow/radius,
     so pills display cleanly without any bleeding. */
  if (isFront && isitState.labelsData && isitState.labelsData[photo.id]) {
    const pillsContainer = isitCreatePills(photo);
    if (pillsContainer) card.appendChild(pillsContainer);
  }

  return card;
}

/* ===== Create gorgeous pills: camera + top 4 labels ===== */

function isitCreatePills(photo) {
  const data = isitState.labelsData[photo.id];
  if (!data) return null;

  const pills = [];

  if (data.camera) {
    pills.push({ text: data.camera, category: "camera", primary: true });
  }

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
  container.className = "isit-gorgeous-pills";

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

function setupIsitHoverZones(wrap, card) {
  const zoneReject = document.createElement("div");
  zoneReject.className = "isit-hover-zone isit-hover-left";
  const iconReject = document.createElement("div");
  iconReject.className = "isit-hover-icon isit-hover-icon-reject";
  iconReject.innerHTML =
    '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>';
  zoneReject.appendChild(iconReject);

  const zoneAccept = document.createElement("div");
  zoneAccept.className = "isit-hover-zone isit-hover-right";
  const iconAccept = document.createElement("div");
  iconAccept.className = "isit-hover-icon isit-hover-icon-accept";
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
    voteIsit("reject");
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
    voteIsit("accept");
  });

  /* Hover zones live INSIDE the wrap — clipped by its border-radius */
  wrap.appendChild(zoneReject);
  wrap.appendChild(zoneAccept);
}

function isitRenderStack() {
  const stack = document.getElementById("isit-stack");
  if (!stack) return;

  const idx = isitState.index;
  const photos = isitState.photos;

  if (idx >= photos.length) {
    stack.innerHTML =
      '<div class="isit-empty">No more photos to review</div>';
    updateIsitCounter();
    return;
  }

  stack.innerHTML = "";

  /* Back card (next photo) — rendered first, sits behind */
  if (idx + 1 < photos.length) {
    stack.appendChild(isitBuildCard(photos[idx + 1], false));
  }

  /* Front card (current photo) — on top */
  const front = isitBuildCard(photos[idx], true);
  stack.appendChild(front);

  if (isitState.hasTouch) {
    setupIsitSwipe(front);
  }

  isitPreloadBuffer();
}

/* After a vote animation completes, advance and rebuild the stack */
function isitAdvance() {
  isitState.index++;
  isitState.animating = false;

  const stack = document.getElementById("isit-stack");
  if (!stack) return;

  const idx = isitState.index;
  const photos = isitState.photos;

  if (idx >= photos.length) {
    stack.innerHTML =
      '<div class="isit-empty">No more photos to review</div>';
    updateIsitCounter();
    renderIsitMinimap();
    return;
  }

  /* Remove the old front card (already animated off-screen) */
  const oldFront = stack.querySelector(".isit-card-front");
  if (oldFront) oldFront.remove();

  /* Promote back card to front with smooth scale-up */
  const backCard = stack.querySelector(".isit-card-back");
  if (backCard) {
    backCard.classList.add("isit-card-promoting");
    backCard.classList.remove("isit-card-back");
    backCard.classList.add("isit-card-front");
    setTimeout(() => backCard.classList.remove("isit-card-promoting"), 320);
    if (isitState.hasTouch) setupIsitSwipe(backCard);
    if (isitState.hasHover) {
      const wrap = backCard.querySelector(".isit-image-wrap");
      if (wrap) setupIsitHoverZones(wrap, backCard);
    }
    /* Add pills to promoted card */
    const promotedPhoto = isitState.photos[idx];
    if (promotedPhoto && isitState.labelsData && isitState.labelsData[promotedPhoto.id]) {
      const pillsContainer = isitCreatePills(promotedPhoto);
      if (pillsContainer) backCard.appendChild(pillsContainer);
    }
  }

  /* Build new back card for the one after */
  if (idx + 1 < photos.length) {
    const newBack = isitBuildCard(photos[idx + 1], false);
    if (backCard) {
      stack.insertBefore(newBack, backCard);
    } else {
      stack.appendChild(newBack);
    }
  }

  isitPreloadBuffer();
  updateIsitCounter();
  renderIsitMinimap();
}

/* ===== Swipe ===== */

function setupIsitSwipe(card) {
  let startX = 0,
    startY = 0,
    deltaX = 0;
  let tracking = false,
    rafId = 0;
  let dirLocked = false,
    swipeDir = null;
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
      if (isitState.animating) return;
      startX = e.touches[0].clientX;
      startY = e.touches[0].clientY;
      deltaX = 0;
      tracking = true;
      dirLocked = false;
      swipeDir = null;
      vSamples = [{ x: startX, t: performance.now() }];
      card.style.transition = "none";
      card.style.transform =
        "translate3d(0,0,0) scale(" + ISIT_GRAB_SCALE + ")";
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

      const now = performance.now();
      vSamples.push({ x: cx, t: now });
      if (vSamples.length > 3) vSamples.shift();

      if (!rafId) {
        rafId = requestAnimationFrame(() => {
          rafId = 0;
          const rot = deltaX * ISIT_ROTATION_FACTOR;
          card.style.transform =
            "translate3d(" + deltaX + "px,0,0) rotate(" + rot + "deg)";
        });
      }
    },
    { passive: false },
  );

  function endTouch() {
    if (!tracking) return;
    resetSwipe();

    if (swipeDir === "h" && Math.abs(deltaX) > ISIT_SWIPE_THRESHOLD) {
      let vel = 0;
      if (vSamples.length >= 2) {
        const a = vSamples[0],
          b = vSamples[vSamples.length - 1];
        const dt = b.t - a.t;
        if (dt > 0) vel = Math.abs(b.x - a.x) / dt;
      }
      voteIsit(deltaX > 0 ? "accept" : "reject", vel);
    } else {
      card.style.transition = "transform .35s cubic-bezier(.175,.885,.32,1.1)";
      card.style.transform = "";
    }
  }

  card.addEventListener("touchend", endTouch, { passive: true });
  card.addEventListener("touchcancel", endTouch, { passive: true });
}

/* ===== Vote ===== */

function voteIsit(vote, swipeVelocity) {
  if (isitState.animating) return;
  if (isitState.index >= isitState.photos.length) return;

  isitState.animating = true;
  const photo = isitState.photos[isitState.index];
  const card = document.querySelector("#isit-stack .isit-card-front");

  isitState.votes[photo.id] = vote;
  try {
    localStorage.setItem("isit-votes", JSON.stringify(isitState.votes));
  } catch {}

  try {
    if (typeof db !== "undefined") {
      db.collection("isit-votes").add({
        photo: photo.id,
        vote: vote,
        device: isitState.isMobile ? "mobile" : "desktop",
        ts: firebase.firestore.FieldValue.serverTimestamp(),
      });
    }
  } catch (e) {}

  if (card) {
    const dir = vote === "accept" ? 1 : -1;
    const vel = Math.max(swipeVelocity || 0, ISIT_MIN_EXIT_V);
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

    let advanced = false;
    const onEnd = () => {
      if (advanced) return;
      advanced = true;
      card.removeEventListener("transitionend", onEnd);
      isitAdvance();
    };
    card.addEventListener("transitionend", onEnd);
    setTimeout(onEnd, dur * 1000 + 50);
  } else {
    isitAdvance();
  }
}

/* ===== Minimap ===== */

function renderIsitMinimap() {
  const el = document.getElementById("isit-minimap");
  if (!el) return;
  el.innerHTML = "";

  const idx = isitState.index;
  const photos = isitState.photos;
  const total = photos.length;
  if (total === 0) return;

  for (let i = idx - 3; i <= idx + 3; i++) {
    const slot = document.createElement("div");
    slot.className = "isit-mini-slot";

    if (i < 0 || i >= total) {
      slot.classList.add("isit-mini-empty");
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
      slot.classList.add("isit-mini-current");
    } else if (i < idx) {
      const v = isitState.votes[photo.id];
      const tint = document.createElement("div");
      tint.className = "isit-mini-tint";
      tint.classList.add(
        v === "accept" ? "isit-mini-accept" : "isit-mini-reject",
      );
      slot.appendChild(tint);
      slot.style.cursor = "pointer";
      slot.addEventListener("click", () => {
        if (isitState.animating) return;
        isitGoBack(i);
      });
    } else {
      slot.classList.add("isit-mini-future");
    }

    el.appendChild(slot);
  }
}

function isitGoBack(targetIndex) {
  const photo = isitState.photos[targetIndex];
  if (!photo) return;

  delete isitState.votes[photo.id];
  try {
    localStorage.setItem("isit-votes", JSON.stringify(isitState.votes));
  } catch {}

  isitState.index = targetIndex;
  isitState.animating = false;
  isitRenderStack();
  updateIsitCounter();
  renderIsitMinimap();
}
