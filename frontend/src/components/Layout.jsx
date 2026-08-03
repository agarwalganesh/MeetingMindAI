import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import {
  LayoutDashboard,
  FileAudio,
  ShieldAlert,
  LogOut,
  Menu,
  X,
  Brain,
  Sun,
  Moon,
  User as UserIcon
} from 'lucide-react';

// Button that flips between light and dark themes. Icon-only by default; pass
// `label` to render a full-width labelled row (used in the sidebar).
const ThemeToggle = ({ className = '', label = false }) => {
  const { isDark, toggleTheme } = useTheme();
  const Icon = isDark ? Sun : Moon;
  const text = isDark ? 'Light mode' : 'Dark mode';
  return (
    <button
      onClick={toggleTheme}
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      aria-label="Toggle color theme"
      className={`flex items-center ${label ? 'gap-3 px-4 py-2.5 w-full text-left text-sm' : 'justify-center'} rounded-xl border border-slate-800 bg-slate-900/60 text-slate-400 hover:text-white hover:border-slate-700 transition-colors ${className}`}
    >
      <Icon className="w-4 h-4" />
      {label && <span>{text}</span>}
    </button>
  );
};

const Layout = ({ children }) => {
  const { user, logout, isAdmin } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const navItems = [
    { name: 'Dashboard', path: '/', icon: LayoutDashboard },
    { name: 'Meetings', path: '/meetings', icon: FileAudio },
  ];

  if (isAdmin) {
    navItems.push({ name: 'Admin Panel', path: '/admin', icon: ShieldAlert });
  }

  const isActive = (path) => {
    if (path === '/') {
      return location.pathname === '/';
    }
    return location.pathname.startsWith(path);
  };

  return (
    <div className="min-h-screen bg-slate-950 flex">
      {/* Sidebar for Desktop */}
      <aside className="hidden md:flex flex-col w-64 glass-panel border-r border-slate-800 text-slate-300">
        <div className="p-6 flex items-center gap-3 border-b border-slate-800">
          <Brain className="w-8 h-8 text-primary-500" />
          <span className="text-xl font-bold bg-gradient-to-r from-white to-slate-400 bg-clip-text text-transparent">
            MeetingMind AI
          </span>
        </div>
        
        <nav className="flex-1 px-4 py-6 space-y-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = isActive(item.path);
            return (
              <Link
                key={item.name}
                to={item.path}
                className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200 group ${
                  active 
                    ? 'bg-primary-600/20 text-primary-400 border-l-4 border-primary-500 font-semibold' 
                    : 'hover:bg-slate-800/50 hover:text-white'
                }`}
              >
                <Icon className={`w-5 h-5 transition-transform group-hover:scale-105 ${active ? 'text-primary-400' : 'text-slate-400'}`} />
                <span>{item.name}</span>
              </Link>
            );
          })}
        </nav>

        {/* User Card */}
        <div className="p-4 border-t border-slate-800 flex flex-col gap-3">
          <div className="flex items-center gap-3 px-2">
            <div className="w-10 h-10 rounded-full bg-primary-600/30 flex items-center justify-center border border-primary-500/20">
              <UserIcon className="w-5 h-5 text-primary-400" />
            </div>
            <div className="overflow-hidden">
              <p className="text-sm font-semibold text-white truncate">{user?.name}</p>
              <p className="text-xs text-slate-500 truncate">{user?.email}</p>
            </div>
          </div>
          <ThemeToggle label />
          <button
            onClick={handleLogout}
            className="flex items-center gap-3 px-4 py-2.5 rounded-xl hover:bg-red-500/10 hover:text-red-400 text-slate-400 transition-colors w-full text-left text-sm"
          >
            <LogOut className="w-4 h-4" />
            <span>Sign Out</span>
          </button>
        </div>
      </aside>

      {/* Mobile Menu Button */}
      <div className="md:hidden fixed top-4 right-4 z-50 flex items-center gap-2">
        <ThemeToggle className="p-2.5 shadow-lg" />
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="p-2.5 rounded-xl bg-slate-900 border border-slate-800 text-slate-300 hover:text-white transition-all shadow-lg"
        >
          {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
        </button>
      </div>

      {/* Mobile Drawer */}
      {mobileMenuOpen && (
        <div className="md:hidden fixed inset-0 z-40 bg-slate-950/80 backdrop-blur-sm">
          <nav className="fixed top-0 bottom-0 left-0 w-72 bg-slate-900 border-r border-slate-800 p-6 flex flex-col justify-between">
            <div className="space-y-8">
              <div className="flex items-center gap-3">
                <Brain className="w-8 h-8 text-primary-500" />
                <span className="text-xl font-bold text-white">MeetingMind AI</span>
              </div>
              <div className="space-y-2">
                {navItems.map((item) => {
                  const Icon = item.icon;
                  const active = isActive(item.path);
                  return (
                    <Link
                      key={item.name}
                      to={item.path}
                      onClick={() => setMobileMenuOpen(false)}
                      className={`flex items-center gap-3 px-4 py-3.5 rounded-xl transition-all ${
                        active 
                          ? 'bg-primary-600/20 text-primary-400 border-l-4 border-primary-500 font-semibold' 
                          : 'hover:bg-slate-800 text-slate-300'
                      }`}
                    >
                      <Icon className="w-5 h-5 text-current" />
                      <span>{item.name}</span>
                    </Link>
                  );
                })}
              </div>
            </div>
            
            <div className="space-y-4">
              <div className="flex items-center gap-3 border-t border-slate-800 pt-4">
                <div className="w-9 h-9 rounded-full bg-slate-800 flex items-center justify-center">
                  <UserIcon className="w-4 h-4 text-slate-400" />
                </div>
                <div className="overflow-hidden">
                  <p className="text-sm font-semibold text-white truncate">{user?.name}</p>
                  <p className="text-xs text-slate-500 truncate">{user?.email}</p>
                </div>
              </div>
              <button
                onClick={handleLogout}
                className="flex items-center gap-3 px-4 py-2.5 rounded-xl hover:bg-red-500/10 hover:text-red-400 text-slate-400 transition-colors w-full text-left text-sm"
              >
                <LogOut className="w-4 h-4" />
                <span>Sign Out</span>
              </button>
            </div>
          </nav>
        </div>
      )}

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col min-w-0 overflow-y-auto max-h-screen">
        <header className="md:hidden h-16 border-b border-slate-800 flex items-center px-6">
          <div className="flex items-center gap-2">
            <Brain className="w-6 h-6 text-primary-500" />
            <span className="font-bold text-white">MeetingMind AI</span>
          </div>
        </header>
        <div className="p-6 md:p-10 w-full max-w-7xl mx-auto">
          {children}
        </div>
      </main>
    </div>
  );
};

export default Layout;
