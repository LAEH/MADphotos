interface PaletteDotsProps {
  palette?: string[]
  size?: number
}

export function PaletteDots({ palette, size }: PaletteDotsProps) {
  if (!palette || palette.length === 0) return null

  const dotStyle = size
    ? { width: size + 'px', height: size + 'px' }
    : undefined

  return (
    <>
      {palette.map((hex, i) => (
        <span
          key={`${hex}-${i}`}
          className="palette-dot"
          style={{ background: hex, ...dotStyle }}
        />
      ))}
    </>
  )
}
