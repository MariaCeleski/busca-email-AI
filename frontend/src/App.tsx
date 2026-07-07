import { Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Dashboard } from './pages/Dashboard'
import { EmailDetail } from './pages/EmailDetail'
import { ManualReview } from './pages/ManualReview'
import { Settings } from './pages/Settings'

function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/email/:id" element={<EmailDetail />} />
        <Route path="/review" element={<ManualReview />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
    </Routes>
  )
}

export default App
