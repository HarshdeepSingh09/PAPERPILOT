import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';

interface RouterContextValue {
  pathname: string;
  search: string;
  isAppRoute: boolean;
  navigate: (to: string) => void;
}

const RouterContext = createContext<RouterContextValue | undefined>(undefined);

function normalizePath(path: string): string {
  if (!path) return '/';
  const cleaned = path.split('?')[0].split('#')[0];
  return cleaned || '/';
}

export const RouterProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [pathname, setPathname] = useState<string>(() =>
    typeof window !== 'undefined' ? normalizePath(window.location.pathname) : '/'
  );
  const [search, setSearch] = useState<string>(() =>
    typeof window !== 'undefined' ? window.location.search : ''
  );

  useEffect(() => {
    const handlePopState = () => {
      setPathname(normalizePath(window.location.pathname));
      setSearch(window.location.search || '');
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const navigate = useCallback((to: string) => {
    if (typeof window === 'undefined') return;
    const qIdx = to.indexOf('?');
    const targetPath = normalizePath(to);
    const targetSearch = qIdx >= 0 ? to.slice(qIdx).split('#')[0] : '';
    const fullTarget = `${targetPath}${targetSearch}`;
    const currentFull = `${window.location.pathname}${window.location.search}`;
    if (currentFull !== fullTarget) {
      window.history.pushState({}, '', fullTarget);
    }
    setPathname(targetPath);
    setSearch(targetSearch);
  }, []);

  const isAppRoute = pathname === '/app' || pathname.startsWith('/app/');

  return (
    <RouterContext.Provider value={{ pathname, search, isAppRoute, navigate }}>
      {children}
    </RouterContext.Provider>
  );
};

export function useRouter(): RouterContextValue {
  const ctx = useContext(RouterContext);
  if (!ctx) {
    throw new Error('useRouter must be used within a RouterProvider');
  }
  return ctx;
}
