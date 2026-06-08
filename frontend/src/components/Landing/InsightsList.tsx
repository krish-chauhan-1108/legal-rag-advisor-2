import React from 'react';

export const InsightsList: React.FC = () => {
  const insights = [
    { date: 'OCT 24, 2026', title: 'The Implications of AI in Cross-Border Data Transfers' },
    { date: 'SEP 12, 2026', title: 'Recent Shifts in Antitrust Enforcement and Corporate Strategy' },
    { date: 'AUG 05, 2026', title: 'Navigating ESG Compliance in Global Supply Chains' },
    { date: 'JUL 18, 2026', title: 'Smart Contracts: Legal Enforceability and Future Outlook' },
  ];

  return (
    <section className="section">
      <h2 className="section__header">Latest Insights</h2>
      <div className="insights-list">
        {insights.map((item, idx) => (
          <article key={idx} className="insight-item">
            <div className="insight-item__date">{item.date}</div>
            <h3 className="insight-item__title">{item.title}</h3>
          </article>
        ))}
      </div>
    </section>
  );
};
