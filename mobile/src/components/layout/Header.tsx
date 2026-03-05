import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, type LucideIcon } from 'lucide-react';

export interface HeaderAction {
  /** Icon component from lucide-react */
  icon: LucideIcon;
  /** Action label for accessibility */
  label: string;
  /** Click handler */
  onClick: () => void;
  /** Disabled state */
  disabled?: boolean;
  /** Badge count (shows notification badge) */
  badge?: number;
}

export interface HeaderProps {
  /** Page title (displayed center) */
  title?: string;
  /** Show back button */
  showBack?: boolean;
  /** Custom back action (defaults to navigate(-1)) */
  onBack?: () => void;
  /** Back button destination path */
  backTo?: string;
  /** Right action buttons */
  actions?: HeaderAction[];
  /** Transparent variant (for overlay on images) */
  transparent?: boolean;
  /** Custom left content (replaces back button) */
  leftContent?: React.ReactNode;
  /** Custom center content (replaces title) */
  centerContent?: React.ReactNode;
  /** Custom right content (replaces actions) */
  rightContent?: React.ReactNode;
  /** Additional CSS classes */
  className?: string;
  /** Inline styles */
  style?: React.CSSProperties;
}

const HEADER_HEIGHT = 56;
const PRIMARY_COLOR = '#2563EB';

export const Header: React.FC<HeaderProps> = ({
  title,
  showBack = false,
  onBack,
  backTo,
  actions = [],
  transparent = false,
  leftContent,
  centerContent,
  rightContent,
  className = '',
  style,
}) => {
  const navigate = useNavigate();

  const handleBack = () => {
    if (onBack) {
      onBack();
    } else if (backTo) {
      navigate(backTo);
    } else {
      navigate(-1);
    }
  };

  const baseStyles: React.CSSProperties = {
    height: HEADER_HEIGHT,
    paddingTop: 'env(safe-area-inset-top)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingLeft: 'max(8px, env(safe-area-inset-left))',
    paddingRight: 'max(8px, env(safe-area-inset-right))',
    backgroundColor: transparent ? 'transparent' : '#FFFFFF',
    borderBottom: transparent ? 'none' : '1px solid #E5E7EB',
    boxSizing: 'border-box',
    ...style,
  };

  const buttonStyles: React.CSSProperties = {
    width: 40,
    height: 40,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    border: 'none',
    background: 'transparent',
    borderRadius: '50%',
    cursor: 'pointer',
    color: transparent ? '#FFFFFF' : '#374151',
    position: 'relative',
    transition: 'background-color 0.2s ease',
  };

  const titleStyles: React.CSSProperties = {
    flex: 1,
    textAlign: 'center',
    fontSize: 18,
    fontWeight: 600,
    color: transparent ? '#FFFFFF' : '#111827',
    margin: 0,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    padding: '0 8px',
  };

  const badgeStyles: React.CSSProperties = {
    position: 'absolute',
    top: 4,
    right: 4,
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: '#EF4444',
    color: '#FFFFFF',
    fontSize: 11,
    fontWeight: 600,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '0 5px',
  };

  return (
    <header className={`mobile-header ${className}`} style={baseStyles}>
      {/* Left Section */}
      <div style={{ display: 'flex', alignItems: 'center', minWidth: 48 }}>
        {leftContent ? (
          leftContent
        ) : showBack ? (
          <button
            type="button"
            onClick={handleBack}
            style={buttonStyles}
            aria-label="Go back"
          >
            <ArrowLeft size={24} />
          </button>
        ) : (
          <div style={{ width: 40 }} />
        )}
      </div>

      {/* Center Section */}
      <div style={{ flex: 1, overflow: 'hidden' }}>
        {centerContent ? (
          centerContent
        ) : title ? (
          <h1 style={titleStyles}>{title}</h1>
        ) : null}
      </div>

      {/* Right Section */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, minWidth: 48, justifyContent: 'flex-end' }}>
        {rightContent
          ? rightContent
          : actions.map((action, index) => {
              const IconComponent = action.icon;
              return (
                <button
                  key={index}
                  type="button"
                  onClick={action.onClick}
                  disabled={action.disabled}
                  style={{
                    ...buttonStyles,
                    opacity: action.disabled ? 0.5 : 1,
                    cursor: action.disabled ? 'not-allowed' : 'pointer',
                  }}
                  aria-label={action.label}
                >
                  <IconComponent size={24} />
                  {action.badge !== undefined && action.badge > 0 && (
                    <span style={badgeStyles}>
                      {action.badge > 99 ? '99+' : action.badge}
                    </span>
                  )}
                </button>
              );
            })}
        {actions.length === 0 && !rightContent && <div style={{ width: 40 }} />}
      </div>

      <style>{`
        .mobile-header button:active {
          background-color: ${transparent ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.05)'};
        }

        .mobile-header button:focus-visible {
          outline: 2px solid ${PRIMARY_COLOR};
          outline-offset: 2px;
        }
      `}</style>
    </header>
  );
};

export default Header;
