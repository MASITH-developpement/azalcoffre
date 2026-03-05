import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Plus, X, type LucideIcon } from 'lucide-react';

export interface SpeedDialAction {
  /** Icon component from lucide-react */
  icon: LucideIcon;
  /** Action label (shown as tooltip) */
  label: string;
  /** Click handler */
  onClick: () => void;
  /** Optional color for the mini FAB */
  color?: string;
}

export interface FloatingActionButtonProps {
  /** Primary action icon */
  icon?: LucideIcon;
  /** Primary action click handler */
  onClick?: () => void;
  /** Speed dial actions (shows when expanded) */
  speedDialActions?: SpeedDialAction[];
  /** Button color (default: primary blue) */
  color?: string;
  /** Button size in pixels */
  size?: number;
  /** Position from bottom */
  bottom?: number;
  /** Position from right */
  right?: number;
  /** Accessibility label */
  ariaLabel?: string;
  /** Disabled state */
  disabled?: boolean;
  /** Extended FAB with label */
  extended?: boolean;
  /** Label text for extended FAB */
  label?: string;
  /** Additional CSS classes */
  className?: string;
}

const PRIMARY_COLOR = '#2563EB';
const MINI_FAB_SIZE = 48;
const SPEED_DIAL_GAP = 16;

export const FloatingActionButton: React.FC<FloatingActionButtonProps> = ({
  icon: Icon = Plus,
  onClick,
  speedDialActions = [],
  color = PRIMARY_COLOR,
  size = 56,
  bottom = 80,
  right = 16,
  ariaLabel = 'Action button',
  disabled = false,
  extended = false,
  label,
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const hasSpeedDial = speedDialActions.length > 0;

  // Close speed dial when clicking outside
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (event: Event) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside);

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, [isOpen]);

  // Close on escape key
  useEffect(() => {
    if (!isOpen) return;

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen]);

  const handleMainClick = useCallback(() => {
    if (hasSpeedDial) {
      setIsOpen((prev) => !prev);
    } else if (onClick) {
      onClick();
    }
  }, [hasSpeedDial, onClick]);

  const handleSpeedDialClick = useCallback((action: SpeedDialAction) => {
    setIsOpen(false);
    action.onClick();
  }, []);

  const containerStyles: React.CSSProperties = {
    position: 'fixed',
    bottom: `calc(${bottom}px + env(safe-area-inset-bottom))`,
    right: `max(${right}px, env(safe-area-inset-right))`,
    zIndex: 100,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: SPEED_DIAL_GAP,
  };

  const fabStyles: React.CSSProperties = {
    width: extended && label ? 'auto' : size,
    height: size,
    minWidth: size,
    borderRadius: extended && label ? size / 2 : '50%',
    padding: extended && label ? '0 20px 0 16px' : 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    border: 'none',
    backgroundColor: color,
    color: '#FFFFFF',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.6 : 1,
    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15), 0 2px 4px rgba(0, 0, 0, 0.12)',
    transition: 'transform 0.2s ease, box-shadow 0.2s ease',
    outline: 'none',
  };

  const speedDialContainerStyles: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-end',
    gap: 12,
    opacity: isOpen ? 1 : 0,
    transform: isOpen ? 'translateY(0)' : 'translateY(10px)',
    pointerEvents: isOpen ? 'auto' : 'none',
    transition: 'opacity 0.2s ease, transform 0.2s ease',
  };

  const speedDialItemStyles: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    flexDirection: 'row-reverse',
  };

  const miniFabStyles = (actionColor?: string): React.CSSProperties => ({
    width: MINI_FAB_SIZE,
    height: MINI_FAB_SIZE,
    borderRadius: '50%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    border: 'none',
    backgroundColor: actionColor || '#FFFFFF',
    color: actionColor ? '#FFFFFF' : color,
    cursor: 'pointer',
    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)',
    transition: 'transform 0.15s ease',
    outline: 'none',
  });

  const tooltipStyles: React.CSSProperties = {
    backgroundColor: '#1F2937',
    color: '#FFFFFF',
    padding: '6px 12px',
    borderRadius: 6,
    fontSize: 14,
    fontWeight: 500,
    whiteSpace: 'nowrap',
    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)',
  };

  const backdropStyles: React.CSSProperties = {
    position: 'fixed',
    inset: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.3)',
    opacity: isOpen ? 1 : 0,
    pointerEvents: isOpen ? 'auto' : 'none',
    transition: 'opacity 0.2s ease',
    zIndex: 99,
  };

  const CurrentIcon = hasSpeedDial && isOpen ? X : Icon;

  return (
    <>
      {/* Backdrop for speed dial */}
      {hasSpeedDial && (
        <div
          style={backdropStyles}
          onClick={() => setIsOpen(false)}
          aria-hidden="true"
        />
      )}

      <div
        ref={containerRef}
        className={`floating-action-button ${className}`}
        style={containerStyles}
      >
        {/* Speed Dial Actions */}
        {hasSpeedDial && (
          <div style={speedDialContainerStyles}>
            {speedDialActions.map((action, index) => {
              const ActionIcon = action.icon;
              return (
                <div
                  key={index}
                  style={{
                    ...speedDialItemStyles,
                    transitionDelay: isOpen ? `${index * 50}ms` : '0ms',
                  }}
                >
                  <span style={tooltipStyles}>{action.label}</span>
                  <button
                    type="button"
                    onClick={() => handleSpeedDialClick(action)}
                    style={miniFabStyles(action.color)}
                    aria-label={action.label}
                  >
                    <ActionIcon size={20} />
                  </button>
                </div>
              );
            })}
          </div>
        )}

        {/* Main FAB */}
        <button
          type="button"
          onClick={handleMainClick}
          disabled={disabled}
          style={{
            ...fabStyles,
            transform: isOpen ? 'rotate(45deg)' : 'none',
          }}
          aria-label={ariaLabel}
          aria-expanded={hasSpeedDial ? isOpen : undefined}
          aria-haspopup={hasSpeedDial ? 'menu' : undefined}
        >
          <CurrentIcon
            size={24}
            style={{
              transition: 'transform 0.2s ease',
              transform: hasSpeedDial && isOpen ? 'rotate(-45deg)' : 'none',
            }}
          />
          {extended && label && (
            <span style={{ fontWeight: 600, fontSize: 14 }}>{label}</span>
          )}
        </button>
      </div>

      <style>{`
        .floating-action-button button:active:not(:disabled) {
          transform: scale(0.95);
        }

        .floating-action-button button:focus-visible {
          outline: 3px solid rgba(37, 99, 235, 0.5);
          outline-offset: 2px;
        }

        @media (hover: hover) {
          .floating-action-button button:hover:not(:disabled) {
            box-shadow: 0 6px 16px rgba(0, 0, 0, 0.2), 0 3px 6px rgba(0, 0, 0, 0.15);
          }
        }
      `}</style>
    </>
  );
};

export default FloatingActionButton;
