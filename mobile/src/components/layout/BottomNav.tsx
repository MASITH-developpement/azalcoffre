import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Icon } from '../ui/Icon';
import { useMobileConfig } from '../../core/config/MobileConfigProvider';

export interface NavItem {
  /** Navigation path */
  path: string;
  /** Display label */
  label: string;
  /** Icon name (from /assets/icons/) */
  icon: string;
  /** Badge count for notifications */
  badge?: number;
  /** Exact path matching (default: false, uses startsWith) */
  exact?: boolean;
}

export interface BottomNavProps {
  /** Callback when navigation item is clicked */
  onChange?: (path: string) => void;
  /** Additional CSS classes */
  className?: string;
  /** Inline styles */
  style?: React.CSSProperties;
}

const NAV_HEIGHT = 64;
const PRIMARY_COLOR = '#2563EB';
const INACTIVE_COLOR = '#6B7280';

export const BottomNav: React.FC<BottomNavProps> = ({
  onChange,
  className = '',
  style,
}) => {
  const { navShortcuts } = useMobileConfig();

  // Convert navShortcuts to NavItems
  const items: NavItem[] = navShortcuts.map((shortcut) => ({
    path: shortcut.path,
    label: shortcut.label,
    icon: shortcut.icon,
    exact: shortcut.path === '/',
  }));
  const navigate = useNavigate();
  const location = useLocation();

  const isActive = (item: NavItem): boolean => {
    if (item.exact) {
      return location.pathname === item.path;
    }
    return location.pathname.startsWith(item.path);
  };

  const handleNavigation = (path: string) => {
    if (onChange) {
      onChange(path);
    }
    navigate(path);
  };

  const baseStyles: React.CSSProperties = {
    height: NAV_HEIGHT,
    paddingBottom: 'env(safe-area-inset-bottom)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-around',
    paddingLeft: 'env(safe-area-inset-left)',
    paddingRight: 'env(safe-area-inset-right)',
    backgroundColor: '#FFFFFF',
    borderTop: '1px solid #E5E7EB',
    boxSizing: 'content-box',
    ...style,
  };

  const navItemStyles: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    flex: 1,
    height: '100%',
    border: 'none',
    background: 'transparent',
    cursor: 'pointer',
    padding: '8px 4px',
    position: 'relative',
    transition: 'color 0.2s ease',
  };

  const labelStyles = (active: boolean): React.CSSProperties => ({
    fontSize: 11,
    fontWeight: active ? 600 : 500,
    marginTop: 4,
    color: active ? PRIMARY_COLOR : INACTIVE_COLOR,
  });

  const badgeStyles: React.CSSProperties = {
    position: 'absolute',
    top: 4,
    right: '50%',
    transform: 'translateX(12px)',
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: '#EF4444',
    color: '#FFFFFF',
    fontSize: 10,
    fontWeight: 600,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '0 5px',
  };

  const indicatorStyles: React.CSSProperties = {
    position: 'absolute',
    top: 0,
    left: '50%',
    transform: 'translateX(-50%)',
    width: 32,
    height: 3,
    borderRadius: '0 0 3px 3px',
    backgroundColor: PRIMARY_COLOR,
  };

  return (
    <nav className={`bottom-nav ${className}`} style={baseStyles}>
      {items.map((item) => {
        const active = isActive(item);

        return (
          <button
            key={item.path}
            type="button"
            onClick={() => handleNavigation(item.path)}
            style={{
              ...navItemStyles,
              color: active ? PRIMARY_COLOR : INACTIVE_COLOR,
            }}
            aria-label={item.label}
            aria-current={active ? 'page' : undefined}
          >
            {active && <span style={indicatorStyles} />}

            <Icon
              name={item.icon}
              size={24}
              style={{ opacity: active ? 1 : 0.7 }}
            />

            <span style={labelStyles(active)}>{item.label}</span>

            {item.badge !== undefined && item.badge > 0 && (
              <span style={badgeStyles}>
                {item.badge > 99 ? '99+' : item.badge}
              </span>
            )}
          </button>
        );
      })}

      <style>{`
        .bottom-nav button:active {
          background-color: rgba(0,0,0,0.03);
        }

        .bottom-nav button:focus-visible {
          outline: 2px solid ${PRIMARY_COLOR};
          outline-offset: -2px;
        }

        @media (hover: hover) {
          .bottom-nav button:hover {
            background-color: rgba(0,0,0,0.02);
          }
        }
      `}</style>
    </nav>
  );
};

export default BottomNav;
