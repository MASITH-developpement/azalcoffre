import React, { Suspense, lazy } from 'react';
import { Routes, Route, Navigate, Outlet, useLocation } from 'react-router-dom';

import { AuthProvider } from './core/auth/AuthProvider';
import { MobileConfigProvider } from './core/config/MobileConfigProvider';
import { useAuth } from './core/auth/useAuth';
import { MobileLayout } from './components/layout/MobileLayout';

// Lazy-loaded pages for code splitting
const LoginPage = lazy(() => import('./pages/LoginPage'));
const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const AgendaPage = lazy(() => import('./pages/AgendaPage'));
const ModulePage = lazy(() => import('./pages/ModulePage'));
const RecordDetailPage = lazy(() => import('./pages/RecordDetailPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));
const OfflinePage = lazy(() => import('./pages/OfflinePage'));
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'));

// Loading fallback component
function LoadingFallback(): React.ReactElement {
  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-50">
      <div className="flex flex-col items-center gap-4">
        <div className="w-10 h-10 border-4 border-primary-200 border-t-primary-600 rounded-full animate-spin" />
        <p className="text-sm text-gray-500">Chargement...</p>
      </div>
    </div>
  );
}

// Protected route wrapper with MobileLayout
function ProtectedLayout(): React.ReactElement {
  const { isAuthenticated, isLoading, user } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <LoadingFallback />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // Determine page title based on route
  const getPageTitle = (): string => {
    if (location.pathname === '/') return `Bonjour, ${user?.firstName || 'Utilisateur'}`;
    if (location.pathname === '/settings') return 'Paramètres';
    if (location.pathname === '/agenda') return 'Agenda';
    if (location.pathname === '/modules') return 'Modules';
    if (location.pathname.startsWith('/module/')) {
      const moduleId = location.pathname.split('/')[2];
      if (moduleId) {
        return moduleId.charAt(0).toUpperCase() + moduleId.slice(1);
      }
      return 'Module';
    }
    return 'AZALPLUS';
  };

  return (
    <MobileLayout
      header={{
        title: getPageTitle(),
        showBack: location.pathname !== '/',
      }}
      bottomNav={{}}
    >
      <Suspense fallback={<LoadingFallback />}>
        <Outlet />
      </Suspense>
    </MobileLayout>
  );
}

// Public route wrapper (redirects authenticated users)
function PublicRoute({ children }: { children: React.ReactNode }): React.ReactElement {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return <LoadingFallback />;
  }

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}

// Main App Routes
function AppRoutes(): React.ReactElement {
  return (
    <Suspense fallback={<LoadingFallback />}>
      <Routes>
        {/* Public routes */}
        <Route
          path="/login"
          element={
            <PublicRoute>
              <LoginPage />
            </PublicRoute>
          }
        />

        {/* Protected routes with MobileLayout */}
        <Route element={<ProtectedLayout />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/agenda" element={<AgendaPage />} />
          <Route path="/modules" element={<DashboardPage showModulesOnly />} />
          <Route path="/module/:moduleId" element={<ModulePage />} />
          <Route path="/module/:moduleId/:recordId" element={<RecordDetailPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/offline" element={<OfflinePage />} />
        </Route>

        {/* Fallback route */}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}

// Root App component
function App(): React.ReactElement {
  return (
    <AuthProvider>
      <MobileConfigProvider>
        <AppRoutes />
      </MobileConfigProvider>
    </AuthProvider>
  );
}

export default App;
