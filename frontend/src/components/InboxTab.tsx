import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Mail, Loader2, CheckCircle, XCircle, AlertTriangle, Paperclip,
  Sparkles, Inbox as InboxIcon, FileText, Clock, RotateCcw,
} from 'lucide-react';
import {
  getInbox, simulateInboxEmail, getShipmentDetail, approveShipment, sendAmendment,
  type InboxItem, type ShipmentDetail,
} from '../lib/api';
import { decisionBadge, confidenceBadge } from '../lib/helpers';
import { DOC_TYPE_CONFIG, getDocStats, getDocStatus } from '../lib/shipmentHelpers';
import FieldResultsTable from './shared/FieldResultsTable';
import CrossDocTable from './shared/CrossDocTable';
import DraftEmailPanel from './shared/DraftEmailPanel';
import EmailPreview from './shared/EmailPreview';

const POLL_MS = 2000;

function statusChip(item: InboxItem) {
  switch (item.status) {
    case 'new':
      return <span className="badge badge-neutral"><Mail size={12} /> New</span>;
    case 'processing':
      return <span className="badge badge-warning"><Loader2 size={12} className="animate-spin" /> Processing</span>;
    case 'processed':
      return <span className="badge badge-success"><CheckCircle size={12} /> Ready for Review</span>;
    case 'error':
      return <span className="badge badge-error"><XCircle size={12} /> Failed</span>;
    default:
      return <span className="badge badge-neutral">{item.status}</span>;
  }
}

/**
 * "CG Inbox" — the Part 2 workflow. Instead of a generic upload screen, this
 * frames the same Part 1 agents (Extractor -> Validator -> Cross-Validate ->
 * Router) as a mailbox a CG operator already understands:
 *
 *   Incoming            -> mailbox list, polls the simulated SU inbox
 *   Verification result -> field-by-field + cross-doc view once processed
 *   Discrepancy detail  -> click a flagged field (inside FieldResultsTable)
 *   Draft reply         -> editable reply, CG must click Send — never automatic
 */
export default function InboxTab() {
  const [items, setItems] = useState<InboxItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ShipmentDetail | null>(null);
  const [selectedDocIndex, setSelectedDocIndex] = useState(0);
  const [draftEmail, setDraftEmail] = useState('');
  const [simulating, setSimulating] = useState(false);
  const pollRef = useRef<number | null>(null);

  const refreshInbox = useCallback(async () => {
    try {
      const data = await getInbox();
      setItems(data);
    } catch {
      // Backend not reachable yet — polling will retry.
    }
  }, []);

  useEffect(() => {
    refreshInbox();
    pollRef.current = window.setInterval(refreshInbox, POLL_MS);
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [refreshInbox]);

  // Keep the open shipment's status in sync while it's still processing.
  useEffect(() => {
    if (!selectedId) return;
    const item = items.find(i => i.id === selectedId);
    if (item?.status === 'processed' && item.shipment_id && detail?.id !== item.shipment_id) {
      getShipmentDetail(item.shipment_id).then(d => {
        setDetail(d);
        setSelectedDocIndex(0);
        setDraftEmail(d.draft_email || '');
      });
    }
  }, [items, selectedId, detail]);

  const handleSelect = (item: InboxItem) => {
    setSelectedId(item.id);
    setDetail(null);
    setDraftEmail('');
    if (item.status === 'processed' && item.shipment_id) {
      getShipmentDetail(item.shipment_id).then(d => {
        setDetail(d);
        setSelectedDocIndex(0);
        setDraftEmail(d.draft_email || '');
      });
    }
  };

  const handleSimulate = async () => {
    setSimulating(true);
    try {
      await simulateIncomingAndRefresh();
    } finally {
      setSimulating(false);
    }
  };

  const simulateIncomingAndRefresh = async () => {
    await simulateInboxEmail();
    await refreshInbox();
  };

  const handleApprove = async () => {
    if (!detail) return;
    await approveShipment(detail.id);
    setDetail(prev => prev ? { ...prev, status: 'approved', decision: 'approved' } : null);
  };

  const handleSendAmendment = async () => {
    if (!detail) return;
    await sendAmendment(detail.id, draftEmail);
    setDetail(prev => prev ? { ...prev, status: 'amendment_sent' } : null);
  };

  const selectedItem = items.find(i => i.id === selectedId) || null;
  const selectedDoc = detail?.documents?.[selectedDocIndex] || null;

  return (
    <div className="space-y-6">
      <div className="glass-panel p-6">
        <div className="flex items-center justify-between" style={{ flexWrap: 'wrap', gap: '0.75rem' }}>
          <div>
            <h3 className="section-title" style={{ marginBottom: '0.25rem' }}>
              <InboxIcon size={20} /> CG Inbox — Simulated SU Trigger
            </h3>
            
          </div>
          <button onClick={handleSimulate} disabled={simulating} className="btn-primary" style={{ whiteSpace: 'nowrap' }}>
            {simulating ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
            Simulate Incoming Email
          </button>
        </div>
      </div>

      <div className="split-container">
        {/* LEFT: Incoming mailbox */}
        <div className="doc-navigator">
          <div className="glass-panel p-4">
            <h4 className="doc-nav-title">Incoming ({items.length})</h4>
            {items.length === 0 ? (
              <p className="text-muted" style={{ padding: '1.5rem 0', textAlign: 'center', fontSize: '0.85rem' }}>
                No emails yet. Click "Simulate Incoming Email" or drop a folder into <code>data/inbox/</code>.
              </p>
            ) : (
              <div className="doc-list">
                {items.map(item => (
                  <div
                    key={item.id}
                    className={`doc-card ${selectedId === item.id ? 'selected' : ''}`}
                    onClick={() => handleSelect(item)}
                  >
                    <div className="doc-type-icon" style={{ background: 'rgba(139,92,246,0.12)', color: '#8B5CF6' }}>
                      <Mail size={18} />
                    </div>
                    <div className="doc-card-info">
                      <h4 className="cell-truncate">{item.subject || 'Shipment Documents'}</h4>
                      <p className="cell-truncate">{item.sender || 'unknown sender'}</p>
                      <div className="doc-card-footer">
                        <span className="flex items-center gap-1 text-muted">
                          <Paperclip size={11} /> {item.attachments?.length ?? 0}
                        </span>
                        {statusChip(item)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* RIGHT: Reading pane */}
        <div className="results-panel">
          {!selectedItem && (
            <div className="glass-panel p-6" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '400px' }}>
              <p className="text-muted">Select a message to see the verification result</p>
            </div>
          )}

          {selectedItem && selectedItem.status !== 'processed' && (
            <div className="space-y-6">
              <div className="glass-panel p-6">
                <div className="flex items-center gap-2 mb-2">
                  {selectedItem.status === 'error'
                    ? <XCircle size={20} className="text-error" />
                    : <Loader2 className="animate-spin" size={20} style={{ color: 'var(--accent-primary)' }} />}
                  <h3 className="section-title" style={{ marginBottom: 0 }}>
                    {selectedItem.status === 'error' ? 'Pipeline Failed' : 'Agent is processing this email'}
                  </h3>
                </div>
                {selectedItem.status === 'error' && (
                  <div className="reasoning-block font-mono mt-4" style={{ color: 'var(--status-error)' }}>
                    {selectedItem.error}
                  </div>
                )}
              </div>
              <EmailPreview item={selectedItem} />
            </div>
          )}

          {selectedItem && selectedItem.status === 'processed' && detail && (
            <div className="space-y-6">
              <EmailPreview item={selectedItem} />

              {/* Verification header framing */}
              <div className="upload-mini-bar">
                <div className="flex items-center gap-3" style={{ flexWrap: 'wrap' }}>
                  <span className="font-mono text-gradient-primary" style={{ fontWeight: 700 }}>{detail.id}</span>
                  <span className="text-muted">·</span>
                  <span className="text-muted flex items-center gap-1"><Clock size={12} /> {new Date(selectedItem.received_at || detail.created_at).toLocaleString()}</span>
                  {decisionBadge(detail.decision)}
                </div>
              </div>

              {/* Verification Result — summary */}
              <div className="stat-row">
                {(() => {
                  const matches = detail.validations.filter(v => v.match_result === 'match').length;
                  const mismatches = detail.validations.filter(v => v.match_result === 'mismatch').length;
                  const uncertain = detail.validations.filter(v => v.match_result === 'uncertain').length;
                  return (
                    <>
                      <div className="stat-card">
                        <div className="stat-value" style={{ color: 'var(--accent-primary)' }}>{detail.document_count}</div>
                        <div className="stat-label">Attachments</div>
                      </div>
                      <div className="stat-card">
                        <div className="stat-value" style={{ color: 'var(--status-success)' }}>{matches}</div>
                        <div className="stat-label">Fields Match</div>
                      </div>
                      <div className="stat-card">
                        <div className="stat-value" style={{ color: 'var(--status-error)' }}>{mismatches}</div>
                        <div className="stat-label">Mismatches</div>
                      </div>
                      <div className="stat-card">
                        <div className="stat-value" style={{ color: 'var(--status-warning)' }}>{uncertain}</div>
                        <div className="stat-label">Uncertain</div>
                      </div>
                      <div className="stat-card">
                        <div className="stat-value">{detail.overall_confidence ? `${(detail.overall_confidence * 100).toFixed(0)}%` : '—'}</div>
                        <div className="stat-label">Avg Confidence</div>
                      </div>
                    </>
                  );
                })()}
              </div>

              {/* Document tabs */}
              <div className="glass-panel p-4">
                <h4 className="doc-nav-title">Attachments ({detail.documents.length})</h4>
                <div className="flex gap-2" style={{ flexWrap: 'wrap' }}>
                  {detail.documents.map((doc, i) => {
                    const config = DOC_TYPE_CONFIG[doc.document_type] || { icon: FileText, label: doc.document_type, color: '#6B7280' };
                    const Icon = config.icon;
                    const status = getDocStatus(doc, detail.validations);
                    const stats = getDocStats(doc, detail.validations);
                    return (
                      <button
                        key={doc.id}
                        onClick={() => setSelectedDocIndex(i)}
                        className={`btn-secondary ${i === selectedDocIndex ? 'active' : ''}`}
                        style={{
                          display: 'flex', alignItems: 'center', gap: '0.4rem',
                          borderColor: i === selectedDocIndex ? config.color : undefined,
                        }}
                      >
                        <Icon size={14} style={{ color: config.color }} />
                        {config.label}
                        {status === 'success' && <CheckCircle size={13} className="text-success" />}
                        {status === 'error' && <XCircle size={13} className="text-error" />}
                        {status === 'warning' && <AlertTriangle size={13} className="text-warning" />}
                        {stats.total > 0 && <span className="text-muted" style={{ fontSize: '0.75rem' }}>({stats.matches}/{stats.total})</span>}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Verification Result — field-by-field (click a row for Discrepancy Detail) */}
              {selectedDoc && (
                <div className="glass-panel p-6">
                  <div className="results-doc-header">
                    <h3 className="section-title" style={{ marginBottom: 0 }}>
                      {DOC_TYPE_CONFIG[selectedDoc.document_type]?.label || selectedDoc.document_type}
                    </h3>
                    {confidenceBadge(selectedDoc.extraction_confidence_avg)}
                  </div>
                  <FieldResultsTable doc={selectedDoc} validations={detail.validations} />
                </div>
              )}

              {/* Cross-document consistency */}
              {detail.cross_validation && <CrossDocTable crossValidation={detail.cross_validation} />}

              {/* Agent reasoning */}
              <div className="glass-panel p-6">
                <h3 className="section-title">Agent Reasoning</h3>
                <div className="reasoning-block font-mono">{detail.decision_reasoning}</div>
              </div>

              {/* Draft reply — CG must click Send, agent never sends on its own */}
              <DraftEmailPanel
                decision={detail.decision}
                draftEmail={draftEmail}
                onDraftChange={setDraftEmail}
                onApprove={handleApprove}
                onSendAmendment={handleSendAmendment}
                recipientEmail={selectedItem.sender}
              />

              {(detail.status === 'approved' || detail.status === 'amendment_sent') && (
                <div className="glass-panel p-4 flex items-center gap-2" style={{ color: 'var(--status-success)' }}>
                  <RotateCcw size={16} />
                  Reply sent. This shipment is no longer pending review.
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
