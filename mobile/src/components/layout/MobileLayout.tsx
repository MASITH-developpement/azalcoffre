import React, { useCallback, useRef, useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Header, HeaderProps } from './Header';
import { BottomNav, BottomNavProps } from './BottomNav';

export interface MobileLayoutProps {
  /** Header configuration */
  header?: Omit<HeaderProps, 'className'>;
  /** Bottom navigation configuration */
  bottomNav?: Omit<BottomNavProps, 'className'>;
  /** Enable pull-to-refresh functionality */
  pullToRefresh?: boolean;
  /** Callback when pull-to-refresh is triggered */
  onRefresh?: () => Promise<void>;
  /** Hide header */
  hideHeader?: boolean;
  /** Hide bottom navigation */
  hideBottomNav?: boolean;
  /** Custom content instead of Outlet */
  children?: React.ReactNode;
  /** Additional CSS classes for the layout */
  className?: string;
}

const PULL_THRESHOLD = 80;
const RESISTANCE = 2.5;

export const MobileLayout: React.FC<MobileLayoutProps> = ({
  header,
  bottomNav,
  pullToRefresh = false,
  onRefresh,
  hideHeader = false,
  hideBottomNav = false,
  children,
  className = '',
}) => {
  const contentRef = useRef<HTMLDivElement>(null);
  const [isPulling, setIsPulling] = useState(false);
  const [pullDistance, setPullDistance] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const startY = useRef(0);
  const currentY = useRef(0);

  const handleTouchStart = useCallback(
    (e: React.TouchEvent) => {
      if (!pullToRefresh || !contentRef.current) return;

      // Only enable pull-to-refresh when scrolled to top
      if (contentRef.current.scrollTop === 0 && e.touches[0]) {
        startY.current = e.touches[0].clientY;
        setIsPulling(true);
      }
    },
    [pullToRefresh]
  );

  const handleTouchMove = useCallback(
    (e: React.TouchEvent) => {
      if (!isPulling || isRefreshing || !e.touches[0]) return;

      currentY.current = e.touches[0].clientY;
      const distance = Math.max(0, (currentY.current - startY.current) / RESISTANCE);

      if (distance > 0) {
        e.preventDefault();
        setPullDistance(Math.min(distance, PULL_THRESHOLD * 1.5));
      }
    },
    [isPulling, isRefreshing]
  );

  const handleTouchEnd = useCallback(async () => {
    if (!isPulling) return;

    if (pullDistance >= PULL_THRESHOLD && onRefresh) {
      setIsRefreshing(true);
      try {
        await onRefresh();
      } finally {
        setIsRefreshing(false);
      }
    }

    setIsPulling(false);
    setPullDistance(0);
    startY.current = 0;
    currentY.current = 0;
  }, [isPulling, pullDistance, onRefresh]);

  const pullProgress = Math.min(pullDistance / PULL_THRESHOLD, 1);

  return (
    <div
      className={`mobile-layout ${className}`}
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100dvh', // Dynamic viewport height for mobile browsers
        width: '100%',
        overflow: 'hidden',
        backgroundColor: '#F9FAFB',
      }}
    >
      {/* Header */}
      {!hideHeader && (
        <Header
          {...header}
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            zIndex: 50,
          }}
        />
      )}

      {/* Pull-to-refresh indicator */}
      {pullToRefresh && (pullDistance > 0 || isRefreshing) && (
        <div
          style={{
            position: 'fixed',
            top: hideHeader ? 'env(safe-area-inset-top)' : 56,
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 45,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            height: 40,
            opacity: pullProgress,
            transition: isPulling ? 'none' : 'opacity 0.2s ease',
          }}
        >
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: '50%',
              border: '3px solid #E5E7EB',
              borderTopColor: '#2563EB',
              animation: isRefreshing ? 'spin 0.8s linear infinite' : 'none',
              transform: isRefreshing ? 'none' : `rotate(${pullProgress * 360}deg)`,
            }}
          />
        </div>
      )}

      {/* Scrollable Content Area */}
      <main
        ref={contentRef}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        style={{
          flex: 1,
          overflowY: 'auto',
          overflowX: 'hidden',
          WebkitOverflowScrolling: 'touch',
          paddingTop: hideHeader
            ? 'env(safe-area-inset-top)'
            : 'calc(56px + env(safe-area-inset-top, 0px))',
          paddingBottom: hideBottomNav
            ? 'env(safe-area-inset-bottom)'
            : 'calc(64px + env(safe-area-inset-bottom, 0px))',
          paddingLeft: 'env(safe-area-inset-left)',
          paddingRight: 'env(safe-area-inset-right)',
          transform: pullToRefresh && pullDistance > 0 ? `translateY(${pullDistance}px)` : 'none',
          transition: isPulling ? 'none' : 'transform 0.2s ease',
        }}
      >
        {children ?? <Outlet />}
      </main>

      {/* Bottom Navigation */}
      {!hideBottomNav && (
        <BottomNav
          {...bottomNav}
          style={{
            position: 'fixed',
            bottom: 0,
            left: 0,
            right: 0,
            zIndex: 50,
          }}
        />
      )}

      {/* Global styles for animations */}
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }

        .mobile-layout {
          -webkit-tap-highlight-color: transparent;
        }

        .mobile-layout main::-webkit-scrollbar {
          display: none;
        }

        .mobile-layout main {
          -ms-overflow-style: none;
          scrollbar-width: none;
        }
      `}</style>
    </div>
  );
};

export default MobileLayout;
