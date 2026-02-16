import { useState } from 'react'
import { PageShell } from '../components/layout/PageShell'
import './ScreensPage.css'

interface Device {
  displayName: string
  slug: string
  width: number
  height: number
  type: 'laptop' | 'tablet' | 'mobile'
}

const DEVICES: Device[] = [
  // Laptops
  { displayName: 'MacBook Pro 16"', slug: 'macbook-pro-16', width: 1728, height: 997, type: 'laptop' },
  { displayName: 'MacBook Air 13"', slug: 'macbook-air-13', width: 1440, height: 780, type: 'laptop' },

  // Tablets - portrait
  { displayName: 'iPad Pro 12.9"', slug: 'ipad-pro-12-portrait', width: 1024, height: 1272, type: 'tablet' },
  { displayName: 'iPad Air 11"', slug: 'ipad-air-11-portrait', width: 820, height: 1086, type: 'tablet' },
  { displayName: 'iPad Mini', slug: 'ipad-mini-portrait', width: 744, height: 1039, type: 'tablet' },

  // Tablets - landscape
  { displayName: 'iPad 10.9" landscape', slug: 'ipad-10-landscape', width: 1080, height: 716, type: 'tablet' },
  { displayName: 'iPad Mini landscape', slug: 'ipad-mini-landscape', width: 1133, height: 650, type: 'tablet' },

  // Mobile
  { displayName: 'iPhone 17 Pro Max', slug: 'iphone-17-pro-max', width: 440, height: 852, type: 'mobile' },
  { displayName: 'iPhone 15 Pro', slug: 'iphone-15-pro', width: 393, height: 748, type: 'mobile' },
  { displayName: 'iPhone SE', slug: 'iphone-se', width: 375, height: 563, type: 'mobile' },
  { displayName: 'Pixel 8 Pro', slug: 'pixel-8-pro', width: 412, height: 811, type: 'mobile' },
]

export function ScreensPage() {
  const [filterType, setFilterType] = useState<'all' | Device['type']>('all')

  const filteredDevices = DEVICES.filter(d =>
    filterType === 'all' || d.type === filterType
  )

  return (
    <PageShell
      title="Device Screens"
      subtitle="ISIT view screenshots across devices - actual viewport after browser UI"
    >
      <div className="screens-controls">
        <button
          className={filterType === 'all' ? 'active' : ''}
          onClick={() => setFilterType('all')}
        >
          All ({DEVICES.length})
        </button>
        <button
          className={filterType === 'laptop' ? 'active' : ''}
          onClick={() => setFilterType('laptop')}
        >
          Laptops
        </button>
        <button
          className={filterType === 'tablet' ? 'active' : ''}
          onClick={() => setFilterType('tablet')}
        >
          Tablets
        </button>
        <button
          className={filterType === 'mobile' ? 'active' : ''}
          onClick={() => setFilterType('mobile')}
        >
          Mobile
        </button>
      </div>

      <div className="devices-grid">
        {filteredDevices.map((device) => {
          const scale = device.type === 'laptop' ? 0.25 : device.type === 'tablet' ? 0.35 : 0.5;
          const scaledWidth = device.width * scale;
          const scaledHeight = device.height * scale;

          return (
            <div key={device.slug} className="device-card">
              <div className={`device-bezel ${device.type}`}>
                <img
                  src={`/system/screenshots/devices/${device.slug}.png`}
                  alt={`${device.displayName} screenshot`}
                  style={{
                    width: scaledWidth,
                    height: scaledHeight,
                    display: 'block',
                  }}
                />
              </div>

              <div className="device-info">
                <h3>{device.displayName}</h3>
                <div className="device-viewport">{device.width} × {device.height}</div>
              </div>
            </div>
          )
        })}
      </div>
    </PageShell>
  )
}
