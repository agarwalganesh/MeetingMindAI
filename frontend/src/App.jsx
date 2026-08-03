import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Dashboard from './pages/Dashboard';
import MeetingDetails from './pages/MeetingDetails';
import AdminPanel from './pages/AdminPanel';

// Protected Route Wrapper
const PrivateRoute = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();
  
  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }
  
  return isAuthenticated ? children : <Navigate to="/login" replace />;
};

// Admin Route Wrapper
const AdminRoute = ({ children }) => {
  const { isAuthenticated, isAdmin, loading } = useAuth();
  
  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }
  
  return isAuthenticated && isAdmin ? children : <Navigate to="/" replace />;
};

// Layout Injector
const LayoutWrapper = ({ children }) => {
  return <Layout>{children}</Layout>;
};

function App() {
  return (
    <ErrorBoundary>
    <ThemeProvider>
    <Router>
      <AuthProvider>
        <Routes>
          {/* Public Routes */}
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />

          {/* Private Core Routes */}
          <Route path="/" element={
            <PrivateRoute>
              <LayoutWrapper>
                <Dashboard />
              </LayoutWrapper>
            </PrivateRoute>
          } />
          
          <Route path="/meetings" element={
            <PrivateRoute>
              <LayoutWrapper>
                <Dashboard />
              </LayoutWrapper>
            </PrivateRoute>
          } />

          <Route path="/meeting/:id" element={
            <PrivateRoute>
              <LayoutWrapper>
                <MeetingDetails />
              </LayoutWrapper>
            </PrivateRoute>
          } />

          {/* Admin Locked Routes */}
          <Route path="/admin" element={
            <AdminRoute>
              <LayoutWrapper>
                <AdminPanel />
              </LayoutWrapper>
            </AdminRoute>
          } />

          {/* Fallback Catch-all */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </Router>
    </ThemeProvider>
    </ErrorBoundary>
  );
}

export default App;
