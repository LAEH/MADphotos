import { useFetch } from '../hooks/useFetch'
import { PageShell } from '../components/layout/PageShell'
import { Card } from '../components/layout/Card'

interface Stats {
  timestamp: string
  total: number
  analyzed: number
  failed: number
  pending: number
  analysis_pct: number
  pixel_analyzed: number
  pixel_pct: number
  categories: { name: string; count: number }[]
  subcategories: { name: string; count: number }[]
  tiers: { name: string; tier: string; format: string; count: number; size_human: string }[]
  tier_coverage: { tier: string; images: number }[]
  total_rendered_human: string
  total_tier_files: number
  ai_variants_total: number
  variant_summary: { type: string; ok: number; fail: number; filtered: number; pending: number; total: number; pct: number }[]
  gcs_uploads: number
  cameras: { body: string; count: number; medium: string; film: string; wb_r: number; wb_b: number; noise: number; shadow: number; luminance: number }[]
  source_formats: { name: string; count: number }[]
  monochrome_count: number
  grading: { name: string; count: number }[]
  time_of_day: { name: string; count: number }[]
  settings: { name: string; count: number }[]
  exposure: { name: string; count: number }[]
  composition: { name: string; count: number }[]
  vibes: { name: string; count: number }[]
  curation: { status: string; count: number }[]
  kept: number
  rejected: number
  curated_total: number
  curation_pct: number
  vector_count: number
  vector_size: string
  runs: { phase: string; status: string; ok: number; failed: number; started: string }[]
  signals: Record<string, { rows: number; images: number; processed?: number }>
  aesthetic_count: number
  aesthetic_avg: number
  aesthetic_min?: number
  aesthetic_max?: number
  depth_count: number
  depth_avg_near: number
  depth_avg_mid: number
  depth_avg_far: number
  scene_count: number
  top_scenes: { name: string; count: number }[]
  scene_environments: { name: string; count: number }[]
  enhancement_count: number
  style_count: number
  top_styles: { name: string; count: number }[]
  ocr_images: number
  ocr_texts: number
  caption_count: number
  emotion_count: number
  top_emotions: { name: string; count: number }[]
  top_objects: { name: string; count: number }[]
  top_color_names: { name: string; hex: string; count: number }[]
  face_images_with: number
  face_total: number
  exif_gps: number
  exif_iso: number
  models_complete: number
  total_signals: number
  db_size: string
  web_json_size: string
  web_photo_count: number
  location_count: number
  location_sources?: { name: string; count: number }[]
  // V2 signals
  v2_signals: Record<string, { rows: number; images: number }>
  aesthetic_v2_count: number
  aesthetic_v2_labels?: { name: string; count: number }[]
  top_tags?: { name: string; count: number }[]
  top_open_labels?: { name: string; count: number }[]
  // Picks curation
  picks?: {
    portrait: number
    landscape: number
    total: number
    votes_total: number
    votes_accept: number
    votes_reject: number
    by_device: { device: string; accepts: number; rejects: number }[]
  }
  // Firestore feedback
  feedback?: {
    last_sync: string | null
    tinder: {
      total: number
      accepts: number
      rejects: number
      by_day: { date: string; accepts: number; rejects: number }[]
      top_accepted: { photo: string; count: number }[]
      top_rejected: { photo: string; count: number }[]
    }
    couple: {
      likes: number
      by_strategy: { strategy: string; count: number }[]
      approves: number
      rejects: number
    }
  }
}

/* ── SVG Icons ── */
const IC = {
  scene:   <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M17 21v-2a4 4 0 00-3-3.87M9 21v-2a4 4 0 00-4-4H3"/><path d="M1 21h22"/><path d="M12 2l3 7h-6l3-7z"/><path d="M7 10l-3 5"/><path d="M17 10l3 5"/></svg>,
  home:    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/></svg>,
  eye:     <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>,
  sparkle: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8z"/></svg>,
  star:    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>,
  frame:   <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><rect x="7" y="7" width="10" height="10"/></svg>,
  film:    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"/><line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/></svg>,
  sunset:  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M17 18a5 5 0 00-10 0"/><line x1="12" y1="9" x2="12" y2="2"/><line x1="4.22" y1="10.22" x2="5.64" y2="11.64"/><line x1="1" y1="18" x2="3" y2="18"/><line x1="21" y1="18" x2="23" y2="18"/><line x1="18.36" y1="11.64" x2="19.78" y2="10.22"/><line x1="23" y1="22" x2="1" y2="22"/></svg>,
}

function fmt(n: number | null | undefined): string {
  return n != null ? n.toLocaleString() : '\u2014'
}

export function StatusPage() {
  const { data, loading, error } = useFetch<Stats>('/api/stats')

  if (loading) return <div style={{ color: 'var(--muted)', padding: 'var(--space-10)' }}>Loading status...</div>
  if (error) return <div style={{ color: 'var(--system-red)', padding: 'var(--space-10)' }}>Error: {error}</div>
  if (!data) return null

  const s = data
  const sigFD = s.signals?.face_detections || { rows: 0, images: 0, processed: 0 }
  const sigOD = s.signals?.object_detections || { rows: 0, images: 0, processed: 0 }
  const sigDC = s.signals?.dominant_colors || { rows: 0, images: 0 }
  const sigEX = s.signals?.exif_metadata || { rows: 0, images: 0 }
  const v2 = s.v2_signals || {}

  /* ── Models (17 v1 + 7 v2) ── */
  const faceProcessed = sigFD.processed || sigFD.images
  const poseImages = v2.pose_detections?.images || 0
  const models: { n: string; name: string; tech: string; count: number; of?: number; v2?: boolean }[] = [
    { n: '01', name: 'Gemini 2.5 Pro', tech: 'Vertex AI \u00B7 Google Cloud', count: s.analyzed },
    { n: '02', name: 'Pixel Analysis', tech: 'Python \u00B7 Pillow \u00B7 NumPy', count: s.pixel_analyzed },
    { n: '03', name: 'DINOv2', tech: 'PyTorch \u00B7 Meta FAIR \u00B7 ViT-B/14', count: s.vector_count },
    { n: '04', name: 'SigLIP', tech: 'PyTorch \u00B7 Google \u00B7 ViT-B/16', count: s.vector_count },
    { n: '05', name: 'CLIP', tech: 'PyTorch \u00B7 OpenAI \u00B7 ViT-B/32', count: s.vector_count },
    { n: '06', name: 'YuNet', tech: 'OpenCV DNN \u00B7 ONNX \u00B7 C++', count: faceProcessed },
    { n: '07', name: 'YOLOv8n', tech: 'PyTorch \u00B7 Ultralytics \u00B7 COCO', count: sigOD.processed || sigOD.images },
    { n: '08', name: 'NIMA', tech: 'PyTorch \u00B7 TensorFlow origin \u00B7 MobileNet', count: s.aesthetic_count },
    { n: '09', name: 'Depth Anything v2', tech: 'PyTorch \u00B7 Hugging Face \u00B7 ViT', count: s.depth_count },
    { n: '10', name: 'Places365', tech: 'PyTorch \u00B7 MIT CSAIL \u00B7 ResNet-50', count: s.scene_count },
    { n: '11', name: 'Style Net', tech: 'PyTorch \u00B7 Custom classifier', count: s.style_count },
    { n: '12', name: 'BLIP', tech: 'PyTorch \u00B7 Salesforce \u00B7 ViT+LLM', count: s.caption_count },
    { n: '13', name: 'EasyOCR', tech: 'PyTorch \u00B7 CRAFT + CRNN', count: s.ocr_images || 0 },
    { n: '14', name: 'Facial Emotions', tech: 'PyTorch \u00B7 FER \u00B7 CNN', count: s.emotion_count || 0, of: sigFD.images },
    { n: '15', name: 'Enhancement Engine', tech: 'Python \u00B7 Pillow \u00B7 Camera-aware', count: s.enhancement_count },
    { n: '16', name: 'K-means LAB', tech: 'Python \u00B7 scikit-learn \u00B7 LAB space', count: sigDC.images },
    { n: '17', name: 'EXIF Parser', tech: 'Python \u00B7 Pillow \u00B7 piexif', count: sigEX.images },
    // V2 models
    { n: '18', name: 'Aesthetic v2', tech: 'TOPIQ + MUSIQ + LAION CLIP', count: s.aesthetic_v2_count || 0, v2: true },
    { n: '19', name: 'CLIP Tags', tech: 'CLIP ViT-B/32 \u00B7 65 categories', count: v2.image_tags?.images || 0, v2: true },
    { n: '20', name: 'Saliency', tech: 'OpenCV \u00B7 Spectral Residual FFT', count: v2.saliency_maps?.images || 0, v2: true },
    { n: '21', name: 'YOLOv8n-pose', tech: 'PyTorch \u00B7 Ultralytics \u00B7 COCO', count: poseImages, of: sigOD.images || s.total, v2: true },
    { n: '22', name: 'Florence-2', tech: 'PyTorch \u00B7 Microsoft \u00B7 770M', count: v2.florence_captions?.images || 0, v2: true },
    { n: '23', name: 'Grounding DINO', tech: 'PyTorch \u00B7 IDEA \u00B7 Open-vocab', count: v2.open_detections?.images || 0, v2: true },
    { n: '24', name: 'rembg', tech: 'PyTorch \u00B7 U2-Net \u00B7 Foreground', count: v2.foreground_masks?.images || 0, v2: true },
  ]
  const modelCount = models.length

  return (
    <PageShell title="System Status" subtitle={<><span className="live-dot" />{s.timestamp}</>}>
      {/* ═══ OVERVIEW GRID ═══ */}
      <Card>
        <div className="overview-grid" style={{ marginBottom: 0 }}>
          <div className="ov-card">
            <div className="ov-val">{fmt(s.total)}</div>
            <div className="ov-label">Photos</div>
          </div>
          <div className="ov-card">
            <div className="ov-val">{s.cameras.length}</div>
            <div className="ov-label">Cameras</div>
          </div>
          <div className="ov-card">
            <div className="ov-val">{fmt(s.picks?.total || 0)}</div>
            <div className="ov-label">Picks</div>
          </div>
          <div className="ov-card">
            <div className="ov-val">{modelCount}</div>
            <div className="ov-label">AI Models</div>
          </div>
          <div className="ov-card">
            <div className="ov-val">{fmt(s.total_signals)}</div>
            <div className="ov-label">Signals</div>
          </div>
          <div className="ov-card">
            <div className="ov-val">{s.models_complete}/{modelCount}</div>
            <div className="ov-label">Complete</div>
          </div>
          <div className="ov-card">
            <div className="ov-val">{s.total_rendered_human}</div>
            <div className="ov-label">Storage</div>
          </div>
          <div className="ov-card">
            <div className="ov-val">{fmt(s.feedback?.tinder.total || 0)}</div>
            <div className="ov-label">Votes</div>
          </div>
        </div>
      </Card>

      {/* ════════════════════════════════════════════════════════════════
          INGESTION — pipeline, rendering, storage
          ════════════════════════════════════════════════════════════════ */}
      <div className="section">
        <div className="section-title">Ingestion</div>
      </div>

      {/* Render Tiers + Pipeline Runs — side by side */}
      <div className="section-row">
        <div className="section">
          <div className="signal-group-label">Render Tiers</div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Tier / Format</th>
                  <th className="num">Files</th>
                  <th className="num">Size</th>
                </tr>
              </thead>
              <tbody>
                {s.tiers.map(t => (
                  <tr key={t.name}>
                    <td>{t.name}</td>
                    <td className="num">{fmt(t.count)}</td>
                    <td className="num">{t.size_human}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {s.runs.length > 0 && (
          <div className="section">
            <div className="signal-group-label">Pipeline Runs</div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Phase</th>
                    <th>Status</th>
                    <th className="num">OK</th>
                    <th className="num">Failed</th>
                    <th>Started</th>
                  </tr>
                </thead>
                <tbody>
                  {s.runs.map((run, i) => (
                    <tr key={i}>
                      <td style={{ fontWeight: 600 }}>{run.phase}</td>
                      <td>
                        <span className={`badge ${run.status === 'completed' ? 'done' : run.status === 'failed' ? 'empty' : 'partial'}`}>
                          {run.status}
                        </span>
                      </td>
                      <td className="num">{fmt(run.ok)}</td>
                      <td className="num" style={{ color: run.failed > 0 ? 'var(--system-red)' : undefined }}>{fmt(run.failed)}</td>
                      <td style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)' }}>{run.started}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Storage */}
      <div className="section">
        <div className="signal-group-label">Storage</div>
        <div className="disk-row">
          <div className="disk-item">
            <div className="di-val">{s.total_rendered_human}</div>
            <div className="di-label">Rendered tiers</div>
          </div>
          <div className="disk-item">
            <div className="di-val">{s.db_size}</div>
            <div className="di-label">Database</div>
          </div>
          <div className="disk-item">
            <div className="di-val">{s.vector_size}</div>
            <div className="di-label">Vectors (LanceDB)</div>
          </div>
          {s.web_photo_count > 0 && (
            <div className="disk-item">
              <div className="di-val">{s.web_json_size}</div>
              <div className="di-label">Web gallery ({fmt(s.web_photo_count)} photos)</div>
            </div>
          )}
          {s.gcs_uploads > 0 && (
            <div className="disk-item">
              <div className="di-val">{fmt(s.gcs_uploads)}</div>
              <div className="di-label">GCS uploads</div>
            </div>
          )}
        </div>
      </div>

      {/* ════════════════════════════════════════════════════════════════
          VERIFIED — human-curated signals
          ════════════════════════════════════════════════════════════════ */}
      <div className="section">
        <div className="section-title">Verified</div>
      </div>

      {/* Picks */}
      {s.picks && s.picks.total > 0 && (
        <div className="section">
          <div className="signal-group-label">Picks</div>
          <div className="disk-row">
            <div className="disk-item">
              <div className="di-val">{fmt(s.picks.total)}</div>
              <div className="di-label">Total picks</div>
            </div>
            <div className="disk-item">
              <div className="di-val">{fmt(s.picks.portrait)}</div>
              <div className="di-label">Portrait</div>
            </div>
            <div className="disk-item">
              <div className="di-val">{fmt(s.picks.landscape)}</div>
              <div className="di-label">Landscape</div>
            </div>
            <div className="disk-item">
              <div className="di-val">
                {s.total > 0 ? (s.picks.total / s.total * 100).toFixed(1) + '%' : '\u2014'}
              </div>
              <div className="di-label">of collection</div>
            </div>
          </div>

          {s.picks.votes_total > 0 && (
            <div className="signal-group" style={{ marginTop: 'var(--space-4)' }}>
              <div className="signal-group-label">Re-curation Votes</div>
              <p style={{ fontSize: 'var(--text-sm)', color: 'var(--muted)', marginBottom: 'var(--space-2)' }}>
                Second-pass review of accepted picks
              </p>
              <div className="disk-row">
                <div className="disk-item">
                  <div className="di-val">{fmt(s.picks.votes_total)}</div>
                  <div className="di-label">Total votes</div>
                </div>
                <div className="disk-item">
                  <div className="di-val" style={{ color: 'var(--system-green)' }}>{fmt(s.picks.votes_accept)}</div>
                  <div className="di-label">Kept</div>
                </div>
                <div className="disk-item">
                  <div className="di-val" style={{ color: 'var(--system-red)' }}>{fmt(s.picks.votes_reject)}</div>
                  <div className="di-label">Removed</div>
                </div>
              </div>
              {s.picks.by_device.length > 0 && (
                <div className="table-wrap" style={{ marginTop: 'var(--space-3)' }}>
                  <table>
                    <thead>
                      <tr>
                        <th>Device</th>
                        <th className="num" style={{ color: 'var(--system-green)' }}>Kept</th>
                        <th className="num" style={{ color: 'var(--system-red)' }}>Removed</th>
                        <th className="num">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {s.picks.by_device.map(d => (
                        <tr key={d.device}>
                          <td>{d.device}</td>
                          <td className="num">{fmt(d.accepts)}</td>
                          <td className="num">{fmt(d.rejects)}</td>
                          <td className="num">{fmt(d.accepts + d.rejects)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Tinder Feedback + Couple Game — side by side */}
      <div className="section-row">
        {s.feedback && s.feedback.tinder.total > 0 && (
          <div className="section">
            <div className="signal-group-label">Tinder Feedback</div>
            <p style={{ fontSize: 'var(--text-sm)', color: 'var(--muted)', marginBottom: 'var(--space-3)' }}>
              Live votes from Firestore{s.feedback.last_sync && (
                <> &mdash; last sync {new Date(s.feedback.last_sync).toLocaleString()}</>
              )}
            </p>

            <div className="disk-row">
              <div className="disk-item">
                <div className="di-val">{fmt(s.feedback.tinder.total)}</div>
                <div className="di-label">Tinder votes</div>
              </div>
              <div className="disk-item">
                <div className="di-val" style={{ color: 'var(--system-green)' }}>{fmt(s.feedback.tinder.accepts)}</div>
                <div className="di-label">Accepted ({s.feedback.tinder.total > 0 ? Math.round(s.feedback.tinder.accepts / s.feedback.tinder.total * 100) : 0}%)</div>
              </div>
              <div className="disk-item">
                <div className="di-val" style={{ color: 'var(--system-red)' }}>{fmt(s.feedback.tinder.rejects)}</div>
                <div className="di-label">Rejected ({s.feedback.tinder.total > 0 ? Math.round(s.feedback.tinder.rejects / s.feedback.tinder.total * 100) : 0}%)</div>
              </div>
            </div>

            {s.feedback.tinder.by_day.length > 1 && (
              <div className="signal-group" style={{ marginTop: 'var(--space-4)' }}>
                <div className="signal-group-label">Daily Activity</div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th className="num" style={{ color: 'var(--system-green)' }}>Accepts</th>
                        <th className="num" style={{ color: 'var(--system-red)' }}>Rejects</th>
                        <th className="num">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {s.feedback.tinder.by_day.map(day => (
                        <tr key={day.date}>
                          <td>{day.date}</td>
                          <td className="num">{fmt(day.accepts)}</td>
                          <td className="num">{fmt(day.rejects)}</td>
                          <td className="num">{fmt(day.accepts + day.rejects)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {s.feedback && s.feedback.couple.likes > 0 && (
          <div className="section">
            <div className="signal-group-label">Couple Game</div>
            <div className="disk-row">
              <div className="disk-item">
                <div className="di-val">{fmt(s.feedback.couple.likes)}</div>
                <div className="di-label">Couple likes</div>
              </div>
              {s.feedback.couple.approves > 0 && (
                <div className="disk-item">
                  <div className="di-val" style={{ color: 'var(--system-green)' }}>{fmt(s.feedback.couple.approves)}</div>
                  <div className="di-label">Approves</div>
                </div>
              )}
              {s.feedback.couple.rejects > 0 && (
                <div className="disk-item">
                  <div className="di-val" style={{ color: 'var(--system-red)' }}>{fmt(s.feedback.couple.rejects)}</div>
                  <div className="di-label">Rejects</div>
                </div>
              )}
            </div>
            {s.feedback.couple.by_strategy.length > 0 && (
              <div className="signal-group" style={{ marginTop: 'var(--space-4)' }}>
                <div className="signal-group-label">Liked Strategies</div>
                <div className="tag-row">
                  {s.feedback.couple.by_strategy.map(st => (
                    <div key={st.strategy} className="tag tag-cat-style">
                      <span className="tag-icon">{IC.star}</span>
                      <span className="tag-label">{st.strategy}</span>
                      <span className="tag-count">{fmt(st.count)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ════════════════════════════════════════════════════════════════
          PREDICTED — AI-generated signals
          ════════════════════════════════════════════════════════════════ */}
      <div className="section">
        <div className="section-title">Predicted</div>
      </div>

      {/* Models Grid */}
      <div className="section">
        <div className="signal-group-label">Models</div>
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--muted)', marginBottom: 'var(--space-3)' }}>
          {modelCount} models &mdash; {s.models_complete} complete
        </p>
        <div className="el-grid">
          {models.map(m => {
            const denom = m.of ?? s.total
            const pct = denom > 0 ? (m.count / denom * 100) : 0
            const status = pct >= 99.5 ? 'done' : pct > 0 ? 'active' : 'pending'
            return (
              <div key={m.n} className={`el-card status-${status}`}>
                <div className="el-num">{m.n}{m.v2 && <span className="v2-badge">v2</span>}</div>
                <div className="el-model">{m.name}</div>
                <div className="el-tech">{m.tech}</div>
                <div className="el-count">
                  {fmt(m.count)}{' '}
                  {status === 'done' ? (
                    <span className="el-badge done">{'\u2713'}</span>
                  ) : status === 'active' ? (
                    <span className="el-badge active">{pct.toFixed(0)}%</span>
                  ) : (
                    <span className="el-badge pending">{'\u2014'}</span>
                  )}
                </div>
                <div className="el-bar">
                  <div className="el-fill" style={{ width: `${Math.min(pct, 100)}%` }} />
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Semantic + Visual signals — side by side */}
      <div className="section-row">
        <div className="section">
          <div className="signal-group-label">Semantic Signals</div>

          <div className="signal-group">
            <div className="signal-group-label">Scene & Setting</div>
            <div className="tag-row">
              <Tags items={s.top_scenes} icon={IC.scene} cat="scene" />
              <Tags items={s.scene_environments} icon={IC.home} cat="scene-env" />
              <Tags items={s.settings} icon={IC.scene} cat="scene-set" />
              <Tags items={s.top_objects || []} icon={IC.eye} cat="scene-obj" />
            </div>
          </div>

          <div className="signal-group">
            <div className="signal-group-label">Context</div>
            <div className="tag-row">
              <Tags items={s.subcategories} icon={IC.film} cat="camera" />
              <Tags items={s.time_of_day} icon={IC.sunset} cat="camera-time" />
            </div>
          </div>
        </div>

        <div className="section">
          <div className="signal-group-label">Visual Signals</div>

          <div className="signal-group">
            <div className="signal-group-label">Style & Mood</div>
            <div className="tag-row">
              <Tags items={s.vibes} icon={IC.sparkle} cat="style" />
              <Tags items={s.top_emotions || []} icon={IC.sparkle} cat="style-emo" />
              <Tags items={s.grading} icon={IC.star} cat="style-grad" />
              <Tags items={s.top_styles || []} icon={IC.sparkle} cat="style-cls" />
              <ColorTags items={s.top_color_names || []} />
            </div>
          </div>

          <div className="signal-group">
            <div className="signal-group-label">Structure</div>
            <div className="tag-row">
              <Tags items={s.composition} icon={IC.frame} cat="depth-comp" />
            </div>
          </div>
        </div>
      </div>

      {/* Signal Coverage — Content / Detection */}
      <div className="section">
        <div className="signal-group-label">Content Signals</div>
        <div className="disk-row">
          <div className="disk-item">
            <div className="di-val">{fmt(s.face_images_with)}</div>
            <div className="di-label">Images with faces ({fmt(s.face_total)} faces total)</div>
          </div>
          <div className="disk-item">
            <div className="di-val">{fmt(s.ocr_texts)}</div>
            <div className="di-label">Text regions across {fmt(s.ocr_images)} images</div>
          </div>
          <div className="disk-item">
            <div className="di-val">{fmt(sigOD.rows)}</div>
            <div className="di-label">Objects detected in {fmt(sigOD.processed || sigOD.images)} images</div>
          </div>
          {(s.emotion_count || 0) > 0 && (
            <div className="disk-item">
              <div className="di-val">{fmt(s.emotion_count)}</div>
              <div className="di-label">Faces with emotion analysis</div>
            </div>
          )}
        </div>
      </div>

      {/* V2 Signals */}
      {Object.keys(v2).length > 0 && (
        <div className="section">
          <div className="signal-group-label">V2 Signals <span className="v2-badge" style={{ marginLeft: 6, verticalAlign: 'middle' }}>new</span></div>

          <div className="disk-row">
            {(v2.image_tags?.images || 0) > 0 && (
              <div className="disk-item">
                <div className="di-val">{fmt(v2.image_tags?.images)}</div>
                <div className="di-label">Images tagged (CLIP zero-shot)</div>
              </div>
            )}
            {(v2.saliency_maps?.images || 0) > 0 && (
              <div className="disk-item">
                <div className="di-val">{fmt(v2.saliency_maps?.images)}</div>
                <div className="di-label">Saliency maps (spectral residual)</div>
              </div>
            )}
            {(v2.pose_detections?.images || 0) > 0 && (
              <div className="disk-item">
                <div className="di-val">{fmt(v2.pose_detections?.rows)}</div>
                <div className="di-label">Poses across {fmt(v2.pose_detections?.images)} images</div>
              </div>
            )}
            {(s.location_count || 0) > 0 && (
              <div className="disk-item">
                <div className="di-val">{fmt(s.location_count)}</div>
                <div className="di-label">GPS locations extracted</div>
              </div>
            )}
            {(s.aesthetic_v2_count || 0) > 0 && (
              <div className="disk-item">
                <div className="di-val">{fmt(s.aesthetic_v2_count)}</div>
                <div className="di-label">Aesthetic v2 scores (TOPIQ+MUSIQ+LAION)</div>
              </div>
            )}
            {(v2.florence_captions?.images || 0) > 0 && (
              <div className="disk-item">
                <div className="di-val">{fmt(v2.florence_captions?.images)}</div>
                <div className="di-label">Florence-2 captions</div>
              </div>
            )}
            {(v2.open_detections?.images || 0) > 0 && (
              <div className="disk-item">
                <div className="di-val">{fmt(v2.open_detections?.rows)}</div>
                <div className="di-label">Open detections across {fmt(v2.open_detections?.images)} images</div>
              </div>
            )}
            {(v2.foreground_masks?.images || 0) > 0 && (
              <div className="disk-item">
                <div className="di-val">{fmt(v2.foreground_masks?.images)}</div>
                <div className="di-label">Foreground masks (rembg)</div>
              </div>
            )}
            {(v2.segmentation_masks?.images || 0) > 0 && (
              <div className="disk-item">
                <div className="di-val">{fmt(v2.segmentation_masks?.images)}</div>
                <div className="di-label">Segmentation masks (SAM)</div>
              </div>
            )}
            {(v2.face_identities?.images || 0) > 0 && (
              <div className="disk-item">
                <div className="di-val">{fmt(v2.face_identities?.rows)}</div>
                <div className="di-label">Face identities across {fmt(v2.face_identities?.images)} images</div>
              </div>
            )}
          </div>

          {(s.top_tags?.length || 0) > 0 && (
            <div className="signal-group" style={{ marginTop: 'var(--space-4)' }}>
              <div className="signal-group-label">Image Tags (CLIP)</div>
              <div className="tag-row">
                <Tags items={s.top_tags || []} icon={IC.eye} cat="tag" />
              </div>
            </div>
          )}

          {(s.top_open_labels?.length || 0) > 0 && (
            <div className="signal-group">
              <div className="signal-group-label">Open Detections (Grounding DINO)</div>
              <div className="tag-row">
                <Tags items={s.top_open_labels || []} icon={IC.eye} cat="detect" />
              </div>
            </div>
          )}

          {(s.aesthetic_v2_labels?.length || 0) > 0 && (
            <div className="signal-group">
              <div className="signal-group-label">Aesthetic Quality (v2)</div>
              <div className="tag-row">
                <Tags items={s.aesthetic_v2_labels || []} icon={IC.star} cat="aesthetic" />
              </div>
            </div>
          )}
        </div>
      )}

      {/* Technical — Camera Fleet */}
      <div className="section">
        <div className="signal-group-label">Camera Fleet</div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Camera</th>
                <th className="num">Images</th>
                <th>Medium</th>
                <th>Film</th>
                <th className="num">Lum</th>
                <th className="num">WB Red</th>
                <th className="num">WB Blue</th>
                <th className="num">Noise</th>
                <th className="num">Shadow%</th>
              </tr>
            </thead>
            <tbody>
              {s.cameras.map(cam => (
                <tr key={cam.body}>
                  <td style={{ fontWeight: 600 }}>{cam.body}</td>
                  <td className="num">{fmt(cam.count)}</td>
                  <td>{cam.medium}</td>
                  <td>{cam.film || '\u2014'}</td>
                  <td className="num">{cam.luminance}</td>
                  <td className="num">
                    <span className={cam.wb_r > 0.05 ? 'wb-pos' : cam.wb_r < -0.05 ? 'wb-neg' : 'wb-zero'}>
                      {cam.wb_r > 0 ? '+' : ''}{cam.wb_r.toFixed(3)}
                    </span>
                  </td>
                  <td className="num">
                    <span className={cam.wb_b < -0.05 ? 'wb-neg' : cam.wb_b > 0.05 ? 'wb-pos' : 'wb-zero'}>
                      {cam.wb_b > 0 ? '+' : ''}{cam.wb_b.toFixed(3)}
                    </span>
                  </td>
                  <td className="num">{cam.noise}</td>
                  <td className="num">{cam.shadow.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* AI Variants + Embeddings — side by side */}
      <div className="section-row">
        {s.variant_summary.length > 0 && (
          <div className="section">
            <div className="signal-group-label">AI Variants</div>
            <p style={{ fontSize: 'var(--text-sm)', color: 'var(--muted)', marginBottom: 'var(--space-3)' }}>
              {fmt(s.ai_variants_total)} total variants across {s.variant_summary.length} types
            </p>
            <div className="model-cards">
              {s.variant_summary.map(v => (
                <div key={v.type} className="model-card">
                  <div className="mc-name" style={{ textTransform: 'capitalize' }}>{v.type.replace(/_/g, ' ')}</div>
                  <div className="mc-dim">{v.total} variants &middot; {v.pct.toFixed(1)}% of collection</div>
                  <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', marginTop: 'var(--space-2)' }}>
                    <span className="badge done">{v.ok} ok</span>
                    {v.fail > 0 && <span className="badge empty">{v.fail} fail</span>}
                    {v.filtered > 0 && <span className="badge partial">{v.filtered} filtered</span>}
                    {v.pending > 0 && <span className="badge partial">{v.pending} pending</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="section">
          <div className="signal-group-label">Embeddings</div>
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--muted)', marginBottom: 'var(--space-3)' }}
           dangerouslySetInnerHTML={{ __html:
             `${fmt(s.vector_count)} images &times; 3 models &mdash; ${s.vector_size} on disk` +
             (s.vector_count >= s.total ? ' &mdash; <span class="badge done">complete</span>' :
              s.vector_count > 0 ? ` &mdash; <span class="badge partial">${(s.vector_count / s.total * 100).toFixed(1)}%</span>` :
              ' &mdash; <span class="badge empty">not started</span>')
           }}
        />
        <div className="model-cards">
          <div className="model-card">
            <div className="mc-name">DINOv2</div>
            <div className="mc-dim">768 dimensions</div>
            <div className="mc-desc">Self-supervised vision transformer. Sees composition, texture, spatial layout. The artistic eye.</div>
          </div>
          <div className="model-card">
            <div className="mc-name">SigLIP</div>
            <div className="mc-dim">768 dimensions</div>
            <div className="mc-desc">Multimodal image-text model. Sees meaning, enables text search. The semantic brain.</div>
          </div>
          <div className="model-card">
            <div className="mc-name">CLIP</div>
            <div className="mc-dim">512 dimensions</div>
            <div className="mc-desc">Subject matching model. Finds duplicates and similar scenes. The pattern matcher.</div>
          </div>
        </div>
      </div>
      </div>

    </PageShell>
  )
}

/* ── Tag Components ── */

function Tags({ items, icon, cat }: { items: { name: string; count: number }[]; icon: React.ReactNode; cat: string }) {
  if (!items?.length) return null
  return (
    <>
      {items.map(item => (
        <div key={item.name} className={`tag tag-cat-${cat}`}>
          <span className="tag-icon">{icon}</span>
          <span className="tag-label">{item.name}</span>
          <span className="tag-count">{fmt(item.count)}</span>
        </div>
      ))}
    </>
  )
}

function ColorTags({ items }: { items: { name: string; hex: string; count: number }[] }) {
  if (!items?.length) return null
  return (
    <>
      {items.map(item => (
        <div key={item.name} className="tag">
          <span className="tag-cdot" style={{ background: item.hex }} />
          <span className="tag-count">{fmt(item.count)}</span>
        </div>
      ))}
    </>
  )
}
