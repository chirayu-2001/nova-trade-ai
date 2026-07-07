import { useEffect, useState } from 'react';
import { FileText } from 'lucide-react';
import { getShipments, getShipmentDetail, type ShipmentSummary, type ShipmentDetail } from '../lib/api';
import { confidenceBadge, decisionBadge } from '../lib/helpers';

export default function ShipmentsTab() {
  const [shipments, setShipments] = useState<ShipmentSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ShipmentDetail | null>(null);

  useEffect(() => {
    getShipments().then(setShipments).catch(() => {});
  }, []);

  const loadDetail = async (id: string) => {
    setSelectedId(id);
    const d = await getShipmentDetail(id);
    setDetail(d);
  };

  return (
    <div className="space-y-6">
      <div className="glass-panel p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="section-title" style={{ marginBottom: 0 }}>
            <FileText size={20} /> Processed Shipments
          </h3>
          <button onClick={() => getShipments().then(setShipments)} className="btn-secondary" style={{ fontSize: '0.85rem' }}>Refresh</button>
        </div>
        {shipments.length === 0 ? (
          <p className="text-muted" style={{ textAlign: 'center', padding: '3rem 0' }}>
            No shipments processed yet. Run the pipeline to see results here.
          </p>
        ) : (
          <table className="data-grid">
            <thead>
              <tr>
                <th>Shipment ID</th>
                <th>Customer</th>
                <th style={{ textAlign: 'center' }}>Docs</th>
                <th style={{ textAlign: 'center' }}>Decision</th>
                <th style={{ textAlign: 'center' }}>Confidence</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {shipments.map(s => (
                <tr
                  key={s.id}
                  onClick={() => loadDetail(s.id)}
                  style={{ cursor: 'pointer', background: selectedId === s.id ? 'rgba(255,255,255,0.05)' : '' }}
                >
                  <td className="font-mono text-gradient-primary">{s.id}</td>
                  <td style={{ fontWeight: 500 }}>{s.customer_name}</td>
                  <td style={{ textAlign: 'center' }}>{s.document_count}</td>
                  <td style={{ textAlign: 'center' }}>{decisionBadge(s.decision)}</td>
                  <td style={{ textAlign: 'center' }}>{s.overall_confidence ? confidenceBadge(s.overall_confidence) : '—'}</td>
                  <td className="text-muted" style={{ fontSize: '0.85rem' }}>{new Date(s.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {detail && (
        <div className="glass-panel p-6">
          <h3 className="section-title">
            Shipment Details: <span className="font-mono text-gradient-primary">{detail.id}</span>
          </h3>
          <div className="mb-4">{decisionBadge(detail.decision)}</div>
          <div className="reasoning-block font-mono" style={{ marginBottom: '1.5rem' }}>
            {detail.decision_reasoning}
          </div>
          {detail.draft_email && (
            <div>
              <h4 className="section-title" style={{ fontSize: '1rem', marginBottom: '0.75rem' }}>Generated Draft Email</h4>
              <div className="reasoning-block font-mono">
                {detail.draft_email}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
