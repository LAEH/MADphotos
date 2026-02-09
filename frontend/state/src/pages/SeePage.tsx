import { Footer } from '../components/layout/Footer'

export function SeePage() {
  return (
    <>
      {/* Hero */}
      <div style={{ marginBottom: 'var(--space-10)' }}>
        <div style={{
          fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase',
          letterSpacing: 'var(--tracking-caps)', color: 'var(--system-purple)',
          marginBottom: 'var(--space-2)',
        }}>
          Native macOS App
        </div>
        <h1 style={{
          fontFamily: 'var(--font-display)', fontSize: 'var(--text-4xl)', fontWeight: 800,
          letterSpacing: '-0.03em', lineHeight: 1.1, marginBottom: 'var(--space-3)',
        }}>
          See
        </h1>
        <p style={{
          fontSize: 'var(--text-base)', lineHeight: 'var(--leading-relaxed)',
          color: 'var(--fg-secondary)', maxWidth: 600,
        }}>
          The operator's console. A native SwiftUI app for exploring, curating, and editing
          9,011 photographs across 24 filterable dimensions. Every decision flows back into the database.
        </p>
      </div>

      {/* Specs */}
      <Section label="Specifications" heading="Technical foundation">
        <div style={{
          display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)',
        }} className="infra-grid">
          {[
            { label: 'Framework', value: 'SwiftUI (macOS 14+)' },
            { label: 'Build System', value: 'Swift Package Manager' },
            { label: 'Database', value: 'SQLite3 C API (no ORM)' },
            { label: 'Architecture', value: 'MVVM + @MainActor' },
            { label: 'Concurrency', value: 'Actor-based (Swift 5.9)' },
            { label: 'Image Loading', value: 'CGImageSource (GPU-accelerated)' },
            { label: 'Dependencies', value: 'Zero (system sqlite3 only)' },
            { label: 'Window System', value: 'Dual-window (Collection + Viewer)' },
          ].map(item => (
            <div key={item.label} style={{
              background: 'var(--card-bg)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)', padding: 'var(--space-3) var(--space-4)',
              boxShadow: 'var(--shadow-sm)',
            }}>
              <div style={{
                fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase',
                letterSpacing: 'var(--tracking-caps)', color: 'var(--muted)', marginBottom: 2,
              }}>
                {item.label}
              </div>
              <div style={{ fontSize: 'var(--text-sm)', color: 'var(--fg)', fontWeight: 500 }}>
                {item.value}
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* Architecture */}
      <Section label="Architecture" heading="How it fits together">
        <p style={{
          fontSize: 'var(--text-sm)', lineHeight: 'var(--leading-relaxed)',
          color: 'var(--fg-secondary)', marginBottom: 'var(--space-5)', maxWidth: 640,
        }}>
          Single <Code>@MainActor PhotoStore</Code> ObservableObject drives all UI state.
          Two SwiftUI windows share the same store via <Code>@EnvironmentObject</Code>.
          Database access uses the raw SQLite3 C API for maximum control and zero abstraction cost.
          Image loading runs on a dedicated <Code>ThumbnailLoader</Code> actor with 8 concurrent slots.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          {[
            { from: 'SeeApp.swift', arrow: true, to: 'Creates PhotoStore, manages 2 windows' },
            { from: 'PhotoStore.swift', arrow: true, to: 'Central state: filters, sort, curation, cache' },
            { from: 'Database.swift', arrow: true, to: 'Raw SQLite3 C API, 75-column JOIN query' },
            { from: 'ContentView.swift', arrow: true, to: 'Grid + sidebar + toolbar layout' },
            { from: 'ImageGrid.swift', arrow: true, to: 'LazyVGrid, pinch-to-zoom columns' },
            { from: 'DetailView.swift', arrow: true, to: 'Metadata, tags, curation, variants' },
            { from: 'ZoomableImageView.swift', arrow: true, to: 'Pinch/pan zoom, tiered loading' },
            { from: 'FilterSidebar.swift', arrow: true, to: '24 collapsible filter dimensions' },
            { from: 'Models.swift', arrow: true, to: 'PhotoItem, FilterState, SortOption, enums' },
          ].map(row => (
            <div key={row.from} style={{
              display: 'flex', alignItems: 'center', gap: 'var(--space-3)',
              padding: 'var(--space-2) var(--space-3)',
              background: 'var(--card-bg)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
            }}>
              <code style={{
                fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600,
                color: 'var(--system-purple)', whiteSpace: 'nowrap', minWidth: 190,
              }}>
                {row.from}
              </code>
              <span style={{ color: 'var(--muted)', fontSize: 11 }}>&rarr;</span>
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--fg-secondary)' }}>
                {row.to}
              </span>
            </div>
          ))}
        </div>
      </Section>

      {/* Keyboard Shortcuts */}
      <Section label="Controls" heading="Keyboard shortcuts">
        <p style={{
          fontSize: 'var(--text-sm)', color: 'var(--fg-secondary)',
          marginBottom: 'var(--space-5)',
        }}>
          Every action has a single-key shortcut. No modifier keys needed for curation flow.
        </p>
        <div style={{
          display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)',
        }} className="infra-grid">
          <KeyGroup title="Curation" keys={[
            { key: 'P', desc: 'Pick (mark as kept)' },
            { key: 'R', desc: 'Reject' },
            { key: 'U', desc: 'Unflag (reset to pending)' },
          ]} />
          <KeyGroup title="Navigation" keys={[
            { key: '\u2190', desc: 'Previous photo' },
            { key: '\u2192', desc: 'Next photo' },
            { key: 'ESC', desc: 'Deselect / exit mode' },
          ]} />
          <KeyGroup title="View" keys={[
            { key: 'E', desc: 'Toggle enhanced image' },
            { key: 'I', desc: 'Toggle info panel' },
            { key: '\u2318F', desc: 'Focus search field' },
            { key: '\u2318\u2325S', desc: 'Toggle sidebar' },
          ]} />
          <KeyGroup title="Location" keys={[
            { key: 'Y', desc: 'Accept propagated location' },
            { key: 'N', desc: 'Reject propagated location' },
          ]} />
        </div>
        <div style={{ marginTop: 'var(--space-5)' }}>
          <KeyGroup title="Trackpad gestures" keys={[
            { key: 'Pinch', desc: 'Grid: change column count (2\u201312). Viewer: zoom (1\u201310x)' },
            { key: 'Drag', desc: 'Viewer: pan when zoomed in' },
            { key: 'Double-click', desc: 'Viewer: toggle fit \u2194 2.5x zoom' },
          ]} />
        </div>
      </Section>

      {/* Filter System */}
      <Section label="Filters" heading="24 dimensions of exploration">
        <p style={{
          fontSize: 'var(--text-sm)', lineHeight: 'var(--leading-relaxed)',
          color: 'var(--fg-secondary)', marginBottom: 'var(--space-5)', maxWidth: 640,
        }}>
          Every filter shows contextual counts &mdash; how many photos match <em>given all other active filters</em>.
          Multi-value dimensions support union (any match) or intersection (all match) modes.
          Active filters appear as removable chips in the query bar.
        </p>
        <div style={{
          display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 'var(--space-2)',
        }} className="model-grid">
          {[
            { name: 'Camera', color: 'var(--system-blue)' },
            { name: 'Category', color: 'var(--system-blue)' },
            { name: 'Subcategory', color: 'var(--system-blue)' },
            { name: 'Orientation', color: 'var(--system-blue)' },
            { name: 'Format', color: 'var(--system-blue)' },
            { name: 'Curation', color: 'var(--system-green)' },
            { name: 'Vibe', color: 'var(--system-purple)' },
            { name: 'Scene', color: 'var(--system-green)' },
            { name: 'Emotion', color: 'var(--system-pink)' },
            { name: 'Style', color: 'var(--system-orange)' },
            { name: 'Grading', color: 'var(--system-orange)' },
            { name: 'Exposure', color: 'var(--system-orange)' },
            { name: 'Composition', color: 'var(--system-orange)' },
            { name: 'Depth', color: 'var(--system-teal)' },
            { name: 'Time of Day', color: 'var(--system-teal)' },
            { name: 'Setting', color: 'var(--system-teal)' },
            { name: 'Weather', color: 'var(--system-teal)' },
            { name: 'Aesthetic', color: 'var(--system-orange)' },
            { name: 'Location', color: 'var(--system-green)' },
            { name: 'Medium', color: 'var(--system-blue)' },
            { name: 'Film Stock', color: 'var(--system-blue)' },
            { name: 'Enhancement', color: 'var(--system-blue)' },
            { name: 'Monochrome', color: 'var(--muted)' },
            { name: 'Has Text (OCR)', color: 'var(--muted)' },
          ].map(f => (
            <div key={f.name} style={{
              background: 'var(--card-bg)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)', padding: 'var(--space-2) var(--space-3)',
              fontSize: 'var(--text-xs)', fontWeight: 600, color: f.color,
            }}>
              {f.name}
            </div>
          ))}
        </div>
        <p style={{
          fontSize: 'var(--text-xs)', color: 'var(--muted)', marginTop: 'var(--space-3)',
        }}>
          Plus quick toggles: People, Animals, No Subject, Monochrome, Color, Has Text.
          Free-text search scans alt text, filename, folder, vibes, location, captions, and OCR.
        </p>
      </Section>

      {/* Sort Options */}
      <Section label="Sorting" heading="9 sort dimensions">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
          {[
            { name: 'Random', icon: '\uD83C\uDFB2', desc: 'Shuffle (default on launch)' },
            { name: 'Quality', icon: '\u2728', desc: 'Technical + CLIP combined score' },
            { name: 'Aesthetic', icon: '\u2B50', desc: 'NIMA aesthetic score' },
            { name: 'Date', icon: '\uD83D\uDCC5', desc: 'EXIF date taken' },
            { name: 'Exposure', icon: '\u2600\uFE0F', desc: 'Over > Balanced > Under' },
            { name: 'Saturation', icon: '\uD83C\uDFA8', desc: 'Palette saturation' },
            { name: 'Depth', icon: '\uD83C\uDF0A', desc: 'Depth complexity score' },
            { name: 'Brightness', icon: '\uD83D\uDCA1', desc: 'Palette brightness' },
            { name: 'Faces', icon: '\uD83D\uDE42', desc: 'Detected face count' },
          ].map(s => (
            <div key={s.name} style={{
              background: 'var(--card-bg)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)', padding: 'var(--space-2) var(--space-3)',
              boxShadow: 'var(--shadow-sm)', minWidth: 140,
            }}>
              <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: 2 }}>
                {s.name}
              </div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--fg-secondary)' }}>
                {s.desc}
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* Image Tiers */}
      <Section label="Performance" heading="Tiered image loading">
        <p style={{
          fontSize: 'var(--text-sm)', lineHeight: 'var(--leading-relaxed)',
          color: 'var(--fg-secondary)', marginBottom: 'var(--space-5)', maxWidth: 640,
        }}>
          Grid thumbnails load via <Code>CGImageSourceCreateThumbnailAtIndex</Code> &mdash; 40x faster
          than <Code>NSImage(contentsOfFile:)</Code>. The viewer progressively loads
          higher tiers as the user zooms in. No wasted bandwidth.
        </p>
        <table style={{
          width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-xs)',
        }}>
          <thead>
            <tr>
              {['Tier', 'Max px', 'When', 'Cache'].map(h => (
                <th key={h} style={{
                  textAlign: 'left', padding: 'var(--space-2) var(--space-3)',
                  borderBottom: '2px solid var(--border)', fontWeight: 700,
                  textTransform: 'uppercase', letterSpacing: 'var(--tracking-caps)',
                  color: 'var(--muted)', fontSize: 10,
                }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[
              { tier: 'Thumbnail', px: '640', when: 'Grid cells, instant', cache: 'NSCache, 2,000 items' },
              { tier: 'Display', px: '2,048', when: 'Detail view, 0.3s fade', cache: 'NSCache, 20 items' },
              { tier: 'Enhanced', px: '2,048', when: 'E key toggle', cache: 'On-disk only' },
              { tier: 'Cropped', px: '2,048', when: 'Variant picker', cache: 'On-disk only' },
              { tier: 'Full', px: '3,840', when: 'Zoom > 2x, seamless', cache: 'On-disk only' },
            ].map((row, i) => (
              <tr key={row.tier} style={{
                background: i % 2 ? 'var(--hover-overlay)' : 'transparent',
              }}>
                <td style={{ padding: 'var(--space-2) var(--space-3)', fontWeight: 600, color: 'var(--fg)' }}>{row.tier}</td>
                <td style={{ padding: 'var(--space-2) var(--space-3)', fontFamily: 'var(--font-mono)', color: 'var(--fg-secondary)' }}>{row.px}</td>
                <td style={{ padding: 'var(--space-2) var(--space-3)', color: 'var(--fg-secondary)' }}>{row.when}</td>
                <td style={{ padding: 'var(--space-2) var(--space-3)', color: 'var(--fg-secondary)' }}>{row.cache}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{
          marginTop: 'var(--space-5)', display: 'flex', gap: 'var(--space-3)',
          flexWrap: 'wrap',
        }}>
          <Stat label="Thumbnail loader" value="8 concurrent slots" />
          <Stat label="Grid pinch-to-zoom" value="2\u201312 columns" />
          <Stat label="Viewer zoom range" value="1x\u201310x" />
          <Stat label="Prefetch" value="prev + next display tier" />
        </div>
      </Section>

      {/* Data Model */}
      <Section label="Data" heading="What each photo carries">
        <p style={{
          fontSize: 'var(--text-sm)', lineHeight: 'var(--leading-relaxed)',
          color: 'var(--fg-secondary)', marginBottom: 'var(--space-5)', maxWidth: 640,
        }}>
          The <Code>loadPhotos()</Code> query JOINs 11 tables into a single 75-column result set.
          Each <Code>PhotoItem</Code> carries core metadata, all signal outputs, quality scores,
          location data, and curation state. The <Code>prepareCache()</Code> method pre-computes
          derived booleans and lists for O(1) filter matching.
        </p>
        <div style={{
          display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)',
        }} className="infra-grid">
          {[
            { table: 'images', cols: 'uuid, path, filename, category, camera, dimensions, format, medium, monochrome, curated_status, display_variant', count: '9,011' },
            { table: 'gemini_analysis', cols: 'exposure, sharpness, composition, depth, grading, time, setting, weather, vibe, alt_text, semantic_pops', count: '9,011' },
            { table: 'quality_scores', cols: 'technical_score, clip_score, combined_score', count: '9,011' },
            { table: 'aesthetic_scores', cols: 'score, score_label', count: '9,011' },
            { table: 'depth_estimation', cols: 'near_pct, mid_pct, far_pct, depth_complexity', count: '9,011' },
            { table: 'scene_classification', cols: 'scene_1/2/3, score_1/2/3', count: '9,011' },
            { table: 'style_classification', cols: 'style, confidence', count: '9,011' },
            { table: 'image_captions', cols: 'caption (BLIP)', count: '9,011' },
            { table: 'exif_metadata', cols: 'date_taken, gps_lat, gps_lon', count: '9,011' },
            { table: 'enhancement_plans', cols: 'status, brightness, contrast, WB shift', count: '9,011' },
            { table: 'image_locations', cols: 'name, lat, lon, source, confidence, accepted', count: 'variable' },
            { table: 'Subqueries', cols: 'object_count, face_count, person_count, animal_count, ocr_text, emotions', count: 'aggregated' },
          ].map(t => (
            <div key={t.table} style={{
              background: 'var(--card-bg)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)', padding: 'var(--space-3)',
            }}>
              <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
                marginBottom: 4,
              }}>
                <code style={{
                  fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700,
                  color: 'var(--system-purple)',
                }}>
                  {t.table}
                </code>
                <span style={{
                  fontFamily: 'var(--font-mono)', fontSize: 10,
                  color: 'var(--muted)', fontVariantNumeric: 'tabular-nums',
                }}>
                  {t.count}
                </span>
              </div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--fg-secondary)', lineHeight: 1.5 }}>
                {t.cols}
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* Curation Workflow */}
      <Section label="Workflow" heading="Curation in practice">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          {[
            { step: '1', title: 'Launch', desc: 'App opens with Random shuffle and Unflagged filter. You see only un-curated photos in random order.' },
            { step: '2', title: 'Browse', desc: 'Pinch to zoom the grid (2\u201312 columns). Click a photo to open the Viewer window.' },
            { step: '3', title: 'Evaluate', desc: 'Zoom in with trackpad pinch (loads full 3840px tier). Check metadata, colors, vibes, scenes in the info panel.' },
            { step: '4', title: 'Decide', desc: 'Press P to keep, R to reject. The app auto-advances to the next photo. Counters update instantly.' },
            { step: '5', title: 'Batch', desc: 'Toggle select mode, click multiple photos, batch-curate with one click.' },
            { step: '6', title: 'Refine', desc: 'Filter by camera, vibe, scene, quality. Sort by Quality to surface the best images first.' },
            { step: '7', title: 'Variants', desc: 'For analog scans with borders, toggle between Original and Cropped in the variant picker.' },
            { step: '8', title: 'Edit', desc: 'Fix wrong labels: click any tag to edit vibes, grading, exposure, composition, time, setting, weather. Type a location name to propagate it to nearby images from the same camera.' },
          ].map(item => (
            <div key={item.step} style={{
              display: 'flex', gap: 'var(--space-4)', alignItems: 'flex-start',
              padding: 'var(--space-3) var(--space-4)',
              background: 'var(--card-bg)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
            }}>
              <div style={{
                fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xl)', fontWeight: 800,
                color: 'var(--system-purple)', lineHeight: 1, minWidth: 24,
              }}>
                {item.step}
              </div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 'var(--text-sm)', marginBottom: 2 }}>
                  {item.title}
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--fg-secondary)', lineHeight: 'var(--leading-relaxed)' }}>
                  {item.desc}
                </div>
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* Display Variants */}
      <Section label="Variants" heading="Non-destructive image versions">
        <p style={{
          fontSize: 'var(--text-sm)', lineHeight: 'var(--leading-relaxed)',
          color: 'var(--fg-secondary)', marginBottom: 'var(--space-5)', maxWidth: 640,
        }}>
          Each photo can have multiple rendered versions. The variant picker appears in the Viewer
          when more than one version exists. Selection is persisted per-image in the
          <Code>display_variant</Code> column.
        </p>
        <div style={{
          display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 'var(--space-3)',
        }} className="model-grid">
          {[
            { name: 'Original', desc: 'The display-tier render from the source file. Always available.', path: 'rendered/display/jpeg/' },
            { name: 'Enhanced', desc: 'Camera-aware adjustments: white balance, exposure, contrast, saturation, sharpening.', path: 'rendered/enhanced/jpeg/' },
            { name: 'Cropped', desc: 'White/cream film scan borders detected and removed. 162 of 1,126 analog images.', path: 'rendered/cropped/jpeg/' },
          ].map(v => (
            <div key={v.name} style={{
              background: 'var(--card-bg)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)', padding: 'var(--space-4)',
              boxShadow: 'var(--shadow-sm)',
            }}>
              <div style={{
                fontSize: 'var(--text-sm)', fontWeight: 700,
                color: 'var(--fg)', marginBottom: 'var(--space-2)',
              }}>
                {v.name}
              </div>
              <div style={{
                fontSize: 'var(--text-xs)', color: 'var(--fg-secondary)',
                lineHeight: 'var(--leading-relaxed)', marginBottom: 'var(--space-2)',
              }}>
                {v.desc}
              </div>
              <code style={{
                fontFamily: 'var(--font-mono)', fontSize: 10,
                color: 'var(--muted)', background: 'var(--hover-overlay)',
                padding: '2px 6px', borderRadius: 4,
              }}>
                {v.path}
              </code>
            </div>
          ))}
        </div>
      </Section>

      {/* Location Propagation */}
      <Section label="Intelligence" heading="Location propagation">
        <p style={{
          fontSize: 'var(--text-sm)', lineHeight: 'var(--leading-relaxed)',
          color: 'var(--fg-secondary)', marginBottom: 'var(--space-4)', maxWidth: 640,
        }}>
          Type a location name on any photo. The system propagates it to all images taken with the
          same camera within &plusmn;7 days, with confidence scores based on temporal distance.
          Propagated locations require explicit accept/reject (Y/N keys).
        </p>
        <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
          <Stat label="Same day" value="0.95 confidence" />
          <Stat label="&plusmn;2 days" value="0.85 confidence" />
          <Stat label="&plusmn;4 days" value="0.70 confidence" />
          <Stat label="&plusmn;7 days" value="0.60 confidence" />
        </div>
      </Section>

      {/* Design Decisions */}
      <Section label="Decisions" heading="Why it's built this way">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          {[
            { q: 'Why raw SQLite3 C API?', a: 'Zero abstraction cost. The main query JOINs 11 tables with subqueries across 75 columns for 9K images. ORM overhead would be measurable. Direct C API gives us full control over prepared statements, WAL mode, and busy timeouts for concurrent access with the Python pipeline.' },
            { q: 'Why actor-based thumbnail loading?', a: 'CGImageSourceCreateThumbnailAtIndex is 40x faster than NSImage but still I/O bound. The ThumbnailLoader actor manages 8 concurrent slots with a continuation-based queue, preventing thread explosion while maximizing disk throughput.' },
            { q: 'Why no external dependencies?', a: 'The only linked library is system sqlite3. No Alamofire, no SDWebImage, no GRDB. Fewer dependencies means faster builds, smaller binary, no version conflicts, and full understanding of every code path.' },
            { q: 'Why dual windows instead of navigation stack?', a: 'The Collection window is for scanning (grid, filters, batch ops). The Viewer window is for evaluating (zoom, metadata, curation). Separating them means you can resize each independently, move them to different monitors, and never lose your grid position when examining a photo.' },
            { q: 'Why in-memory filtering?', a: '9,011 PhotoItems with 30+ cached properties fit easily in memory. Filtering, sorting, and faceted counting all run in-memory on the main actor with zero DB round-trips. This makes filter changes feel instant.' },
            { q: 'Why discrete column counts instead of continuous zoom?', a: 'Continuous thumbSize changes force LazyVGrid to relayout 9K+ items every frame. Discrete column counts (2\u201312) with scaleEffect during the gesture give 60fps pinch with zero layout cost, committing the new layout only on gesture end.' },
          ].map(item => (
            <div key={item.q} style={{
              background: 'var(--card-bg)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)', padding: 'var(--space-4)',
            }}>
              <div style={{
                fontWeight: 700, fontSize: 'var(--text-sm)',
                color: 'var(--fg)', marginBottom: 'var(--space-2)',
              }}>
                {item.q}
              </div>
              <div style={{
                fontSize: 'var(--text-xs)', color: 'var(--fg-secondary)',
                lineHeight: 'var(--leading-relaxed)',
              }}>
                {item.a}
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* Paths */}
      <Section label="Paths" heading="Filesystem layout">
        <table style={{
          width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-xs)',
        }}>
          <tbody>
            {[
              { label: 'Base path', path: '/Users/laeh/Github/MADphotos' },
              { label: 'Database', path: 'images/mad_photos.db' },
              { label: 'Thumbnails', path: 'images/rendered/thumb/jpeg/{uuid}.jpg' },
              { label: 'Display', path: 'images/rendered/display/jpeg/{uuid}.jpg' },
              { label: 'Enhanced', path: 'images/rendered/enhanced/jpeg/{uuid}.jpg' },
              { label: 'Cropped', path: 'images/rendered/cropped/jpeg/{uuid}.jpg' },
              { label: 'Full', path: 'images/rendered/full/jpeg/{uuid}.jpg' },
              { label: 'Vectors', path: 'images/vectors.lance/' },
              { label: 'App icon', path: 'frontend/see/See.icns' },
              { label: 'Source', path: 'frontend/see/Sources/See/*.swift' },
            ].map((row, i) => (
              <tr key={row.label} style={{
                background: i % 2 ? 'var(--hover-overlay)' : 'transparent',
              }}>
                <td style={{
                  padding: 'var(--space-2) var(--space-3)', fontWeight: 600,
                  color: 'var(--fg)', whiteSpace: 'nowrap', width: 100,
                }}>
                  {row.label}
                </td>
                <td style={{ padding: 'var(--space-2) var(--space-3)' }}>
                  <code style={{
                    fontFamily: 'var(--font-mono)', fontSize: 11,
                    color: 'var(--fg-secondary)', background: 'var(--hover-overlay)',
                    padding: '1px 6px', borderRadius: 3,
                  }}>
                    {row.path}
                  </code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Footer />
    </>
  )
}

// -- Helper components --

function Section({ label, heading, children }: { label: string; heading: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 'var(--space-12)' }}>
      <div style={{
        fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: 'var(--tracking-caps)', color: 'var(--muted)', marginBottom: 'var(--space-3)',
      }}>
        {label}
      </div>
      <h2 style={{
        fontFamily: 'var(--font-display)', fontSize: 'var(--text-2xl)', fontWeight: 700,
        letterSpacing: 'var(--tracking-tight)', marginBottom: 'var(--space-5)',
        paddingBottom: 'var(--space-3)', borderBottom: '1px solid var(--border)',
      }}>
        {heading}
      </h2>
      {children}
    </div>
  )
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code style={{
      fontFamily: 'var(--font-mono)', fontSize: '0.9em',
      color: 'var(--system-purple)', background: 'var(--hover-overlay)',
      padding: '1px 5px', borderRadius: 3, fontWeight: 500,
    }}>
      {children}
    </code>
  )
}

function KeyGroup({ title, keys }: { title: string; keys: { key: string; desc: string }[] }) {
  return (
    <div style={{
      background: 'var(--card-bg)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)', padding: 'var(--space-4)',
    }}>
      <div style={{
        fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: 'var(--tracking-caps)', color: 'var(--muted)',
        marginBottom: 'var(--space-3)',
      }}>
        {title}
      </div>
      {keys.map(k => (
        <div key={k.key} style={{
          display: 'flex', alignItems: 'center', gap: 'var(--space-3)',
          padding: '4px 0',
        }}>
          <kbd style={{
            fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 700,
            background: 'var(--hover-overlay)', border: '1px solid var(--border)',
            borderRadius: 4, padding: '2px 8px', minWidth: 32, textAlign: 'center',
            color: 'var(--fg)', lineHeight: '18px',
          }}>
            {k.key}
          </kbd>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--fg-secondary)' }}>
            {k.desc}
          </span>
        </div>
      ))}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{
      background: 'var(--card-bg)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-md)', padding: 'var(--space-2) var(--space-4)',
    }}>
      <div style={{
        fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: 'var(--tracking-caps)', color: 'var(--muted)', marginBottom: 1,
      }}>
        {label}
      </div>
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)',
        fontWeight: 600, color: 'var(--fg)',
      }}>
        {value}
      </div>
    </div>
  )
}
