import type { Photo } from '../../types/photo'

interface LabelData {
  labels?: { label: string; category: string }[]
}

interface ActiveFilter {
  type: string
  value: string
}

interface IsitPillsProps {
  photo: Photo | null
  labelsData: Record<string, LabelData> | null
  isMobile: boolean
  activeFilter: ActiveFilter | null
  onFilterSignal: (type: string, value: string) => void
}

export function IsitPills({ photo, labelsData, isMobile, activeFilter, onFilterSignal }: IsitPillsProps) {
  if (!photo) return <div className="isit-pills-display" />

  const pills: { text: string; category: string; signalType: string; signalValue: string }[] = []

  /* Photo label pills from photo_labels.json */
  if (labelsData && labelsData[photo.id]) {
    const data = labelsData[photo.id]
    const maxPills = isMobile ? 2 : 3
    if (data.labels && data.labels.length > 0) {
      data.labels.slice(0, maxPills).forEach(label => {
        pills.push({
          text: label.label.charAt(0).toUpperCase() + label.label.slice(1),
          category: label.category,
          signalType: 'label',
          signalValue: label.label,
        })
      })
    }
  }

  /* Signal pills from photo metadata */
  const maxSignals = isMobile ? 2 : 3
  const addedSignals: string[] = []

  /* Priority 1: Consensus tags */
  if (photo.consensus && photo.consensus.length > 0 && addedSignals.length < maxSignals) {
    const tag = photo.consensus[0]
    pills.push({ text: tag, category: 'style', signalType: 'consensus', signalValue: tag })
    addedSignals.push(tag)
  }

  /* Priority 2: Scene or emotion */
  if (photo.scene && addedSignals.length < maxSignals) {
    pills.push({ text: photo.scene, category: 'scene', signalType: 'scene', signalValue: photo.scene })
    addedSignals.push(photo.scene)
  } else if (photo.emotion && addedSignals.length < maxSignals) {
    pills.push({ text: photo.emotion, category: 'mood', signalType: 'emotion', signalValue: photo.emotion })
    addedSignals.push(photo.emotion)
  }

  /* Priority 3: Top vibe or time/grading */
  if (photo.vibes && photo.vibes.length > 0 && addedSignals.length < maxSignals) {
    const vibe = photo.vibes[0]
    pills.push({ text: vibe, category: 'vibe', signalType: 'vibe', signalValue: vibe })
    addedSignals.push(vibe)
  } else if (photo.time && addedSignals.length < maxSignals) {
    pills.push({ text: photo.time, category: 'time', signalType: 'time', signalValue: photo.time })
    addedSignals.push(photo.time)
  } else if (photo.grading && addedSignals.length < maxSignals) {
    pills.push({ text: photo.grading, category: 'technique', signalType: 'grading', signalValue: photo.grading })
    addedSignals.push(photo.grading)
  }

  if (pills.length === 0) return <div className="isit-pills-display" />

  return (
    <div className="isit-pills-display">
      <div className="isit-gorgeous-pills">
        {pills.map((pill, i) => {
          const isActive = activeFilter &&
            activeFilter.type === pill.signalType &&
            activeFilter.value === pill.signalValue
          return (
            <span
              key={`${pill.signalType}-${pill.signalValue}-${i}`}
              className={`gorgeous-pill${isActive ? ' pill-active' : ''}`}
              data-category={pill.category}
              onClick={(e) => {
                e.stopPropagation()
                onFilterSignal(pill.signalType, pill.signalValue)
              }}
            >
              {pill.text}
            </span>
          )
        })}
      </div>
    </div>
  )
}
