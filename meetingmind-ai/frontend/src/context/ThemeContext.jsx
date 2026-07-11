import { createContext, useState, useEffect, useContext } from 'react';

const ThemeContext = createContext(null);

// Resolve the starting theme from (1) a saved preference, else (2) the class the
// no-flash inline script in index.html already put on <html>, else dark.
const getInitialTheme = () => {
  try {
    const saved = localStorage.getItem('theme');
    if (saved === 'light' || saved === 'dark') return saved;
  } catch { /* storage unavailable */ }
  if (typeof document !== 'undefined' &&
      !document.documentElement.classList.contains('dark')) {
    return 'light';
  }
  return 'dark';
};

export const ThemeProvider = ({ children }) => {
  const [theme, setTheme] = useState(getInitialTheme);

  // Keep <html class="dark"> and the saved preference in sync with state.
  // Tailwind's `dark:` variant and our CSS-variable overrides both key off it.
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle('dark', theme === 'dark');
    try { localStorage.setItem('theme', theme); } catch { /* ignore */ }
  }, [theme]);

  const toggleTheme = () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'));

  const value = { theme, setTheme, toggleTheme, isDark: theme === 'dark' };
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
};

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};
