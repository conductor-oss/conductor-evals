import React from 'react';
import { Outlet, Link, useLocation } from 'react-router-dom';

const navItems = [
  { path: '/', label: 'Dashboard' },
  { path: '/runs', label: 'Runs' },
  { path: '/compare', label: 'Compare' },
];

export default function Layout() {
  const location = useLocation();

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <nav style={{
        background: '#ffffff',
        color: '#333',
        padding: '0 24px',
        display: 'flex',
        alignItems: 'center',
        height: 56,
        gap: 32,
        borderBottom: '1px solid #e0e0e0',
        boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
      }}>
        <Link to="/" style={{ color: '#1a1a2e', textDecoration: 'none', fontWeight: 700, fontSize: 18, display: 'flex', alignItems: 'center', gap: 10 }}>
          <img src="https://assets.conductor-oss.org/logo.png" alt="Conductor" style={{ height: 28 }} />
          Evals Framework
        </Link>
        <div style={{ display: 'flex', gap: 16 }}>
          {navItems.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              style={{
                color: location.pathname === item.path ? '#1a73e8' : '#666',
                textDecoration: 'none',
                fontSize: 14,
                fontWeight: location.pathname === item.path ? 600 : 400,
              }}
            >
              {item.label}
            </Link>
          ))}
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 16 }}>
          <a
            href="https://github.com/conductor-oss/conductor-evals"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: '#666', textDecoration: 'none', fontSize: 13 }}
          >
            GitHub
          </a>
          <a
            href="https://join.slack.com/t/orkes-conductor/shared_invite/zt-2vdbx239s-Eacdyqya9giNLHfrCavfaA"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: '#666', textDecoration: 'none', fontSize: 13 }}
          >
            Slack
          </a>
        </div>
      </nav>
      <main style={{ flex: 1, padding: 24, maxWidth: 1200, margin: '0 auto', width: '100%' }}>
        <Outlet />
      </main>
    </div>
  );
}
