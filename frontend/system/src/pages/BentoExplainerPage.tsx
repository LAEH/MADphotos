import { PageShell } from '../components/layout/PageShell'
import { Card } from '../components/layout/Card'
import type { CSSProperties } from 'react'

/* ===== ASCII grid renderer ===== */

interface Cell { r: number; c: number; rs: number; cs: number; orient: 'P' | 'L'; label?: string }

function AsciiGrid({ cols, rows, cells, unit = 28 }: { cols: number; rows: number; cells: Cell[]; unit?: number }) {
  const gap = 2
  const w = cols * unit + (cols - 1) * gap
  const h = rows * unit + (rows - 1) * gap
  const colors: Record<string, string> = {
    P: '#6366f1', L: '#06b6d4', S: '#10b981',
  }
  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: '100%', maxWidth: w * 1.5, display: 'block' }}>
      {cells.map((cell, i) => {
        const x = (cell.c - 1) * (unit + gap)
        const y = (cell.r - 1) * (unit + gap)
        const cw = cell.cs * unit + (cell.cs - 1) * gap
        const ch = cell.rs * unit + (cell.rs - 1) * gap
        const ratio = cell.cs / cell.rs
        const fill = ratio < 1 ? colors.P : ratio === 1 ? colors.S : colors.L
        const label = cell.label || `${cell.cs}:${cell.rs}`
        return (
          <g key={i}>
            <rect x={x} y={y} width={cw} height={ch} rx={3}
              fill={fill} opacity={0.18} stroke={fill} strokeWidth={1.2} />
            <text x={x + cw / 2} y={y + ch / 2} textAnchor="middle" dominantBaseline="central"
              fill={fill} fontSize={Math.min(10, unit * 0.4)} fontFamily="monospace" fontWeight={600}>
              {label}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

/* ===== Ratio table ===== */

const RATIOS: { ratio: string; wh: string; spans: string; orient: string; crop: string }[] = [
  { ratio: '1/2', wh: '1:2', spans: '2x1', orient: 'Portrait', crop: '2:3' },
  { ratio: '2/3', wh: '2:3', spans: '3x2', orient: 'Portrait', crop: '2:3' },
  { ratio: '3/4', wh: '3:4', spans: '4x3', orient: 'Portrait', crop: '2:3' },
  { ratio: '1', wh: '1:1', spans: '1x1, 2x2, 3x3', orient: 'Square', crop: '1:1' },
  { ratio: '4/3', wh: '4:3', spans: '3x4', orient: 'Landscape', crop: '3:2' },
  { ratio: '3/2', wh: '3:2', spans: '2x3', orient: 'Landscape', crop: '3:2' },
  { ratio: '2/1', wh: '2:1', spans: '1x2', orient: 'Landscape', crop: '16:9' },
]

/* ===== Layout catalog ===== */

interface LayoutDef { id: string; tiles: number; desc: string; cells: Cell[] }

const desktopLayouts: LayoutDef[] = [
  { id: 'D1', tiles: 8, desc: 'Hero — big 3:2 top-left, portrait, strip bottom', cells: [
    { r:1,c:1,rs:2,cs:3,orient:'L' },{ r:1,c:4,rs:2,cs:1,orient:'P' },{ r:1,c:5,rs:1,cs:1,orient:'L' },
    { r:2,c:5,rs:1,cs:1,orient:'L' },{ r:3,c:1,rs:1,cs:1,orient:'L' },{ r:3,c:2,rs:1,cs:2,orient:'L' },
    { r:3,c:4,rs:1,cs:1,orient:'L' },{ r:3,c:5,rs:1,cs:1,orient:'L' },
  ]},
  { id: 'D2', tiles: 6, desc: 'Balanced — two squares + portrait top, wides bottom', cells: [
    { r:1,c:1,rs:2,cs:2,orient:'L' },{ r:1,c:3,rs:2,cs:1,orient:'P' },{ r:1,c:4,rs:2,cs:2,orient:'L' },
    { r:3,c:1,rs:1,cs:2,orient:'L' },{ r:3,c:3,rs:1,cs:1,orient:'L' },{ r:3,c:4,rs:1,cs:2,orient:'L' },
  ]},
  { id: 'D4', tiles: 5, desc: 'Bold — two big blocks top, wide strip bottom', cells: [
    { r:1,c:1,rs:2,cs:3,orient:'L' },{ r:1,c:4,rs:2,cs:2,orient:'L' },
    { r:3,c:1,rs:1,cs:2,orient:'L' },{ r:3,c:3,rs:1,cs:2,orient:'L' },{ r:3,c:5,rs:1,cs:1,orient:'L' },
  ]},
  { id: 'D5', tiles: 10, desc: 'Portrait wall — alternating portraits + squares', cells: [
    { r:1,c:1,rs:2,cs:1,orient:'P' },{ r:1,c:2,rs:1,cs:1,orient:'L' },{ r:1,c:3,rs:2,cs:1,orient:'P' },
    { r:1,c:4,rs:1,cs:1,orient:'L' },{ r:1,c:5,rs:2,cs:1,orient:'P' },{ r:2,c:2,rs:1,cs:1,orient:'L' },
    { r:2,c:4,rs:1,cs:1,orient:'L' },{ r:3,c:1,rs:1,cs:2,orient:'L' },{ r:3,c:3,rs:1,cs:1,orient:'L' },
    { r:3,c:4,rs:1,cs:2,orient:'L' },
  ]},
  { id: 'D8', tiles: 5, desc: 'Cinema — massive 3x3 square hero', cells: [
    { r:1,c:1,rs:3,cs:3,orient:'L' },{ r:1,c:4,rs:2,cs:1,orient:'P' },{ r:1,c:5,rs:1,cs:1,orient:'L' },
    { r:2,c:5,rs:1,cs:1,orient:'L' },{ r:3,c:4,rs:1,cs:2,orient:'L' },
  ]},
  { id: 'D10', tiles: 3, desc: 'Widescreen — massive 4:3 hero + side column', cells: [
    { r:1,c:1,rs:3,cs:4,orient:'L' },{ r:1,c:5,rs:2,cs:1,orient:'P' },{ r:3,c:5,rs:1,cs:1,orient:'L' },
  ]},
]

const mobileLayouts: LayoutDef[] = [
  { id: 'M1', tiles: 6, desc: 'Blocks — alternating square + portrait rows', cells: [
    { r:1,c:1,rs:2,cs:2,orient:'L' },{ r:1,c:3,rs:2,cs:1,orient:'P' },
    { r:3,c:1,rs:2,cs:1,orient:'P' },{ r:3,c:2,rs:2,cs:2,orient:'L' },
    { r:5,c:1,rs:2,cs:2,orient:'L' },{ r:5,c:3,rs:2,cs:1,orient:'P' },
  ]},
  { id: 'M3', tiles: 7, desc: 'Mixed — sq+p, 3 portraits, p+sq', cells: [
    { r:1,c:1,rs:2,cs:2,orient:'L' },{ r:1,c:3,rs:2,cs:1,orient:'P' },
    { r:3,c:1,rs:2,cs:1,orient:'P' },{ r:3,c:2,rs:2,cs:1,orient:'P' },{ r:3,c:3,rs:2,cs:1,orient:'P' },
    { r:5,c:1,rs:2,cs:1,orient:'P' },{ r:5,c:2,rs:2,cs:2,orient:'L' },
  ]},
  { id: 'M5', tiles: 5, desc: 'Drama — full-width 3:2 top, blocks below', cells: [
    { r:1,c:1,rs:2,cs:3,orient:'L' },
    { r:3,c:1,rs:2,cs:1,orient:'P' },{ r:3,c:2,rs:2,cs:2,orient:'L' },
    { r:5,c:1,rs:2,cs:2,orient:'L' },{ r:5,c:3,rs:2,cs:1,orient:'P' },
  ]},
]

/* ===== Curators ===== */

const CURATORS = [
  { name: 'Hero Story', desc: 'Picks a dominant hero photo with high visual weight, surrounds it with complementary court photos sharing hue harmony.', weight: 2, signals: 'gc_weight, hue, visualImpact' },
  { name: 'Temperature Harmony', desc: 'Groups photos by color temperature — warm (molten/warm), cool (glacial/cool), or mono. Builds a cohesive thermal palette.', weight: 1, signals: 'gc_temp, hue' },
  { name: 'Color Story', desc: 'Clusters photos within a tight hue range (±35°). Creates monochromatic color harmonies with luminance variation.', weight: 2, signals: 'hue, palette, brightness' },
  { name: 'Mood Board', desc: 'Matches photos sharing the same Gemini vibe. All tiles feel emotionally coherent — serene, dramatic, playful, etc.', weight: 1, signals: 'vibes[]' },
  { name: 'Scene Story', desc: 'Groups by scene classification — street, nature, architecture. Location-coherent compositions.', weight: 1, signals: 'scene' },
  { name: 'Depth Journey', desc: 'Contrasts near/far depth distribution. Near-dominant photos in big cells, deep-field in small ones.', weight: 1, signals: 'depth, depth_complexity' },
  { name: 'Mono + Accent', desc: 'B&W dominant set with 1-2 color accent photos. The accent photo gets a large cell.', weight: 1, signals: 'mono, hue, contrast' },
  { name: 'Archetype Exhibition', desc: 'Groups by compositional archetype — portal, horizon, texture, figure, geometry, void, etc.', weight: 1, signals: 'gc_archetype' },
  { name: 'Camera Story', desc: 'All tiles from the same camera body. Shows the character of each sensor/lens combo.', weight: 1, signals: 'camera' },
  { name: 'Night Vision', desc: 'Dark, dramatic photos. Low brightness, high contrast, urban or nocturnal scenes.', weight: 1, signals: 'brightness, contrast, scene' },
  { name: 'Golden Hour', desc: 'Warm-toned photos in golden/sunset/sunrise light. High saturation, warm hue range.', weight: 1, signals: 'time, hue, gc_temp' },
  { name: 'Face Gallery', desc: 'People-focused: only photos with detected faces. Rewards face count and face area.', weight: 1, signals: 'face_count' },
  { name: 'Style Contrast', desc: 'Juxtaposes film grain vs digital clarity. Alternates between analog and digital captures.', weight: 1, signals: 'style' },
  { name: 'Brightness Gradient', desc: 'Arranges photos from dark to light across the grid. Creates a luminance sweep effect.', weight: 1, signals: 'brightness' },
  { name: 'Energy Flow', desc: 'Groups by visual energy direction — diagonal, radial, horizontal. All tiles share a kinetic rhythm.', weight: 2, signals: 'gc_energy' },
  { name: 'Semantic Pops', desc: 'Photos sharing striking color-object combos from Gemini analysis (e.g., "red umbrella", "neon sign").', weight: 1, signals: 'gemma_pops[]' },
  { name: 'Print Worthy', desc: 'Gemma\'s museum-quality picks. Only photos flagged as print_worthy get selected.', weight: 2, signals: 'print_worthy' },
  { name: 'Gemma Vibes', desc: 'Deep thematic matching using Gemma\'s rich vocabulary — nostalgic, gritty, ethereal, confrontational.', weight: 2, signals: 'gemma_vibes[]' },
  { name: 'Subject Gallery', desc: 'Shared subject keyword clusters from Gemma descriptions. Groups photos depicting the same subject.', weight: 1, signals: 'gemma_subject, gemma_tags' },
  { name: 'Sharpness Showcase', desc: 'Groups by visual texture — razor sharp, soft/dreamy, or motion blur. Celebrates each style.', weight: 1, signals: 'gemma_sharpness' },
]

/* ===== Split patterns ===== */

const SPLIT_EXAMPLES: { from: string; to: string; desc: string }[] = [
  { from: '2x2 (1:1)', to: '4x 1x1', desc: '4 squares' },
  { from: '2x2 (1:1)', to: '2x 2x1', desc: '2 portraits (1/2)' },
  { from: '2x2 (1:1)', to: '2x 1x2', desc: '2 wides (2/1)' },
  { from: '2x3 (3/2)', to: '2x2 + 2x1', desc: 'square + portrait' },
  { from: '3x2 (2/3)', to: '2x2 + 1x2', desc: 'square + wide' },
  { from: '3x3 (1:1)', to: '2x2 + 2x1 + 1x2 + 1x1', desc: 'sq + portrait + wide + sq' },
  { from: '2x1 (1/2)', to: '2x 1x1', desc: '2 squares' },
  { from: '1x2 (2/1)', to: '2x 1x1', desc: '2 squares' },
]

/* ===== Page ===== */

export function BentoExplainerPage() {
  return (
    <PageShell title="Bento Algorithm" subtitle="Geometry, selection, and image population">

      {/* 1. Overview */}
      <Card title="How it works">
        <p style={prose}>
          Every bento is a <b>fixed-screen composition</b> — no scrolling. A grid of tiles fills the viewport exactly,
          each tile containing one photograph. The system decides three things:
        </p>
        <ol style={prose}>
          <li><b>Geometry</b> — which layout template, how many tiles, what shape each tile is</li>
          <li><b>Selection</b> — which curator picks the photos, what signals it uses to score them</li>
          <li><b>Population</b> — how photos are assigned to cells (big cells get heroes, small cells get supporters)</li>
        </ol>
      </Card>

      {/* 2. The ratio system */}
      <Card title="The 7 allowed ratios">
        <p style={prose}>
          Grid units are <b>square</b> (UNIT_RATIO = 1). Every cell spans an integer number of rows and columns.
          The cell's aspect ratio is <code>cs / rs</code>. Only 7 ratios are legal — any cell producing a ratio
          outside this set is invalid.
        </p>
        <table style={tbl}>
          <thead>
            <tr><th style={th}>Ratio</th><th style={th}>W:H</th><th style={th}>Spans (rs x cs)</th><th style={th}>Orient</th><th style={th}>Crop Key</th></tr>
          </thead>
          <tbody>
            {RATIOS.map(r => (
              <tr key={r.ratio}>
                <td style={td}><code>{r.ratio}</code></td>
                <td style={td}>{r.wh}</td>
                <td style={td}><code>{r.spans}</code></td>
                <td style={{ ...td, color: r.orient === 'Portrait' ? '#6366f1' : r.orient === 'Square' ? '#10b981' : '#06b6d4' }}>{r.orient}</td>
                <td style={td}>{r.crop}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p style={{ ...prose, marginTop: 12 }}>
          The crop key maps to Gemma's per-image crop recommendations. Each photo has AI-computed focal points
          for 1:1, 2:3, 3:2, and 16:9 crops, telling us where to position <code>object-position</code> so the subject stays centered.
        </p>
      </Card>

      {/* 2b. Container ratio */}
      <Card title="Container ratio — the missing multiplier">
        <p style={prose}>
          The grid math models units as square (<code>UNIT_RATIO = 1</code>), so a 2x3 cell's ratio is <code>cs/rs = 3/2</code>.
          But on screen, the CSS grid container has a fixed <code>aspect-ratio</code> that stretches the units:
        </p>
        <table style={tbl}>
          <thead>
            <tr><th style={th}>Device</th><th style={th}>Container ratio</th><th style={th}>Grid</th><th style={th}>Unit cell on screen</th><th style={th}>Formula</th></tr>
          </thead>
          <tbody>
            <tr>
              <td style={td}>Desktop</td>
              <td style={td}><code>3/2</code> (1.5)</td>
              <td style={td}>5 cols x 3 rows</td>
              <td style={td}><code>(1.5 / 5) x 3 = 0.9</code> — slightly tall</td>
              <td style={td}><code>containerRatio / cols x rows</code></td>
            </tr>
            <tr>
              <td style={td}>Mobile</td>
              <td style={td}><code>2/3</code> (0.667)</td>
              <td style={td}>3 cols x 6 rows</td>
              <td style={td}><code>(0.667 / 3) x 6 = 1.33</code> — wide</td>
              <td style={td}><code>containerRatio / cols x rows</code></td>
            </tr>
          </tbody>
        </table>
        <p style={prose}>
          So the <b>rendered</b> cell ratio is <code>(cs / rs) x unitRatio</code> where <code>unitRatio = containerRatio x rows / cols</code>.
          On desktop, a "1:1" (1x1) cell actually renders at 0.9:1 — 10% taller than square. On mobile, a "1:1" cell renders at 1.33:1 — wider.
        </p>
        <p style={prose}>
          The crop system accounts for this. <code>getObjectPosition</code> receives the grid dimensions and container ratio,
          computes <code>renderedCellRatio = (cs/rs) x containerRatio x rows / cols</code>, and uses <b>that</b> to select
          the correct Gemma crop key. Similarly, <code>cropFitness</code> in <code>fillCells</code> uses the rendered unit ratio
          so the photo-to-cell scoring reflects the actual on-screen shape, not the mathematical one.
        </p>
        <div style={{ ...prose, background: 'var(--surface-elevated, #1a1a1a)', padding: '10px 14px', borderRadius: 8, marginTop: 8, fontFamily: 'monospace', fontSize: 11, lineHeight: 1.8 }}>
          .bento-grid {'{'}<br />
          &nbsp;&nbsp;grid-template-columns: repeat(var(--bento-cols), 1fr);<br />
          &nbsp;&nbsp;grid-template-rows: repeat(var(--bento-rows), 1fr);<br />
          &nbsp;&nbsp;aspect-ratio: {'{'} desktop: 3/2, mobile: 2/3 {'}'};<br />
          &nbsp;&nbsp;height: 100%; /* within 68dvh row */<br />
          {'}'}
        </div>
      </Card>

      {/* 3. Desktop grid */}
      <Card title="Desktop grid — 5 x 3 (15 units)">
        <p style={prose}>
          Viewport ratio ~16:9 = 1.78. Grid ratio 5/3 = 1.67. Unit cells render ~1.07:1 on screen — close to square.
          Layouts range from 3 to 11 tiles.
        </p>
        <div style={gridRow}>
          {desktopLayouts.map(l => (
            <div key={l.id} style={layoutCard}>
              <div style={layoutLabel}>{l.id} <span style={tileBadge}>{l.tiles} tiles</span></div>
              <AsciiGrid cols={5} rows={3} cells={l.cells} unit={24} />
              <div style={layoutDesc}>{l.desc}</div>
            </div>
          ))}
        </div>
      </Card>

      {/* 4. Mobile grid */}
      <Card title="Mobile grid — 3 x 6 (18 units)">
        <p style={prose}>
          Viewport ratio ~9:16 minus bars = 0.5–0.6. Grid ratio 3/6 = 0.5. Unit cells ~1:1 on screen.
          Layouts range from 5 to 8 tiles.
        </p>
        <div style={gridRow}>
          {mobileLayouts.map(l => (
            <div key={l.id} style={layoutCard}>
              <div style={layoutLabel}>{l.id} <span style={tileBadge}>{l.tiles} tiles</span></div>
              <AsciiGrid cols={3} rows={6} cells={l.cells} unit={20} />
              <div style={layoutDesc}>{l.desc}</div>
            </div>
          ))}
        </div>
      </Card>

      {/* 5. Selection */}
      <Card title="Selection — 20 curators">
        <p style={prose}>
          Each bento generation shuffles the curator list and tries up to 3 curators before falling back to the default.
          A curator filters the photo pool by thematic criteria, then scores each candidate. Curators with weight 2 appear
          twice in the list and are selected more often.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 10 }}>
          {CURATORS.map(c => (
            <div key={c.name} style={curatorCard}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <span style={curatorName}>{c.name}</span>
                {c.weight > 1 && <span style={weightBadge}>x{c.weight}</span>}
              </div>
              <div style={curatorDesc}>{c.desc}</div>
              <div style={signalList}>Signals: <code>{c.signals}</code></div>
            </div>
          ))}
        </div>
      </Card>

      {/* 6. Population */}
      <Card title="Population — fillCells algorithm">
        <p style={prose}>
          Once a curator produces a scored photo pool, <code>fillCells</code> assigns photos to grid cells:
        </p>
        <ol style={prose}>
          <li><b>Sort cells by area</b> — largest cells (heroes) get filled first</li>
          <li><b>Match orientation</b> — portrait cells prefer portrait photos, landscape cells prefer landscape</li>
          <li><b>Score = curator score + cropFitness</b> — the crop fitness bonus (+/-3 pts) rewards photos whose
            Gemma crop coverage is high for this specific cell ratio. A photo that fills a 3:2 frame well scores higher
            than one that would need heavy cropping.</li>
          <li><b>Claim + dedup</b> — once assigned, a photo (and its parent/child variants) are blocked from other cells.
            No original and its AI variant can appear in the same bento.</li>
          <li><b>Second pass</b> — any remaining empty cells get filled from the full pool, ignoring orientation preference</li>
        </ol>

        <h4 style={{ marginTop: 16, fontSize: 13, fontWeight: 600 }}>Visual impact scoring</h4>
        <p style={prose}>
          Base score for every photo, used by all curators:
        </p>
        <ul style={prose}>
          <li>Aesthetic score (0-10) — from quality_scores composite</li>
          <li>+2 if print_worthy (Gemma's museum-quality flag)</li>
          <li>+1 if high contrast (&gt;55), +0.5 if monochrome</li>
          <li>+1 if sharp (Gemma sharpness), +0.3 if motion blur</li>
          <li>+0.5 if balanced exposure, +0.5 if dynamic energy</li>
        </ul>

        <h4 style={{ marginTop: 16, fontSize: 13, fontWeight: 600 }}>Crop fitness</h4>
        <p style={prose}>
          For each (photo, cell) pair, Gemma's crop coverage value (0-100) is compared to neutral (50).
          Coverage &gt; 50 means the subject fills the frame well at this ratio. The bonus is <code>(coverage - 50) x 0.06</code>,
          giving ±3 points. This ensures a portrait photo with a perfectly centered face gets placed in the
          portrait cell, not the wide landscape cell where it would be aggressively cropped.
        </p>
      </Card>

      {/* 7. Variant injection */}
      <Card title="AI variant injection">
        <p style={prose}>
          In <b>mixed mode</b>, after the curator fills cells, AI-generated variants are injected:
        </p>
        <ol style={prose}>
          <li><b>First pass:</b> any selected original that has an accepted variant gets swapped (original replaced by variant)</li>
          <li><b>Second pass:</b> if variant count is below 40% of tiles, random originals with variants are pulled in and swapped</li>
          <li><b>Guarantee:</b> if still zero variants, one tile is force-replaced with a random variant</li>
        </ol>
        <p style={prose}>
          In <b>photo mode</b>, only originals appear. In <b>generated mode</b>, only AI variants appear.
          Color-filtered bentos skip variant injection to preserve chromatic coherence.
        </p>
      </Card>

      {/* 8. Tap to split */}
      <Card title="Tap-to-split">
        <p style={prose}>
          Users can tap any multi-span cell to subdivide it. Each cell shape has predefined split patterns
          that only produce children with allowed ratios:
        </p>
        <table style={tbl}>
          <thead>
            <tr><th style={th}>Parent cell</th><th style={th}>Splits into</th><th style={th}>Description</th></tr>
          </thead>
          <tbody>
            {SPLIT_EXAMPLES.map((s, i) => (
              <tr key={i}>
                <td style={td}><code>{s.from}</code></td>
                <td style={td}><code>{s.to}</code></td>
                <td style={td}>{s.desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {/* 9. Density */}
      <Card title="Density control">
        <p style={prose}>
          The density slider controls how many tiles appear. In bento mode, only counts with a beautiful
          mixed-size layout are available:
        </p>
        <ul style={prose}>
          <li><b>Desktop:</b> 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 16, 20, 24, 36, 48, 64</li>
          <li><b>Mobile:</b> 2, 4, 5, 6, 7, 8, 9</li>
        </ul>
        <p style={prose}>
          For counts &gt; 11 (desktop) or &gt; 8 (mobile), layouts are generated dynamically with <code>uniformBentoGrid</code> —
          it computes optimal cols/rows to minimize wasted cells, inserts ~20% portrait cells for variety, and aims for
          a grid ratio matching the device viewport.
        </p>
        <p style={prose}>
          In uniform mode, all tiles are identical squares — valid counts are those that tile perfectly with zero waste.
        </p>
      </Card>

      {/* 10. File map */}
      <Card title="Source files">
        <table style={tbl}>
          <thead>
            <tr><th style={th}>File</th><th style={th}>Responsibility</th></tr>
          </thead>
          <tbody>
            {[
              ['frontend/show/src/lib/cropUtils.ts', 'BENTO_UNIT_RATIO, ALLOWED_RATIOS, BentoCell interface, crop key mapping, smart object-position'],
              ['frontend/show/src/lib/layoutRegistry.ts', 'All layout definitions (desktop, mobile, starter), density computation, split patterns, image type filtering'],
              ['frontend/show/src/views/BentoView.tsx', '20 curators, fillCells algorithm, variant injection, tap-to-split UI, color bucketing, generate() orchestration'],
              ['frontend/show/src/types/photo.ts', 'Photo interface with all signal fields used by curators'],
              ['backend/prepare_show/curate.py', 'Server-side layout assignment for pre-computed data'],
              ['backend/prepare_show/score.py', 'Server-side scoring with ratio-to-crop-key mapping'],
            ].map(([file, desc]) => (
              <tr key={file}>
                <td style={{ ...td, fontFamily: 'monospace', fontSize: 11 }}>{file}</td>
                <td style={td}>{desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </PageShell>
  )
}

/* ===== Styles ===== */

const prose: CSSProperties = { fontSize: 13, lineHeight: 1.65, color: 'var(--text-secondary, #888)', margin: '6px 0' }
const tbl: CSSProperties = { width: '100%', borderCollapse: 'collapse', fontSize: 12, marginTop: 8 }
const th: CSSProperties = { textAlign: 'left', padding: '6px 10px', borderBottom: '1px solid var(--border, #333)', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-tertiary, #666)' }
const td: CSSProperties = { padding: '5px 10px', borderBottom: '1px solid var(--border-subtle, #222)', fontSize: 12, color: 'var(--text-secondary, #aaa)' }
const gridRow: CSSProperties = { display: 'flex', flexWrap: 'wrap', gap: 12, marginTop: 12 }
const layoutCard: CSSProperties = { background: 'var(--surface-elevated, #1a1a1a)', borderRadius: 8, padding: 12, minWidth: 160, flex: '1 1 180px', maxWidth: 260 }
const layoutLabel: CSSProperties = { fontSize: 13, fontWeight: 700, marginBottom: 6, color: 'var(--text-primary, #fff)' }
const layoutDesc: CSSProperties = { fontSize: 11, color: 'var(--text-tertiary, #666)', marginTop: 6 }
const tileBadge: CSSProperties = { fontSize: 10, padding: '1px 5px', borderRadius: 4, background: 'var(--surface-hover, #333)', color: 'var(--text-secondary, #aaa)', fontWeight: 500, marginLeft: 4 }
const curatorCard: CSSProperties = { background: 'var(--surface-elevated, #1a1a1a)', borderRadius: 8, padding: 10 }
const curatorName: CSSProperties = { fontSize: 13, fontWeight: 700, color: 'var(--text-primary, #fff)' }
const curatorDesc: CSSProperties = { fontSize: 12, color: 'var(--text-secondary, #888)', lineHeight: 1.5 }
const signalList: CSSProperties = { fontSize: 10, color: 'var(--text-tertiary, #555)', marginTop: 4 }
const weightBadge: CSSProperties = { fontSize: 9, padding: '1px 4px', borderRadius: 3, background: '#6366f133', color: '#818cf8', fontWeight: 600 }
