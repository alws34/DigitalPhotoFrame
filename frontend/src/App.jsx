import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import ErrorBoundary from './components/ErrorBoundary';
import Login from './pages/Login';
import Signup from './pages/Signup';
import DashboardLayout from './components/DashboardLayout';
import StreamView from './pages/StreamView';
import GalleryView from './pages/GalleryView';
import SettingsView from './pages/SettingsView';
import AlbumsView from './pages/AlbumsView';
import ResetPassword from './pages/ResetPassword';
import FrameView from './pages/FrameView';

const PrivateRoute = ({ children }) => {
  const { user, loading } = useAuth();
  if (loading) {
    return <div style={{ display: 'grid', placeItems: 'center', height: '100vh' }}>Loading...</div>;
  }
  return user ? children : <Navigate to="/login" />;
};

function App() {
  return (
    <Router>
      <AuthProvider>
        <ThemeProvider>
          <Routes>
            <Route path="/login" element={<ErrorBoundary><Login /></ErrorBoundary>} />
            <Route path="/signup" element={<ErrorBoundary><Signup /></ErrorBoundary>} />
            <Route path="/reset-password" element={<ErrorBoundary><ResetPassword /></ErrorBoundary>} />
            <Route path="/frame" element={<ErrorBoundary><FrameView /></ErrorBoundary>} />
            <Route path="/" element={
              <PrivateRoute>
                <DashboardLayout />
              </PrivateRoute>
            }>
              <Route index element={<Navigate to="/stream" replace />} />
              <Route path="stream" element={<ErrorBoundary><StreamView /></ErrorBoundary>} />
              <Route path="gallery" element={<ErrorBoundary><GalleryView /></ErrorBoundary>} />
              <Route path="albums" element={<ErrorBoundary><AlbumsView /></ErrorBoundary>} />
              <Route path="settings" element={<ErrorBoundary><SettingsView /></ErrorBoundary>} />
            </Route>
          </Routes>
        </ThemeProvider>
      </AuthProvider>
    </Router>
  );
}

export default App;
