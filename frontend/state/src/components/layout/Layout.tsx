import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'

export function Layout() {
  return (
    <div className="app-layout">
      <Sidebar />
      <div className="main-scroll">
        <div className="main-content">
          <Outlet />
        </div>
      </div>
    </div>
  )
}
