import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import MainLayout from './layouts/MainLayout'
import Login from './pages/Login/Login'
import Cameras from './pages/Cameras/Cameras'
import Detections from './pages/Detections/Detections'
import Alerts from './pages/Alerts/Alerts'
import StolenVehicles from './pages/StolenVehicles/StolenVehicles'
import UnknownPlates from './pages/UnknownPlates/UnknownPlates'
import Users from './pages/Users/Users'
import VideoUpload from './pages/VideoUpload/VideoUpload'
import Archive from './pages/Archive/Archive'

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <MainLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Navigate to="/cameras" replace />} />
            <Route path="cameras" element={<Cameras />} />
            <Route path="detections" element={<Detections />} />
            <Route path="alerts" element={<Alerts />} />
            <Route path="stolen-vehicles" element={<StolenVehicles />} />
            <Route path="unknown-plates" element={<UnknownPlates />} />
            <Route
              path="users"
              element={
                <ProtectedRoute adminOnly>
                  <Users />
                </ProtectedRoute>
              }
            />
            <Route path="video-upload" element={<VideoUpload />} />
            <Route path="archive" element={<Archive />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
