/**
 * Image URL resolution for dev (local server) vs production (GCS).
 */

const GCS_BASE = 'https://storage.googleapis.com/myproject-public-assets/art/MADphotos'

const isProd = import.meta.env.PROD

/** Resolve an image URL: local in dev, GCS in production */
export function imageUrl(path: string): string {
  if (!isProd) return path
  // Map local paths to GCS paths
  // /rendered/display/jpeg/{uuid}.jpg → {GCS}/v/original/display/jpeg/{uuid}.jpg
  // /rendered/thumb/jpeg/{uuid}.jpg → {GCS}/v/original/thumb/jpeg/{uuid}.jpg
  // /rendered/mosaics/{file} → {GCS}/v/mosaics/{file}
  // /ai_variants/cartoon/{cat}/{sub}/{id}.jpg → {GCS}/v/cartoon/{id}.jpg
  if (path.startsWith('/rendered/mosaics/')) {
    return `${GCS_BASE}/v/mosaics/${path.split('/').pop()}`
  }
  if (path.startsWith('/rendered/')) {
    // /rendered/display/jpeg/xxx.jpg → v/original/display/jpeg/xxx.jpg
    const rel = path.slice('/rendered/'.length)
    return `${GCS_BASE}/v/original/${rel}`
  }
  if (path.startsWith('/ai_variants/cartoon/')) {
    // flatten to just variant_id.jpg
    const filename = path.split('/').pop()
    return `${GCS_BASE}/v/cartoon/${filename}`
  }
  if (path.startsWith('/ai_variants/blind_test/')) {
    const filename = path.split('/').pop()
    return `${GCS_BASE}/v/blind/${filename}`
  }
  return path
}

/** Static data URL: /api/stats → data/stats.json in production */
export function dataUrl(apiPath: string): string {
  if (!isProd) return apiPath
  const map: Record<string, string> = {
    '/api/stats': 'data/stats.json',
    '/api/journal': 'data/journal.json',
    '/api/instructions': 'data/instructions.json',
    '/api/mosaics': 'data/mosaics.json',
    '/api/cartoon': 'data/cartoon.json',
    '/api/blind-test': 'data/blind_test.json',
  }
  const staticPath = map[apiPath]
  if (staticPath) return `${import.meta.env.BASE_URL}${staticPath}`
  return apiPath
}
