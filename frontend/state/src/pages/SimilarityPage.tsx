import { useFetch } from '../hooks/useFetch'
import { Footer } from '../components/layout/Footer'

interface Stats {
  vector_count: number
  vector_size: string
  total: number
}

export function SimilarityPage() {
  const { data } = useFetch<Stats>('/api/stats')

  const models = [
    {
      name: 'DINOv2',
      dims: 768,
      provider: 'Meta FAIR',
      color: 'var(--system-blue)',
      desc: 'Self-supervised vision transformer trained on 142M images. Captures composition, texture, spatial layout, and visual structure. The artistic eye — finds images that feel similar even when subjects differ.',
      finds: 'Composition matches, texture similarities, spatial layout patterns',
    },
    {
      name: 'SigLIP',
      dims: 768,
      provider: 'Google',
      color: 'var(--system-purple)',
      desc: 'Sigmoid-loss image-language pre-training. Maps images and text into a shared 768-dimensional space. Enables natural language search across the entire collection.',
      finds: 'Semantic meaning, text-to-image search, conceptual similarity',
    },
    {
      name: 'CLIP',
      dims: 512,
      provider: 'OpenAI',
      color: 'var(--system-green)',
      desc: 'Contrastive language-image pre-training. 512-dimensional embeddings optimized for cross-modal matching. Excels at finding the same subject across different shots.',
      finds: 'Subject matching, duplicate detection, scene recognition',
    },
  ]

  return (
    <>
      <div style={{ marginBottom: 'var(--space-8)' }}>
        <h1 style={{
          fontFamily: 'var(--font-display)', fontSize: 'var(--text-3xl)', fontWeight: 700,
          letterSpacing: 'var(--tracking-tight)', marginBottom: 'var(--space-2)',
        }}>
          Similarity Search
        </h1>
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--muted)', lineHeight: 'var(--leading-relaxed)' }}>
          Three neural embedding models encode every image into high-dimensional vectors.
          Nearest-neighbor search in these spaces finds visually and semantically similar photos.
        </p>

        {data && (
          <div style={{
            display: 'flex', gap: 'var(--space-6)', marginTop: 'var(--space-4)',
          }}>
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, fontFamily: 'var(--font-display)' }}>
                {data.vector_count.toLocaleString()}
              </span>
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: 'var(--tracking-caps)' }}>
                Embedded images
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, fontFamily: 'var(--font-display)' }}>
                3
              </span>
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: 'var(--tracking-caps)' }}>
                Models
              </span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, fontFamily: 'var(--font-display)' }}>
                {data.vector_size}
              </span>
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: 'var(--tracking-caps)' }}>
                On disk
              </span>
            </div>
          </div>
        )}
      </div>

      {/* How it works */}
      <div style={{ marginBottom: 'var(--space-8)' }}>
        <div style={{
          fontFamily: 'var(--font-display)', fontSize: 'var(--text-xl)', fontWeight: 700,
          marginBottom: 'var(--space-4)', paddingBottom: 'var(--space-3)',
          borderBottom: '1px solid var(--border)', position: 'relative',
        }}>
          How It Works
        </div>
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: 'var(--space-4)',
        }}>
          {[
            { step: '1', title: 'Encode', desc: 'Each image passes through all 3 models, producing embedding vectors of 512-768 dimensions.' },
            { step: '2', title: 'Index', desc: 'Vectors are stored in LanceDB with IVF-PQ indexing for sub-millisecond nearest-neighbor lookup.' },
            { step: '3', title: 'Query', desc: 'Pick any photo. The system finds the K closest neighbors in each embedding space.' },
            { step: '4', title: 'Blend', desc: 'Results from all models are merged with configurable weights for a balanced similarity view.' },
          ].map(s => (
            <div key={s.step} style={{
              background: 'var(--card-bg)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)', padding: 'var(--space-4)',
            }}>
              <div style={{
                width: 28, height: 28, borderRadius: 'var(--radius-full)',
                background: 'var(--hover-overlay)', display: 'flex',
                alignItems: 'center', justifyContent: 'center',
                fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)',
                fontWeight: 700, marginBottom: 'var(--space-2)',
              }}>
                {s.step}
              </div>
              <div style={{ fontWeight: 700, fontSize: 'var(--text-sm)', marginBottom: 'var(--space-1)' }}>{s.title}</div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)', lineHeight: 'var(--leading-relaxed)' }}>{s.desc}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Model cards */}
      <div style={{ marginBottom: 'var(--space-8)' }}>
        <div style={{
          fontFamily: 'var(--font-display)', fontSize: 'var(--text-xl)', fontWeight: 700,
          marginBottom: 'var(--space-4)', paddingBottom: 'var(--space-3)',
          borderBottom: '1px solid var(--border)',
        }}>
          Embedding Models
        </div>
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: 'var(--space-4)',
        }}>
          {models.map(m => (
            <div key={m.name} style={{
              background: 'var(--card-bg)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)', padding: 'var(--space-5)',
              borderTop: `3px solid ${m.color}`,
            }}>
              <div style={{ fontWeight: 700, fontSize: 'var(--text-base)' }}>{m.name}</div>
              <div style={{
                fontSize: 'var(--text-xs)', color: 'var(--muted)', fontFamily: 'var(--font-mono)',
                marginTop: 2,
              }}>
                {m.dims} dims &middot; {m.provider}
              </div>
              <div style={{
                fontSize: 'var(--text-xs)', color: 'var(--muted)', marginTop: 'var(--space-3)',
                lineHeight: 'var(--leading-relaxed)',
              }}>
                {m.desc}
              </div>
              <div style={{
                fontSize: 'var(--text-xs)', marginTop: 'var(--space-3)',
                padding: 'var(--space-2) var(--space-3)', borderRadius: 'var(--radius-sm)',
                background: 'var(--hover-overlay)',
              }}>
                <span style={{ fontWeight: 600 }}>Finds: </span>
                <span style={{ color: 'var(--fg-secondary)' }}>{m.finds}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div style={{
        background: 'var(--card-bg)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)', padding: 'var(--space-8)',
        textAlign: 'center',
      }}>
        <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, marginBottom: 'var(--space-2)' }}>
          Interactive Explorer
        </div>
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--muted)', maxWidth: 480, margin: '0 auto' }}>
          The interactive similarity explorer requires the local backend with LanceDB vector store.
          Run <code style={{
            background: 'var(--hover-overlay)', padding: '2px var(--space-2)',
            fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)',
            borderRadius: 'var(--radius-sm)',
          }}>python3 backend/dashboard.py --serve</code> to enable live vector search.
        </p>
      </div>

      <Footer />
    </>
  )
}
