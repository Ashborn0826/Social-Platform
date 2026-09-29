import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import LoginPage from './pages/LoginPage'
import FeedPage from './pages/FeedPage'
import ChatsPage from './pages/ChatsPage'
import ProfilePage from './pages/ProfilePage'
import UploadPage from './pages/UploadPage'
import Layout from './components/Layout'
import { getToken } from './api'

export default function App() {
  const loc = useLocation()
  const token = getToken()

  // After login/logout the URL changes; this re-reads the token from localStorage.
  void loc.pathname

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="*"
        element={
          token ? (
            <Layout>
              <Routes>
                <Route path="/" element={<Navigate to="/feed" replace />} />
                <Route path="/feed" element={<FeedPage />} />
                <Route path="/chats" element={<ChatsPage />} />
                <Route path="/chats/:chatId" element={<ChatsPage />} />
                <Route path="/users/:userId" element={<ProfilePage />} />
                <Route path="/upload" element={<UploadPage />} />
              </Routes>
            </Layout>
          ) : (
            <Navigate to="/login" replace />
          )
        }
      />
    </Routes>
  )
}