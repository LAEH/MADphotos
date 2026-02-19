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
  v2_signals: Record<string, { rows: number; images: number }>
  aesthetic_v2_count: number
  aesthetic_v2_labels?: { name: string; count: number }[]
  top_tags?: { name: string; count: number }[]
  top_open_labels?: { name: string; count: number }[]
  picks?: {
    portrait: number
    landscape: number
    total: number
    photography: number
    generated: number
    votes_total: number
    votes_accept: number
    votes_reject: number
    by_device: { device: string; accepts: number; rejects: number }[]
  }
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
  const tinder = s.feedback?.tinder
  const couple = s.feedback?.couple

  const faceProcessed = sigFD.processed || sigFD.images
  const poseImages = v2.pose_detections?.images || 0

  /* ── Experiences: what Show views exist and what powers them ── */
  const experiences = [
    { name: 'Bento', desc: 'Aesthetic-ranked masonry grid with color browsing', models: ['NIMA', 'Gemini 2.5 Pro', 'Places365', 'K-means LAB'], stat: `avg ${s.aesthetic_avg?.toFixed(1) || '\u2014'}` },
    { name: 'Couple', desc: '13 pairing strategies across all signals', models: ['NIMA', 'Gemini', 'Places365', 'Depth Anything', 'Style Net'], stat: `${fmt(s.total_signals)} signals` },
    { name: 'Boom', desc: 'Themed sets by vibe, scene, and palette', models: ['Gemini 2.5 Pro', 'NIMA', 'K-means LAB'], stat: '24 sets' },
    { name: 'Caption', desc: 'AI-generated photo stories', models: ['BLIP', 'Florence-2'], stat: `${fmt(s.caption_count)} captions` },
    { name: 'ISIT', desc: 'Binary swipe by scene and vibe', models: ['Places365', 'Gemini 2.5 Pro', 'CLIP Tags'], stat: `${fmt(v2.image_tags?.images || 0)} tagged` },
  ]

  /* ── All 24 models ── */
  const models: { n: string; name: string; tech: string; count: number; of?: number; v2?: boolean }[] = [
    { n: '01', name: 'Gemini 2.5 Pro', tech: 'Vertex AI', count: s.analyzed },
    { n: '02', name: 'Pixel Analysis', tech: 'Pillow + NumPy', count: s.pixel_analyzed },
    { n: '03', name: 'DINOv2', tech: 'Meta FAIR ViT-B/14', count: s.vector_count },
    { n: '04', name: 'SigLIP', tech: 'Google ViT-B/16', count: s.vector_count },
    { n: '05', name: 'CLIP', tech: 'OpenAI ViT-B/32', count: s.vector_count },
    { n: '06', name: 'YuNet', tech: 'OpenCV ONNX', count: faceProcessed },
    { n: '07', name: 'YOLOv8n', tech: 'Ultralytics COCO', count: sigOD.processed || sigOD.images },
    { n: '08', name: 'NIMA', tech: 'MobileNet', count: s.aesthetic_count },
    { n: '09', name: 'Depth Anything v2', tech: 'HF ViT', count: s.depth_count },
    { n: '10', name: 'Places365', tech: 'MIT ResNet-50', count: s.scene_count },
    { n: '11', name: 'Style Net', tech: 'Custom CNN', count: s.style_count },
    { n: '12', name: 'BLIP', tech: 'Salesforce ViT+LLM', count: s.caption_count },
    { n: '13', name: 'EasyOCR', tech: 'CRAFT + CRNN', count: s.ocr_images || 0 },
    { n: '14', name: 'Facial Emotions', tech: 'FER CNN', count: s.emotion_count || 0, of: sigFD.images },
    { n: '15', name: 'Enhancement', tech: 'Camera-aware', count: s.enhancement_count },
    { n: '16', name: 'K-means LAB', tech: 'scikit-learn', count: sigDC.images },
    { n: '17', name: 'EXIF Parser', tech: 'Pillow + piexif', count: sigEX.images },
    { n: '18', name: 'Aesthetic v2', tech: 'TOPIQ+MUSIQ+LAION', count: s.aesthetic_v2_count || 0, v2: true },
    { n: '19', name: 'CLIP Tags', tech: 'Zero-shot \u00D765', count: v2.image_tags?.images || 0, v2: true },
    { n: '20', name: 'Saliency', tech: 'Spectral Residual', count: v2.saliency_maps?.images || 0, v2: true },
    { n: '21', name: 'YOLOv8n-pose', tech: 'Ultralytics', count: poseImages, of: sigOD.images || s.total, v2: true },
    { n: '22', name: 'Florence-2', tech: 'Microsoft 770M', count: v2.florence_captions?.images || 0, v2: true },
    { n: '23', name: 'Grounding DINO', tech: 'IDEA open-vocab', count: v2.open_detections?.images || 0, v2: true },
    { n: '24', name: 'rembg', tech: 'U2-Net', count: v2.foreground_masks?.images || 0, v2: true },
  ]
  const modelCount = models.length

  return (
    <PageShell title="Status" subtitle={<><span className="live-dot" />{s.timestamp}</>}>

      {/* ═══ OVERVIEW ═══ */}
      <Card>
        <div className="overview-grid" style={{ marginBottom: 0 }}>
          <div className="ov-card">
            <div className="ov-val">{fmt(s.total)}</div>
            <div className="ov-label">Photos</div>
          </div>
          <div className="ov-card">
            <div className="ov-val">{fmt(s.picks?.photography || 0)}</div>
            <div className="ov-label">Photography</div>
          </div>
          <div className="ov-card">
            <div className="ov-val">{fmt(s.picks?.generated || 0)}</div>
            <div className="ov-label">Generated</div>
          </div>
          <div className="ov-card">
            <div className="ov-val">{fmt(s.picks?.total || 0)}</div>
            <div className="ov-label">Total Picks</div>
          </div>
          <div className="ov-card">
            <div className="ov-val">{s.models_complete}/{modelCount}</div>
            <div className="ov-label">Models</div>
          </div>
          <div className="ov-card">
            <div className="ov-val">{fmt(s.ai_variants_total)}</div>
            <div className="ov-label">Variants</div>
          </div>
          <div className="ov-card">
            <div className="ov-val">{fmt(tinder?.total || 0)}</div>
            <div className="ov-label">Votes</div>
          </div>
          <div className="ov-card">
            <div className="ov-val">{s.total_rendered_human}</div>
            <div className="ov-label">Storage</div>
          </div>
        </div>
      </Card>

      {/* ═══ EXPERIENCES — what the signals enable ═══ */}
      <div className="section">
        <div className="section-title">Experiences</div>
      </div>
      <div className="section">
        <div className="model-cards">
          {experiences.map(exp => (
            <div key={exp.name} className="model-card">
              <div className="mc-name">{exp.name}</div>
              <div className="mc-dim">{exp.desc}</div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)', marginTop: 'var(--space-1)' }}>
                {exp.models.join(' \u00B7 ')}
              </div>
              <div style={{ marginTop: 'var(--space-2)', fontWeight: 600, fontSize: 'var(--text-sm)' }}>
                {exp.stat}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ═══ INTELLIGENCE — models & signals ═══ */}
      <div className="section">
        <div className="section-title">Intelligence</div>
      </div>

      <div className="section">
        <div className="signal-group-label">{modelCount} Models &mdash; {s.models_complete} complete</div>
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

      {/* AI Variants */}
      {s.variant_summary.length > 0 && (
        <div className="section">
          <div className="signal-group-label">AI Variants &mdash; {fmt(s.ai_variants_total)} generated</div>
          <div className="model-cards">
            {s.variant_summary.map(v => (
              <div key={v.type} className="model-card">
                <div className="mc-name" style={{ textTransform: 'capitalize' }}>{v.type.replace(/_/g, ' ')}</div>
                <div className="mc-dim">{v.total} variants &middot; {v.pct.toFixed(1)}%</div>
                <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', marginTop: 'var(--space-2)' }}>
                  <span className="badge done">{v.ok} ok</span>
                  {v.fail > 0 && <span className="badge empty">{v.fail} fail</span>}
                  {v.filtered > 0 && <span className="badge partial">{v.filtered} filtered</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ═══ CURATION — human signals ═══ */}
      <div className="section">
        <div className="section-title">Curation</div>
      </div>

      <div className="section">
        <div className="disk-row">
          {s.picks && (
            <>
              <div className="disk-item">
                <div className="di-val">{fmt(s.picks.total)}</div>
                <div className="di-label">Total picks ({fmt(s.picks.portrait)}P &middot; {fmt(s.picks.landscape)}L)</div>
              </div>
              <div className="disk-item">
                <div className="di-val">{fmt(s.picks.photography)}</div>
                <div className="di-label">Photography</div>
              </div>
              <div className="disk-item">
                <div className="di-val">{fmt(s.picks.generated)}</div>
                <div className="di-label">Generated</div>
              </div>
              <div className="disk-item">
                <div className="di-val">{s.total > 0 ? (s.picks.total / s.total * 100).toFixed(1) + '%' : '\u2014'}</div>
                <div className="di-label">of collection</div>
              </div>
            </>
          )}
          {tinder && tinder.total > 0 && (
            <div className="disk-item">
              <div className="di-val">{fmt(tinder.total)}</div>
              <div className="di-label">Tinder votes ({Math.round(tinder.accepts / tinder.total * 100)}% accept)</div>
            </div>
          )}
          {couple && couple.likes > 0 && (
            <div className="disk-item">
              <div className="di-val">{fmt(couple.likes)}</div>
              <div className="di-label">Couple likes</div>
            </div>
          )}
          {s.picks && s.picks.votes_total > 0 && (
            <div className="disk-item">
              <div className="di-val">{fmt(s.picks.votes_total)}</div>
              <div className="di-label">Re-curation ({fmt(s.picks.votes_reject)} removed)</div>
            </div>
          )}
        </div>
      </div>

      {/* ═══ INFRASTRUCTURE ═══ */}
      <div className="section">
        <div className="section-title">Infrastructure</div>
      </div>

      <div className="section-row">
        <div className="section">
          <div className="signal-group-label">Storage</div>
          <div className="disk-row">
            <div className="disk-item">
              <div className="di-val">{s.total_rendered_human}</div>
              <div className="di-label">Rendered ({fmt(s.total_tier_files)} files)</div>
            </div>
            <div className="disk-item">
              <div className="di-val">{s.db_size}</div>
              <div className="di-label">Database</div>
            </div>
            <div className="disk-item">
              <div className="di-val">{s.vector_size}</div>
              <div className="di-label">Vectors (3 models)</div>
            </div>
            {s.gcs_uploads > 0 && (
              <div className="disk-item">
                <div className="di-val">{fmt(s.gcs_uploads)}</div>
                <div className="di-label">GCS uploads</div>
              </div>
            )}
          </div>
        </div>

        <div className="section">
          <div className="signal-group-label">Cameras</div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Body</th>
                  <th className="num">Photos</th>
                  <th>Medium</th>
                </tr>
              </thead>
              <tbody>
                {s.cameras.map(cam => (
                  <tr key={cam.body}>
                    <td style={{ fontWeight: 600 }}>{cam.body}</td>
                    <td className="num">{fmt(cam.count)}</td>
                    <td>{cam.medium}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {s.runs.length > 0 && (
        <div className="section">
          <div className="signal-group-label">Pipeline</div>
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

    </PageShell>
  )
}
