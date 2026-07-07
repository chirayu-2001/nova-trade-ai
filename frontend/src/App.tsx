import { useState } from 'react';
import { Package, Search, FileText, Inbox } from 'lucide-react';
import InboxTab from './components/InboxTab';
import PipelineView from './components/PipelineView';
import QueryTab from './components/QueryTab';
import ShipmentsTab from './components/ShipmentsTab';

type Tab = 'inbox' | 'pipeline' | 'query' | 'shipments';

export default function App() {
  const [tab, setTab] = useState<Tab>('inbox');

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'inbox', label: 'CG Inbox', icon: <Inbox size={18} /> },
    { id: 'pipeline', label: 'Document Validation', icon: <Package size={18} /> },
    { id: 'query', label: 'Knowledge Base', icon: <Search size={18} /> },
    { id: 'shipments', label: 'Shipment Audit', icon: <FileText size={18} /> },
  ];

  return (
    <>
      {/* Header */}
      <header className="app-header">
        <div className="header-content">
          <div>
            <div className="flex items-center gap-2">
              <div className="brand-dot" />
              <h1 className="brand-title text-gradient">Nova</h1>
            </div>
            <p className="brand-subtitle mt-1">Autonomous Trade Document Validation</p>
          </div>
          <div className="badge badge-neutral" style={{ padding: '0.5rem 1rem' }}>GoComet OS</div>
        </div>
      </header>

      {/* Tabs */}
      <div className="tabs-container">
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`tab-btn ${tab === t.id ? 'active' : ''}`}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <main className="main-content">
        {tab === 'inbox' && <InboxTab />}
        {tab === 'pipeline' && <PipelineView />}
        {tab === 'query' && <QueryTab />}
        {tab === 'shipments' && <ShipmentsTab />}
      </main>
    </>
  );
}
