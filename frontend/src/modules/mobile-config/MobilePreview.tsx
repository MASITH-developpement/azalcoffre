// AZALPLUS - Mobile Preview Component
// Device frame preview with live configuration

import React from 'react';
import type { MobilePreviewProps, MobileConfig, ScreenType, DeviceType } from './types';

// -----------------------------------------------------------------------------
// Device Frame SVGs
// -----------------------------------------------------------------------------
const IPhoneFrame: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="relative">
    {/* iPhone Frame */}
    <div className="relative w-[280px] h-[570px] bg-gray-900 rounded-[40px] p-[10px] shadow-2xl">
      {/* Notch */}
      <div className="absolute top-0 left-1/2 transform -translate-x-1/2 w-[120px] h-[25px] bg-gray-900 rounded-b-2xl z-20" />

      {/* Screen */}
      <div className="w-full h-full bg-white rounded-[32px] overflow-hidden relative">
        {/* Status Bar */}
        <div className="h-11 bg-white flex items-center justify-between px-6 pt-2">
          <span className="text-xs font-medium">9:41</span>
          <div className="flex items-center gap-1">
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12.01 21.49L23.64 7.05a.75.75 0 00-.57-1.24H.93a.75.75 0 00-.57 1.24l11.63 14.44a.75.75 0 001.02 0z" />
            </svg>
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M2 22h20V2H2v20zm2-2V4h16v16H4z" />
            </svg>
            <div className="w-6 h-3 bg-gray-900 rounded-sm relative">
              <div className="absolute right-0 top-1/2 transform -translate-y-1/2 w-0.5 h-1.5 bg-gray-900 rounded-r" />
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="h-[calc(100%-44px-34px)] overflow-hidden">
          {children}
        </div>

        {/* Home Indicator */}
        <div className="absolute bottom-2 left-1/2 transform -translate-x-1/2 w-32 h-1 bg-gray-900 rounded-full" />
      </div>
    </div>
  </div>
);

const AndroidFrame: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="relative">
    {/* Android Frame */}
    <div className="relative w-[280px] h-[570px] bg-gray-800 rounded-[24px] p-[8px] shadow-2xl">
      {/* Screen */}
      <div className="w-full h-full bg-white rounded-[18px] overflow-hidden relative">
        {/* Status Bar */}
        <div className="h-7 bg-gray-900 flex items-center justify-between px-4">
          <span className="text-xs text-white font-medium">9:41</span>
          <div className="flex items-center gap-2 text-white">
            <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12.01 21.49L23.64 7.05a.75.75 0 00-.57-1.24H.93a.75.75 0 00-.57 1.24l11.63 14.44a.75.75 0 001.02 0z" />
            </svg>
            <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M17 4h3v16h-3zM5 14h3v6H5zM11 9h3v11h-3z" />
            </svg>
            <div className="w-5 h-2.5 border border-white rounded-sm relative">
              <div className="absolute inset-0.5 bg-white rounded-sm" style={{ width: '70%' }} />
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="h-[calc(100%-28px-40px)] overflow-hidden">
          {children}
        </div>

        {/* Navigation Bar */}
        <div className="absolute bottom-0 left-0 right-0 h-10 bg-gray-100 flex items-center justify-center gap-16">
          <div className="w-4 h-4 border-2 border-gray-400 rounded-sm" />
          <div className="w-5 h-5 border-2 border-gray-400 rounded-full" />
          <div className="w-0 h-0 border-l-[8px] border-l-transparent border-r-[8px] border-r-transparent border-b-[10px] border-b-gray-400" />
        </div>
      </div>
    </div>
  </div>
);

// -----------------------------------------------------------------------------
// Screen Content Components
// -----------------------------------------------------------------------------
interface ScreenContentProps {
  config: MobileConfig;
}

const DashboardScreen: React.FC<ScreenContentProps> = ({ config }) => {
  const { themeBranding, dashboardWidgets, appName } = config;

  return (
    <div className={themeBranding.darkMode ? 'bg-gray-900 h-full' : 'bg-gray-50 h-full'}>
      {/* Header */}
      <div
        className="px-4 py-3"
        style={{ backgroundColor: themeBranding.primaryColor }}
      >
        <div className="flex items-center gap-3">
          {themeBranding.logoUrl ? (
            <img src={themeBranding.logoUrl} alt="" className="w-8 h-8 rounded-lg bg-white/20" />
          ) : (
            <div className="w-8 h-8 bg-white/20 rounded-lg flex items-center justify-center text-white text-xs font-bold">
              {appName.substring(0, 2).toUpperCase()}
            </div>
          )}
          <span className="text-white font-semibold text-sm">{appName}</span>
        </div>
      </div>

      {/* Widgets */}
      <div className="p-3 space-y-3">
        {dashboardWidgets.slice(0, 4).map((widget, index) => {
          const borderRadius = themeBranding.borderRadius === 'none' ? '0' :
                              themeBranding.borderRadius === 'small' ? '4px' :
                              themeBranding.borderRadius === 'medium' ? '8px' : '12px';

          if (widget.type === 'stat') {
            return (
              <div
                key={widget.id}
                className={`p-3 ${themeBranding.darkMode ? 'bg-gray-800' : 'bg-white'} shadow-sm`}
                style={{ borderRadius }}
              >
                <div className="text-[10px] text-gray-500 mb-1">{widget.title}</div>
                <div
                  className="text-lg font-bold"
                  style={{ color: widget.color }}
                >
                  {Math.floor(Math.random() * 1000)}
                </div>
              </div>
            );
          }

          if (widget.type === 'list') {
            return (
              <div
                key={widget.id}
                className={`p-3 ${themeBranding.darkMode ? 'bg-gray-800' : 'bg-white'} shadow-sm`}
                style={{ borderRadius }}
              >
                <div className="text-[10px] text-gray-500 mb-2">{widget.title}</div>
                {[1, 2, 3].map((i) => (
                  <div key={i} className="flex items-center gap-2 py-1.5 border-b border-gray-100 last:border-0">
                    <div
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: widget.color }}
                    />
                    <div className={`h-2 flex-1 ${themeBranding.darkMode ? 'bg-gray-700' : 'bg-gray-200'} rounded`} />
                  </div>
                ))}
              </div>
            );
          }

          if (widget.type === 'chart') {
            return (
              <div
                key={widget.id}
                className={`p-3 ${themeBranding.darkMode ? 'bg-gray-800' : 'bg-white'} shadow-sm`}
                style={{ borderRadius }}
              >
                <div className="text-[10px] text-gray-500 mb-2">{widget.title}</div>
                <div className="flex items-end justify-between h-12 gap-1">
                  {[40, 65, 45, 80, 55, 70, 60].map((h, i) => (
                    <div
                      key={i}
                      className="flex-1 rounded-t"
                      style={{
                        height: `${h}%`,
                        backgroundColor: widget.color,
                        opacity: 0.3 + (i * 0.1),
                      }}
                    />
                  ))}
                </div>
              </div>
            );
          }

          return null;
        })}

        {dashboardWidgets.length === 0 && (
          <div className={`p-6 text-center ${themeBranding.darkMode ? 'text-gray-500' : 'text-gray-400'}`}>
            <div className="text-[10px]">Aucun widget</div>
          </div>
        )}
      </div>
    </div>
  );
};

const ModuleListScreen: React.FC<ScreenContentProps> = ({ config }) => {
  const { themeBranding, modules, appName } = config;
  const enabledModules = modules.filter(m => m.enabled);

  const borderRadius = themeBranding.borderRadius === 'none' ? '0' :
                      themeBranding.borderRadius === 'small' ? '4px' :
                      themeBranding.borderRadius === 'medium' ? '8px' : '12px';

  return (
    <div className={themeBranding.darkMode ? 'bg-gray-900 h-full' : 'bg-gray-50 h-full'}>
      {/* Header */}
      <div
        className="px-4 py-3"
        style={{ backgroundColor: themeBranding.primaryColor }}
      >
        <span className="text-white font-semibold text-sm">Modules</span>
      </div>

      {/* Module Grid */}
      <div className="p-3 grid grid-cols-3 gap-2">
        {enabledModules.slice(0, 9).map((module) => (
          <div
            key={module.id}
            className={`p-3 flex flex-col items-center ${themeBranding.darkMode ? 'bg-gray-800' : 'bg-white'} shadow-sm`}
            style={{ borderRadius }}
          >
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center mb-1"
              style={{ backgroundColor: `${themeBranding.primaryColor}20` }}
            >
              <svg
                className="w-4 h-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke={themeBranding.primaryColor}
                strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </div>
            <span className={`text-[8px] truncate max-w-full ${themeBranding.darkMode ? 'text-gray-300' : 'text-gray-600'}`}>
              {module.name}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

const QuickActionsScreen: React.FC<ScreenContentProps> = ({ config }) => {
  const { themeBranding, quickActions } = config;

  return (
    <div className={themeBranding.darkMode ? 'bg-gray-900 h-full' : 'bg-gray-50 h-full'}>
      {/* Overlay */}
      <div className="absolute inset-0 bg-black/50" />

      {/* FAB Menu */}
      <div className="absolute bottom-20 right-4 flex flex-col-reverse items-end gap-3">
        {quickActions.map((action, index) => (
          <div key={action.id} className="flex items-center gap-2">
            <span className="px-2 py-1 bg-white rounded text-[8px] shadow">
              {action.label}
            </span>
            <div
              className="w-10 h-10 rounded-full flex items-center justify-center text-white shadow-lg"
              style={{ backgroundColor: action.color }}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
            </div>
          </div>
        ))}

        {/* Main FAB */}
        <div
          className="w-14 h-14 rounded-full flex items-center justify-center text-white shadow-xl"
          style={{ backgroundColor: themeBranding.primaryColor }}
        >
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
        </div>
      </div>
    </div>
  );
};

// -----------------------------------------------------------------------------
// Main Component
// -----------------------------------------------------------------------------
export function MobilePreview({
  config,
  screen,
  device,
  onScreenChange,
  onDeviceChange,
}: MobilePreviewProps) {
  const screens: { value: ScreenType; label: string }[] = [
    { value: 'dashboard', label: 'Dashboard' },
    { value: 'module-list', label: 'Modules' },
    { value: 'quick-actions', label: 'Actions' },
  ];

  const devices: { value: DeviceType; label: string }[] = [
    { value: 'iphone', label: 'iPhone' },
    { value: 'android', label: 'Android' },
  ];

  const Frame = device === 'iphone' ? IPhoneFrame : AndroidFrame;

  const renderScreen = () => {
    switch (screen) {
      case 'dashboard':
        return <DashboardScreen config={config} />;
      case 'module-list':
        return <ModuleListScreen config={config} />;
      case 'quick-actions':
        return <QuickActionsScreen config={config} />;
      default:
        return <DashboardScreen config={config} />;
    }
  };

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-col sm:flex-row gap-3">
        {/* Screen Selector */}
        <div className="flex rounded-lg border border-gray-300 overflow-hidden">
          {screens.map((s) => (
            <button
              key={s.value}
              onClick={() => onScreenChange(s.value)}
              className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                screen === s.value
                  ? 'bg-blue-600 text-white'
                  : 'bg-white text-gray-700 hover:bg-gray-50'
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>

        {/* Device Selector */}
        <div className="flex rounded-lg border border-gray-300 overflow-hidden">
          {devices.map((d) => (
            <button
              key={d.value}
              onClick={() => onDeviceChange(d.value)}
              className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                device === d.value
                  ? 'bg-blue-600 text-white'
                  : 'bg-white text-gray-700 hover:bg-gray-50'
              }`}
            >
              {d.label}
            </button>
          ))}
        </div>
      </div>

      {/* Device Frame */}
      <div className="flex justify-center py-4 bg-gradient-to-br from-gray-100 to-gray-200 rounded-xl">
        <Frame>
          {renderScreen()}
        </Frame>
      </div>

      {/* Info */}
      <div className="text-center text-xs text-gray-500">
        Apercu en direct - Les modifications sont appliquees instantanement
      </div>
    </div>
  );
}

export default MobilePreview;
