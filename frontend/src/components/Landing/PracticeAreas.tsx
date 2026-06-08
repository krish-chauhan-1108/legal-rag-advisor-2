import React from 'react';
import { Briefcase, Landmark, ShieldCheck, Scale, FileText, Globe } from 'lucide-react';

export const PracticeAreas: React.FC = () => {
  const areas = [
    { icon: <Briefcase size={24} strokeWidth={1.5} />, title: 'Corporate M&A', desc: 'Navigating complex mergers, acquisitions, and corporate restructuring.' },
    { icon: <Landmark size={24} strokeWidth={1.5} />, title: 'Litigation', desc: 'Strategic representation in high-stakes commercial disputes.' },
    { icon: <ShieldCheck size={24} strokeWidth={1.5} />, title: 'Compliance', desc: 'Proactive regulatory counsel and risk mitigation strategies.' },
    { icon: <FileText size={24} strokeWidth={1.5} />, title: 'Contract Analysis', desc: 'Deep-dive review of obligations, indemnifications, and liabilities.' },
    { icon: <Scale size={24} strokeWidth={1.5} />, title: 'Employment Law', desc: 'Advising on executive compensation and labor relations.' },
    { icon: <Globe size={24} strokeWidth={1.5} />, title: 'Intellectual Property', desc: 'Safeguarding global assets, patents, and trademarks.' },
  ];

  return (
    <section className="section">
      <h2 className="section__header">Practice Areas</h2>
      <div className="practice-grid">
        {areas.map((area, idx) => (
          <div key={idx} className="practice-card">
            <div className="practice-card__icon">{area.icon}</div>
            <h3 className="practice-card__title">{area.title}</h3>
            <p className="practice-card__desc">{area.desc}</p>
          </div>
        ))}
      </div>
    </section>
  );
};
