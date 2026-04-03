import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Login from './pages/Login';
import Signup from './pages/Signup';
import DashboardLayout from './components/DashboardLayout';
import StreamView from './pages/StreamView';
import GalleryView from './pages/GalleryView';
import SettingsView from './pages/SettingsView';
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
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/frame" element={<FrameView />} />
          <Route path="/" element={
            <PrivateRoute>
              <DashboardLayout />
            </PrivateRoute>
          }>
            <Route index element={<Navigate to="/stream" replace />} />
            <Route path="stream" element={<StreamView />} />
            <Route path="gallery" element={<GalleryView />} />
            <Route path="settings" element={<SettingsView />} />
          </Route>
        </Routes>
      </AuthProvider>
    </Router>
  );
}

export default App;
