// AZALPLUS - Composant Sidebar (Menu latéral)
import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { menuConfig, type MenuItem, type MenuSection } from '../core/menu';

// -----------------------------------------------------------------------------
// Composant Icon - Charge les icônes depuis /assets/icons/
// -----------------------------------------------------------------------------
interface IconProps {
  name: string;
  className?: string;
  size?: number;
}

const Icon: React.FC<IconProps> = ({ name, className = 'w-5 h-5', size = 20 }) => {
  return (
    <img
      src={`/assets/icons/${name}.svg`}
      alt={name}
      width={size}
      height={size}
      className={className}
      style={{ filter: 'var(--icon-filter, none)' }}
      onError={(e) => {
        (e.target as HTMLImageElement).src = '/assets/icons/default.svg';
      }}
    />
  );
};

// -----------------------------------------------------------------------------
// Composant MenuItem
// -----------------------------------------------------------------------------
interface MenuItemComponentProps {
  item: MenuItem;
  isActive: boolean;
  isCollapsed: boolean;
}

const MenuItemComponent: React.FC<MenuItemComponentProps> = ({ item, isActive, isCollapsed }) => {
  if (item.separator) {
    return <div className="my-2 border-t border-gray-200" />;
  }

  const baseClasses = `
    flex items-center gap-3 px-3 py-2 rounded-lg transition-colors
    ${isActive ? 'bg-blue-50 text-blue-700 font-medium' : 'text-gray-700 hover:bg-gray-100'}
    ${item.disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
  `;

  const content = (
    <>
      <span className={`flex-shrink-0 ${isActive ? 'text-blue-600' : 'text-gray-500'}`}>
        <Icon name={item.icon || 'default'} />
      </span>
      {!isCollapsed && (
        <>
          <span className="flex-1 truncate">{item.label}</span>
          {item.badge && (
            <span
              className={`
                text-xs px-2 py-0.5 rounded-full font-medium
                ${item.badgeColor === 'purple' ? 'bg-purple-100 text-purple-700' : ''}
                ${item.badgeColor === 'blue' ? 'bg-blue-100 text-blue-700' : ''}
                ${item.badgeColor === 'green' ? 'bg-green-100 text-green-700' : ''}
                ${item.badgeColor === 'red' ? 'bg-red-100 text-red-700' : ''}
                ${item.badgeColor === 'yellow' ? 'bg-yellow-100 text-yellow-700' : ''}
                ${!item.badgeColor ? 'bg-gray-100 text-gray-700' : ''}
              `}
            >
              {item.badge}
            </span>
          )}
        </>
      )}
    </>
  );

  if (item.disabled) {
    return <div className={baseClasses}>{content}</div>;
  }

  if (item.external && item.path) {
    return (
      <a href={item.path} target="_blank" rel="noopener noreferrer" className={baseClasses}>
        {content}
      </a>
    );
  }

  if (item.path) {
    return (
      <Link to={item.path} className={baseClasses}>
        {content}
      </Link>
    );
  }

  return <div className={baseClasses}>{content}</div>;
};

// -----------------------------------------------------------------------------
// Composant Section
// -----------------------------------------------------------------------------
interface MenuSectionComponentProps {
  section: MenuSection;
  currentPath: string;
  isCollapsed: boolean;
}

const MenuSectionComponent: React.FC<MenuSectionComponentProps> = ({
  section,
  currentPath,
  isCollapsed,
}) => {
  return (
    <div className="mb-4">
      {section.title && !isCollapsed && (
        <h3 className="px-3 mb-2 text-xs font-semibold text-gray-400 uppercase tracking-wider">
          {section.title}
        </h3>
      )}
      <nav className="space-y-1">
        {section.items.map((item) => (
          <MenuItemComponent
            key={item.id}
            item={item}
            isActive={currentPath === item.path || currentPath.startsWith(`${item.path}/`)}
            isCollapsed={isCollapsed}
          />
        ))}
      </nav>
    </div>
  );
};

// -----------------------------------------------------------------------------
// Composant Sidebar Principal
// -----------------------------------------------------------------------------
interface SidebarProps {
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isCollapsed = false, onToggleCollapse }) => {
  const location = useLocation();
  const currentPath = location.pathname;

  return (
    <aside
      className={`
        h-screen bg-white border-r border-gray-200 flex flex-col
        transition-all duration-300 ease-in-out
        ${isCollapsed ? 'w-16' : 'w-64'}
      `}
    >
      {/* Logo */}
      <div className="h-16 flex items-center justify-between px-4 border-b border-gray-200">
        {!isCollapsed && (
          <Link to="/" className="flex items-center gap-2">
            <div className="w-8 h-8 bg-gradient-to-br from-blue-600 to-purple-600 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-sm">AZ</span>
            </div>
            <span className="font-bold text-xl text-gray-900">AZALPLUS</span>
          </Link>
        )}
        {isCollapsed && (
          <Link to="/" className="mx-auto">
            <div className="w-8 h-8 bg-gradient-to-br from-blue-600 to-purple-600 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-sm">AZ</span>
            </div>
          </Link>
        )}
        {onToggleCollapse && !isCollapsed && (
          <button
            onClick={onToggleCollapse}
            className="p-1 rounded hover:bg-gray-100 text-gray-500"
            title="Réduire le menu"
          >
            <Icon name="arrow-left-right" />
          </button>
        )}
      </div>

      {/* Menu */}
      <div className="flex-1 overflow-y-auto py-4 px-2">
        {menuConfig.map((section) => (
          <MenuSectionComponent
            key={section.id}
            section={section}
            currentPath={currentPath}
            isCollapsed={isCollapsed}
          />
        ))}
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-gray-200">
        {!isCollapsed ? (
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-gray-200 rounded-full flex items-center justify-center">
              <span className="text-gray-600 text-sm font-medium">JD</span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 truncate">John Doe</p>
              <p className="text-xs text-gray-500 truncate">Admin</p>
            </div>
          </div>
        ) : (
          <div className="flex justify-center">
            <div className="w-8 h-8 bg-gray-200 rounded-full flex items-center justify-center">
              <span className="text-gray-600 text-sm font-medium">JD</span>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
};

export default Sidebar;
