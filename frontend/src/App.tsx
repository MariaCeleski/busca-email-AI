import { Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { ProtectedRoute } from './components/ProtectedRoute'
import { ToastContainer } from './components/ToastContainer'
import { NotificationProvider } from './contexts/NotificationContext'
import { Auth } from './pages/Auth'
import { Dashboard } from './pages/Dashboard'
import { EmailDetail } from './pages/EmailDetail'
import { ManualReview } from './pages/ManualReview'
import { Feedback } from './pages/Feedback'
import { Settings } from './pages/Settings'
import { OAuthSuccess, OAuthError } from './pages/OAuthCallback'

function App() {
  return (
    <NotificationProvider>
      <ToastContainer />
      <Routes>
        <Route path="/auth" element={<Auth />} />
        <Route path="/auth/success" element={<OAuthSuccess />} />
        <Route path="/auth/error" element={<OAuthError />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<Layout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/email/:id" element={<EmailDetail />} />
            <Route path="/review" element={<ManualReview />} />
            <Route path="/feedback" element={<Feedback />} />
            <Route path="/settings" element={<Settings />} />
          </Route>
        </Route>
      </Routes>
    </NotificationProvider>
  )
}

export default App
