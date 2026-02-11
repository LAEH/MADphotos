import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'

export function Layout() {
  return (
    <>
      <div className="sidebar-rail" id="sidebar-rail">
        <Sidebar />
      </div>
      <div id="content">
        <div className="main-scroll">
          <div className="main-content">
            <Outlet />
          </div>
        </div>
      </div>
    </>
  )
}
