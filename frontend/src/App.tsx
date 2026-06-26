import { useCallback, useEffect, useState } from 'react';
import {
  CheckCircle, XCircle, AlertTriangle, Upload, Search,
  FileText, Loader2, Send, ChevronDown, ChevronUp, Package
} from 'lucide-react';
import {
  uploadDocuments, processSample, getShipments, getShipmentDetail, queryNL,
  getSampleShipments, getCustomers, approveShipment, sendAmendment,
  subscribePipelineStatus,
  type ShipmentSummary, type ShipmentDetail, type QueryResult, type SampleShipment
} from './lib/api';

// --- Helpers ---

function confidenceBadge(conf: number) {
  if (conf >= 0.85) return <span className="badge badge-success">{(conf * 100).toFixed(0)}%</span>;
  if (conf >= 0.6) return <span className="badge badge-warning">{(conf * 100).toFixed(0)}%</span>;
  return <span className="badge badge-error">{(conf * 100).toFixed(0)}%</span>;
}

function statusIcon(result: string) {
  if (result === 'match') return <CheckCircle className="text-success" size={16} />;
  if (result === 'mismatch') return <XCircle className="text-error" size={16} />;
  return <AlertTriangle className="text-warning" size={16} />;
}

function decisionBadge(decision: string | null) {
  if (decision === 'approved') return <span className="badge badge-success">APPROVED</span>;
  if (decision === 'amendment_required') return <span className="badge badge-error">AMENDMENT REQUIRED</span>;
  if (decision === 'flagged') return <span className="badge badge-warning">FLAGGED FOR REVIEW</span>;
  return <span className="badge badge-neutral">{decision || 'PENDING'}</span>;
}

function severityBadge(sev: string) {
  const badgeClass = sev === 'critical' ? 'badge-error' : sev === 'high' ? 'badge-warning' : sev === 'medium' ? 'badge-info' : 'badge-neutral';
  return <span className={`badge ${badgeClass}`}>{sev.toUpperCase()}</span>;
}

function fieldLabel(name: string) {
  return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

// --- Pipeline Tab ---

function PipelineTab() {
  const [files, setFiles] = useState<File[]>([]);
  const [customerId, setCustomerId] = useState('homestyle_germany');
  const [customers, setCustomers] = useState<Array<{ customer_id: string; customer_name: string }>>([]);
  const [samples, setSamples] = useState<Record<string, SampleShipment>>({});
  const [processing, setProcessing] = useState(false);
  const [pipelineStatus, setPipelineStatus] = useState<string>('');
  const [shipmentId, setShipmentId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ShipmentDetail | null>(null);
  const [expandedField, setExpandedField] = useState<string | null>(null);
  const [draftEmail, setDraftEmail] = useState('');

  useEffect(() => {
    getCustomers().then(setCustomers).catch(() => {});
    getSampleShipments().then(setSamples).catch(() => {});
  }, []);

  const handleUpload = useCallback(async () => {
    if (files.length === 0) return;
    setProcessing(true);
    setPipelineStatus('Uploading...');
    setDetail(null);
    try {
      const res = await uploadDocuments(files, customerId);
      setShipmentId(res.shipment_id);
      setPipelineStatus('Pipeline started...');
      const es = subscribePipelineStatus(res.shipment_id, (data) => {
        setPipelineStatus(data.status as string);
        if (data.status === 'stored' || data.status === 'decided' || data.status === 'error') {
          es.close();
          getShipmentDetail(res.shipment_id).then(d => {
            setDetail(d);
            if (d.draft_email) setDraftEmail(d.draft_email);
            setProcessing(false);
          });
        }
      });
    } catch (e) {
      setPipelineStatus('Error: ' + String(e));
      setProcessing(false);
    }
  }, [files, customerId]);

  const sampleCustomerMap: Record<string, string> = {
    shipment_1: 'american_home_furnishings',
    shipment_2: 'homestyle_germany',
    shipment_3: 'techvista_solutions',
    shipment_4: 'al_baraka_trading',
    shipment_5: 'britfashion_retail',
    shipment_6: 'yamato_automotive',
  };

  const handleSample = useCallback(async (folder: string) => {
    const correctCustomer = sampleCustomerMap[folder] || customerId;
    setCustomerId(correctCustomer);
    setProcessing(true);
    setPipelineStatus('Processing sample...');
    setDetail(null);
    setFiles([]);
    try {
      const res = await processSample(folder, correctCustomer);
      setShipmentId(res.shipment_id);
      const es = subscribePipelineStatus(res.shipment_id, (data) => {
        setPipelineStatus(data.status as string);
        if (data.status === 'stored' || data.status === 'decided' || data.status === 'error') {
          es.close();
          getShipmentDetail(res.shipment_id).then(d => {
            setDetail(d);
            if (d.draft_email) setDraftEmail(d.draft_email);
            setProcessing(false);
          });
        }
      });
    } catch (e) {
      setPipelineStatus('Error: ' + String(e));
      setProcessing(false);
    }
  }, [customerId]);

  const handleApprove = async () => {
    if (!shipmentId) return;
    await approveShipment(shipmentId);
    setDetail(prev => prev ? { ...prev, status: 'approved', decision: 'approved' } : null);
  };

  const handleSendAmendment = async () => {
    if (!shipmentId) return;
    await sendAmendment(shipmentId, draftEmail);
    setDetail(prev => prev ? { ...prev, status: 'amendment_sent' } : null);
  };

  return (
    <div className="space-y-6">
      {/* Customer Selector */}
      <div className="glass-panel p-6">
        <label className="section-title">
          Customer Rule Set
        </label>
        <select
          value={customerId}
          onChange={e => setCustomerId(e.target.value)}
          className="input-field"
          style={{ maxWidth: '300px' }}
        >
          {customers.map(c => (
            <option key={c.customer_id} value={c.customer_id}>{c.customer_name}</option>
          ))}
        </select>
      </div>

      {/* Upload Area */}
      <div className="glass-panel p-6">
        <h3 className="section-title">Upload Documents</h3>
        <div className="upload-zone">
          <Upload className="upload-icon" size={32} style={{ margin: '0 auto 10px' }} />
          <input
            type="file"
            accept=".pdf"
            multiple
            onChange={e => setFiles(Array.from(e.target.files || []))}
            className="upload-input"
          />
          <p className="text-muted">Drag & drop files here, or click to select</p>
          {files.length > 0 && (
            <p className="mt-2 text-gradient-primary" style={{ fontWeight: 600 }}>{files.length} file(s) selected</p>
          )}
        </div>
        <button
          onClick={handleUpload}
          disabled={files.length === 0 || processing}
          className="btn-primary mt-4"
        >
          {processing ? <><Loader2 className="animate-spin" size={16} /> Processing...</> : 'Run Pipeline'}
        </button>
      </div>

      {/* Sample Shipments */}
      <div className="glass-panel p-6">
        <h3 className="section-title">Or Process a Sample Shipment</h3>
        <div className="grid-container">
          {Object.entries(samples).map(([folder, s]) => (
            <div
              key={folder}
              onClick={() => !processing && handleSample(folder)}
              className="card interactive"
              style={{ opacity: processing ? 0.5 : 1 }}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="font-mono text-gradient-primary" style={{ fontSize: '1.1rem', fontWeight: 600 }}>{s.id}</span>
                <span className={`badge ${s.quality === 'clean' ? 'badge-success' : s.quality === 'degraded' ? 'badge-error' : 'badge-warning'}`}>{s.quality}</span>
              </div>
              <p className="text-muted" style={{ fontSize: '0.85rem' }}>{s.route} | {s.trade}</p>
              <p className="text-muted mt-2" style={{ fontSize: '0.85rem' }}>{s.description}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Pipeline Progress */}
      {processing && (
        <div className="glass-panel p-6">
          <div className="flex items-center gap-2 mb-2">
            <Loader2 className="text-info animate-spin" size={20} style={{ color: 'var(--accent-primary)' }}/>
            <span className="text-gradient-primary" style={{ fontWeight: 600, fontSize: '1.1rem' }}>Pipeline Status: {fieldLabel(pipelineStatus)}</span>
          </div>
          <div className="progress-track">
            {['extracting', 'validated', 'cross_validated', 'decided', 'stored'].map((stage) => {
              const stages = ['extracting', 'extracted', 'validating', 'validated', 'cross_validating', 'cross_validated', 'routing', 'decided', 'stored'];
              const current = stages.indexOf(pipelineStatus);
              const stageIdx = stages.indexOf(stage);
              const done = current >= stageIdx;
              const active = current === stageIdx || current === stageIdx - 1;
              return (
                <div key={stage} className={`progress-step ${done ? 'completed' : ''} ${active ? 'active' : ''}`} />
              );
            })}
          </div>
        </div>
      )}

      {/* Results */}
      {detail && (
        <div className="space-y-6 mt-6">
          {/* Decision */}
          <div className="glass-panel p-6" style={{ borderLeft: `4px solid ${detail.decision === 'approved' ? 'var(--status-success)' : detail.decision === 'amendment_required' ? 'var(--status-error)' : 'var(--status-warning)'}` }}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="section-title" style={{ marginBottom: 0 }}>Agent Decision</h3>
              {decisionBadge(detail.decision)}
            </div>
            <div className="input-field font-mono" style={{ padding: '1rem', background: 'rgba(0,0,0,0.3)', whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>
              {detail.decision_reasoning}
            </div>
          </div>

          {/* Validation Results */}
          {detail.validations?.length > 0 && (() => {
            const grouped: Record<string, typeof detail.validations> = {};
            for (const v of detail.validations) {
              const key = v.document_type || 'unknown';
              if (!grouped[key]) grouped[key] = [];
              grouped[key].push(v);
            }
            return (
              <div className="space-y-6">
                {Object.entries(grouped).map(([docType, vals]) => {
                  const mismatches = vals.filter(v => v.match_result === 'mismatch').length;
                  const uncertain = vals.filter(v => v.match_result === 'uncertain').length;
                  const matches = vals.filter(v => v.match_result === 'match').length;
                  return (
                    <div key={docType} className="glass-panel p-6">
                      <div className="flex items-center justify-between mb-2">
                        <h3 className="section-title" style={{ marginBottom: 0, color: 'var(--accent-primary)' }}>
                          <FileText size={20} /> {fieldLabel(docType)}
                        </h3>
                        <div className="flex gap-2">
                          {matches > 0 && <span className="badge badge-success">{matches} Matches</span>}
                          {mismatches > 0 && <span className="badge badge-error">{mismatches} Mismatches</span>}
                          {uncertain > 0 && <span className="badge badge-warning">{uncertain} Uncertain</span>}
                        </div>
                      </div>
                      
                      <table className="data-grid">
                        <thead>
                          <tr>
                            <th style={{ width: '40px' }}></th>
                            <th>Field</th>
                            <th>Found in Document</th>
                            <th>Expected (Rules)</th>
                            <th style={{ textAlign: 'center' }}>Severity</th>
                          </tr>
                        </thead>
                        <tbody>
                          {vals.map((v, i) => (
                            <tr
                              key={i}
                              className={v.match_result === 'mismatch' ? 'grid-row-error' : v.match_result === 'uncertain' ? 'grid-row-warning' : ''}
                            >
                              <td>{statusIcon(v.match_result)}</td>
                              <td style={{ fontWeight: 500 }}>{fieldLabel(v.field_name)}</td>
                              <td className="font-mono" style={{ color: v.match_result !== 'match' ? 'var(--text-primary)' : 'var(--text-secondary)' }}>{v.found_value || '—'}</td>
                              <td className="font-mono" style={{ color: 'var(--text-secondary)' }}>{v.expected_value || '—'}</td>
                              <td style={{ textAlign: 'center' }}>{severityBadge(v.severity)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  );
                })}
              </div>
            );
          })()}

          {/* Cross-Document Validation */}
          {detail.cross_validation?.has_cross_doc_issues && (
            <div className="glass-panel p-6" style={{ borderLeft: '4px solid var(--status-error)' }}>
              <h3 className="section-title text-error" style={{ marginBottom: '1rem' }}>
                <AlertTriangle size={20} /> Cross-Document Discrepancies
              </h3>
              <table className="data-grid">
                <thead>
                  <tr>
                    <th>Field</th>
                    {detail.cross_validation.field_results[0] &&
                      Object.keys(detail.cross_validation.field_results[0].values_by_doc).map(doc => (
                        <th key={doc}>{fieldLabel(doc)}</th>
                      ))
                    }
                    <th style={{ textAlign: 'center' }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.cross_validation.field_results.map((f, i) => (
                    <tr key={i} className={f.status === 'mismatch' ? 'grid-row-error' : ''}>
                      <td style={{ fontWeight: 600 }}>{fieldLabel(f.field_name)}</td>
                      {Object.entries(f.values_by_doc).map(([doc, val]) => (
                        <td key={doc} className="font-mono" style={{ color: f.mismatching_documents.includes(doc) ? 'var(--status-error)' : 'inherit', fontWeight: f.mismatching_documents.includes(doc) ? 700 : 400 }}>
                          {val || '—'}
                        </td>
                      ))}
                      <td style={{ textAlign: 'center' }}>{statusIcon(f.status)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Draft Email */}
          {detail.draft_email && (
            <div className="glass-panel p-6">
              <h3 className="section-title">
                <Send size={20} /> Draft Email (Editable)
              </h3>
              <textarea
                value={draftEmail}
                onChange={e => setDraftEmail(e.target.value)}
                className="input-field font-mono"
              />
              <div className="flex gap-4 mt-4">
                {detail.decision === 'amendment_required' && (
                  <button onClick={handleSendAmendment} className="btn-danger">
                    <Send size={16} /> Send Amendment to Supplier
                  </button>
                )}
                <button onClick={handleApprove} className="btn-success">
                  <CheckCircle size={16} /> Force Approve
                </button>
              </div>
            </div>
          )}

          {/* Action Buttons if no email */}
          {!detail.draft_email && detail.decision && (
            <div className="glass-panel p-6 flex gap-4">
              <button onClick={handleApprove} className="btn-success">
                <CheckCircle size={16} /> Mark as Approved
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// --- Query Tab ---

function QueryTab() {
  const [question, setQuestion] = useState('');
  const [result, setResult] = useState<QueryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [showSql, setShowSql] = useState(false);

  const examples = [
    "How many shipments were processed?",
    "Show me all critical mismatches",
    "What's the average confidence score?",
    "Which fields have the most mismatches?",
  ];

  const handleQuery = async (q?: string) => {
    const query = q || question;
    if (!query.trim()) return;
    setLoading(true);
    setQuestion(query);
    try {
      const res = await queryNL(query);
      setResult(res);
    } catch (e) {
      setResult({ question: query, sql: '', explanation: '', results: [], answer: 'Error: ' + String(e), error: String(e) });
    }
    setLoading(false);
  };

  return (
    <div className="space-y-6">
      <div className="glass-panel p-6">
        <h3 className="section-title">Query the Knowledge Base</h3>
        <div className="flex gap-4">
          <input
            type="text"
            value={question}
            onChange={e => setQuestion(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleQuery()}
            placeholder="Ask a question in plain English..."
            className="input-field"
            style={{ fontSize: '1rem', padding: '1rem' }}
          />
          <button
            onClick={() => handleQuery()}
            disabled={loading || !question.trim()}
            className="btn-primary"
            style={{ padding: '0 2rem' }}
          >
            {loading ? <Loader2 className="animate-spin" size={20} /> : <Search size={20} />} Ask
          </button>
        </div>
        <div className="flex gap-2 mt-4" style={{ flexWrap: 'wrap' }}>
          {examples.map(ex => (
            <button
              key={ex}
              onClick={() => handleQuery(ex)}
              className="badge badge-neutral"
              style={{ cursor: 'pointer', padding: '0.5rem 1rem' }}
            >
              {ex}
            </button>
          ))}
        </div>
      </div>

      {result && (
        <div className="space-y-6">
          <div className="glass-panel p-6" style={{ borderLeft: '4px solid var(--accent-primary)', background: 'var(--accent-primary-transparent)' }}>
            <p style={{ fontSize: '1.1rem', fontWeight: 500 }}>{result.answer}</p>
          </div>

          <div className="glass-panel p-6">
            <button onClick={() => setShowSql(!showSql)} className="btn-secondary" style={{ marginBottom: '1rem' }}>
              {showSql ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              {showSql ? 'Hide Generated SQL' : 'Show Generated SQL'}
            </button>
            {showSql && (
              <div>
                <pre className="input-field font-mono" style={{ background: 'rgba(0,0,0,0.4)' }}>{result.sql}</pre>
                <p className="text-muted mt-2 text-sm">{result.explanation}</p>
              </div>
            )}
          </div>

          {result.results.length > 0 && (
            <div className="glass-panel p-6 overflow-x-auto">
              <table className="data-grid">
                <thead>
                  <tr>
                    {Object.keys(result.results[0]).map(key => (
                      <th key={key}>{key}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.results.slice(0, 20).map((row, i) => (
                    <tr key={i}>
                      {Object.values(row).map((val, j) => (
                        <td key={j} className="font-mono text-muted">{String(val ?? '—')}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {result.results.length > 20 && (
                <p className="text-muted mt-4 text-sm" style={{ textAlign: 'center' }}>Showing 20 of {result.results.length} results</p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// --- Shipments Tab ---

function ShipmentsTab() {
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
          <h3 className="section-title" style={{ marginBottom: 0 }}>Processed Shipments</h3>
          <button onClick={() => getShipments().then(setShipments)} className="btn-secondary text-sm">Refresh</button>
        </div>
        {shipments.length === 0 ? (
          <p className="text-muted text-center" style={{ padding: '2rem 0' }}>No shipments processed yet. Run the pipeline to see results here.</p>
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
                  <td className="text-muted text-sm">{new Date(s.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {detail && (
        <div className="glass-panel p-6">
          <h3 className="section-title">Shipment Details: <span className="font-mono">{detail.id}</span></h3>
          <div className="mb-4">{decisionBadge(detail.decision)}</div>
          <div className="input-field font-mono" style={{ background: 'rgba(0,0,0,0.2)', marginBottom: '1.5rem', whiteSpace: 'pre-wrap' }}>
            {detail.decision_reasoning}
          </div>
          {detail.draft_email && (
            <div>
              <h4 className="section-title text-sm mb-2">Generated Draft Email</h4>
              <div className="input-field font-mono" style={{ background: 'rgba(0,0,0,0.2)', whiteSpace: 'pre-wrap' }}>
                {detail.draft_email}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// --- Main App ---

type Tab = 'pipeline' | 'query' | 'shipments';

export default function App() {
  const [tab, setTab] = useState<Tab>('pipeline');

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'pipeline', label: 'Pipeline Execution', icon: <Package size={18} /> },
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
              <div style={{ width: '12px', height: '12px', borderRadius: '50%', background: 'var(--accent-primary)', boxShadow: 'var(--shadow-glow)' }}></div>
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
        {tab === 'pipeline' && <PipelineTab />}
        {tab === 'query' && <QueryTab />}
        {tab === 'shipments' && <ShipmentsTab />}
      </main>
    </>
  );
}
