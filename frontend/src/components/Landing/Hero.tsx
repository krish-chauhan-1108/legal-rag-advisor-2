import React from 'react';

interface HeroProps {
  onOpenChat: () => void;
}

export const Hero: React.FC<HeroProps> = ({ onOpenChat }) => {
  return (
    <section className="hero">
      <div className="hero__content">
        <h1 className="hero__title">
          Clarity and precision in complex legal matters.
        </h1>
        <p className="hero__subtitle">
          An elite AI-powered advisory platform for the modern firm. 
          Upload sensitive documents, query obligations, and receive meticulously cited analysis instantly.
        </p>
        <div className="hero__actions">
          <button className="btn-primary" onClick={onOpenChat}>
            Access Workspace
          </button>
          <button className="btn-outline">
            View Capabilities
          </button>
        </div>
      </div>
      <div className="hero__frame">
        {/* Sharp minimalist framing replacing blobs */}
        <div style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
          <p style={{ fontFamily: 'var(--font-serif)', fontSize: '1.25rem', marginBottom: '0.5rem', color: 'var(--text-primary)' }}>
            System Status: Active
          </p>
          <p style={{ fontSize: '0.85rem' }}>Secured Environment</p>
        </div>
      </div>
    </section>
  );
};
