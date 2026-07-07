import { useCallback, useEffect, useState } from 'react';
import {
  CheckCircle, XCircle, AlertTriangle, Upload, FileText,
  Loader2, Package, RotateCcw, ClipboardList,
  Clock, Zap, Eye, X, ExternalLink, ChevronDown, ChevronUp
} from 'lucide-react';
import {
  uploadDocuments, processSample, getShipmentDetail,
  getSampleShipments, getCustomers, approveShipment, sendAmendment,
  subscribePipelineStatus, documentFileUrl,
  type ShipmentDetail, type SampleShipment, type DocumentDetail
} from '../lib/api';
import { confidenceBadge, decisionBadge, fieldLabel } from '../lib/helpers';
import { DOC_TYPE_CONFIG, getDocStats, getDocStatus } from '../lib/shipmentHelpers';
import FieldResultsTable from './shared/FieldResultsTable';
import CrossDocTable from './shared/CrossDocTable';
import DraftEmailPanel from './shared/DraftEmailPanel';

// --- Constants ---

// Maps each sample shipment folder to the customer rule set it should be validated against.
const SAMPLE_CUSTOMER_MAP: Record<string, string> = {
  'shipment_1': 'american_home_furnishings',
  'shipment_2': 'homestyle_germany',
  'shipment_3': 'techvista_solutions',
  'shipment_4': 'al_baraka_trading',
  'shipment_5': 'britfashion_retail',
  'shipment_6': 'yamato_automotive',
  'shipment_7': 'reliance_global',
  'shipment_8': 'reliance_global',
  'shipment_9': 'reliance_global',
  'shipment_10': 'tata_motors',
  'shipment_11': 'tata_motors',
  'shipment_12': 'tata_motors',
  'shipment_13': 'reliance_global',
  'shipment_14': 'tata_motors',
};

const PIPELINE_STAGES = [
  { key: 'incoming', label: 'Upload' },
  { key: 'extracting', label: 'Extract' },
  { key: 'validated', label: 'Validate' },
  { key: 'cross_validated', label: 'Cross-Check' },
  { key: 'decided', label: 'Decide' },
  { key: 'stored', label: 'Store' },
];

const STAGE_ORDER = [
  'incoming', 'extracting', 'extracted', 'validating', 'validated',
  'cross_validating', 'cross_validated', 'routing', 'decided', 'stored',
];

// --- Main Component ---

export default function PipelineView() {
  // Upload state
  const [files, setFiles] = useState<File[]>([]);
  const [customerId, setCustomerId] = useState('homestyle_germany');
  const [customers, setCustomers] = useState<Array<{ customer_id: string; customer_name: string }>>([]);
  const [samples, setSamples] = useState<Record<string, SampleShipment>>({});

  // Pipeline state
  const [processing, setProcessing] = useState(false);
  const [pipelineStatus, setPipelineStatus] = useState('');
  const [shipmentId, setShipmentId] = useState<string | null>(null);

  // Results state
  const [detail, setDetail] = useState<ShipmentDetail | null>(null);
  const [selectedDocIndex, setSelectedDocIndex] = useState(0);
  const [showConsolidated, setShowConsolidated] = useState(false);
  const [draftEmail, setDraftEmail] = useState('');
  const [viewerDoc, setViewerDoc] = useState<DocumentDetail | null>(null);

  useEffect(() => {
    getCustomers().then(setCustomers).catch(() => {});
    getSampleShipments().then(setSamples).catch(() => {});
  }, []);

  const handleUpload = useCallback(async () => {
    if (files.length === 0) return;
    setProcessing(true);
    setPipelineStatus('incoming');
    setDetail(null);
    setShowConsolidated(false);
    try {
      const res = await uploadDocuments(files, customerId);
      setShipmentId(res.shipment_id);
      const es = subscribePipelineStatus(res.shipment_id, (data) => {
        setPipelineStatus(data.status as string);
        if (['stored', 'decided', 'error'].includes(data.status as string)) {
          es.close();
          getShipmentDetail(res.shipment_id).then(d => {
            setDetail(d);
            setSelectedDocIndex(0);
            if (d.draft_email) setDraftEmail(d.draft_email);
            setProcessing(false);
          });
        }
      });
    } catch {
      setPipelineStatus('error');
      setProcessing(false);
    }
  }, [files, customerId]);

  const handleSample = useCallback(async (folder: string) => {
    // Each sample ships with its own matching customer rule set — apply it automatically.
    const sampleCustomer = SAMPLE_CUSTOMER_MAP[folder] || customerId;
    setCustomerId(sampleCustomer);
    setProcessing(true);
    setPipelineStatus('incoming');
    setDetail(null);
    setShowConsolidated(false);
    setFiles([]);
    try {
      const res = await processSample(folder, sampleCustomer);
      setShipmentId(res.shipment_id);
      const es = subscribePipelineStatus(res.shipment_id, (data) => {
        setPipelineStatus(data.status as string);
        if (['stored', 'decided', 'error'].includes(data.status as string)) {
          es.close();
          getShipmentDetail(res.shipment_id).then(d => {
            setDetail(d);
            setSelectedDocIndex(0);
            if (d.draft_email) setDraftEmail(d.draft_email);
            setProcessing(false);
          });
        }
      });
    } catch {
      setPipelineStatus('error');
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

  const handleReset = () => {
    setDetail(null);
    setShipmentId(null);
    setFiles([]);
    setProcessing(false);
    setPipelineStatus('');
    setShowConsolidated(false);
    setDraftEmail('');
    setSelectedDocIndex(0);
  };

  const customerNameById = Object.fromEntries(customers.map(c => [c.customer_id, c.customer_name]));

  // Determine current phase
  const phase = detail ? 'results' : processing ? 'processing' : 'upload';
  const selectedDoc = detail?.documents?.[selectedDocIndex] || null;
  const currentStageIndex = STAGE_ORDER.indexOf(pipelineStatus);

  return (
    <div className="space-y-6">

      {/* ===== UPLOAD PHASE ===== */}
      {phase === 'upload' && (
        <>
          {/* Customer Selector */}
          <div className="glass-panel p-6">
            <label className="section-title">Customer Rule Set</label>
            <p className="text-muted" style={{ fontSize: '0.85rem', margin: '-0.5rem 0 0.75rem' }}>
              Pick the rule set only when uploading your own files. Sample shipments below already
              know their customer and apply the matching rule set automatically.
            </p>
            <select
              value={customerId}
              onChange={e => setCustomerId(e.target.value)}
              className="input-field"
              style={{ maxWidth: '400px' }}
            >
              {customers.map(c => (
                <option key={c.customer_id} value={c.customer_id}>{c.customer_name}</option>
              ))}
            </select>
          </div>

          {/* Upload Zone */}
          <div className="glass-panel p-6">
            <h3 className="section-title"><Upload size={20} /> Upload Trade Documents</h3>
            <div className="upload-zone">
              <Upload className="upload-icon" size={36} style={{ margin: '0 auto 12px', display: 'block' }} />
              <input
                type="file"
                accept=".pdf"
                multiple
                onChange={e => setFiles(Array.from(e.target.files || []))}
                className="upload-input"
              />
              <p className="text-muted">Drop PDF files here — Bill of Lading, Invoice, Packing List, Certificate of Origin</p>
              <p className="text-muted" style={{ fontSize: '0.8rem', marginTop: '0.5rem' }}>Document types are automatically detected</p>
              {files.length > 0 && (
                <div style={{ marginTop: '1rem' }}>
                  <p className="text-gradient-primary" style={{ fontWeight: 600 }}>{files.length} file(s) selected</p>
                  <div className="flex gap-2" style={{ flexWrap: 'wrap', justifyContent: 'center', marginTop: '0.5rem' }}>
                    {files.map((f, i) => (
                      <span key={i} className="badge badge-neutral">{f.name}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <button
              onClick={handleUpload}
              disabled={files.length === 0}
              className="btn-primary mt-4"
              style={{ width: '100%', padding: '1rem' }}
            >
              <Zap size={18} /> Run Pipeline on {files.length || 0} Document(s)
            </button>
          </div>

          {/* Sample Shipments */}
          <div className="glass-panel p-6">
            <h3 className="section-title"><Package size={20} /> Or Process a Sample Shipment</h3>
            <p className="text-muted" style={{ fontSize: '0.85rem', margin: '-0.5rem 0 1rem' }}>
              Each sample is tagged with the customer rule set it will be validated against — no need to choose one first.
            </p>
            <div className="grid-container">
              {Object.entries(samples).map(([folder, s]) => {
                const ruleId = SAMPLE_CUSTOMER_MAP[folder];
                const ruleName = (ruleId && customerNameById[ruleId]) || ruleId;
                return (
                  <div
                    key={folder}
                    onClick={() => handleSample(folder)}
                    className="card interactive"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-mono text-gradient-primary" style={{ fontSize: '1rem', fontWeight: 600 }}>{s.id}</span>
                    </div>
                    <p className="text-muted" style={{ fontSize: '0.8rem' }}>{s.route} · {s.trade}</p>
                    {ruleName && (
                      <div className="badge badge-neutral sample-rule-badge" title={`Validated against ${ruleName}'s rule set`}>
                        <ClipboardList size={11} /> {ruleName}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}

      {/* ===== PROCESSING PHASE ===== */}
      {phase === 'processing' && (
        <div className="glass-panel p-6">
          <div className="flex items-center gap-2 mb-4">
            <Loader2 className="animate-spin" size={24} style={{ color: 'var(--accent-primary)' }} />
            <h3 className="section-title" style={{ marginBottom: 0 }}>Processing Pipeline</h3>
          </div>
          <p className="text-muted mb-4">
            Shipment <span className="font-mono text-gradient-primary">{shipmentId}</span> · {fieldLabel(pipelineStatus)}
          </p>

          <div className="pipeline-stepper">
            {PIPELINE_STAGES.map((stage, i) => {
              const stageIdx = STAGE_ORDER.indexOf(stage.key);
              const isCompleted = currentStageIndex > stageIdx;
              const isActive = !isCompleted && currentStageIndex >= stageIdx - 1 && currentStageIndex <= stageIdx;
              return (
                <div key={stage.key} className="stepper-step">
                  {i < PIPELINE_STAGES.length - 1 && (
                    <div className={`stepper-line ${isCompleted ? 'completed' : ''}`} />
                  )}
                  <div className={`stepper-dot ${isCompleted ? 'completed' : ''} ${isActive ? 'active' : ''}`}>
                    {isCompleted
                      ? <CheckCircle size={16} />
                      : isActive
                        ? <Loader2 size={14} className="animate-spin" />
                        : <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{i + 1}</span>
                    }
                  </div>
                  <span className={`stepper-label ${isCompleted || isActive ? 'stepper-label-active' : ''}`}>{stage.label}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ===== RESULTS PHASE ===== */}
      {phase === 'results' && detail && (
        <>
          {/* Top Bar */}
          <div className="upload-mini-bar">
            <div className="flex items-center gap-3" style={{ flexWrap: 'wrap' }}>
              <span className="font-mono text-gradient-primary" style={{ fontWeight: 700, fontSize: '1.1rem' }}>{detail.id}</span>
              <span className="text-muted">·</span>
              <span style={{ fontWeight: 500 }}>{detail.customer_name}</span>
              <span className="text-muted">·</span>
              <span className="text-muted">{detail.document_count} doc(s)</span>
              {decisionBadge(detail.decision)}
            </div>
            <button onClick={handleReset} className="btn-secondary" style={{ padding: '0.5rem 1rem', fontSize: '0.85rem' }}>
              <RotateCcw size={14} /> New Analysis
            </button>
          </div>

          {/* Summary Stats */}
          <div className="stat-row">
            {(() => {
              const matches = detail.validations.filter(v => v.match_result === 'match').length;
              const mismatches = detail.validations.filter(v => v.match_result === 'mismatch').length;
              const uncertain = detail.validations.filter(v => v.match_result === 'uncertain').length;
              return (
                <>
                  <div className="stat-card">
                    <div className="stat-value" style={{ color: 'var(--accent-primary)' }}>{detail.document_count}</div>
                    <div className="stat-label">Documents</div>
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

          {/* Split Pane */}
          <div className="split-container">
            {/* LEFT: Document Navigator */}
            <div className="doc-navigator">
              <div className="glass-panel p-4">
                <h4 className="doc-nav-title">Documents ({detail.documents.length})</h4>
                <div className="doc-list">
                  {detail.documents.map((doc, i) => {
                    const config = DOC_TYPE_CONFIG[doc.document_type] || { icon: FileText, label: doc.document_type, color: '#6B7280' };
                    const Icon = config.icon;
                    const status = getDocStatus(doc, detail.validations);
                    const stats = getDocStats(doc, detail.validations);
                    const isSelected = i === selectedDocIndex;
                    return (
                      <div
                        key={doc.id}
                        className={`doc-card ${isSelected ? 'selected' : ''}`}
                        onClick={() => setSelectedDocIndex(i)}
                      >
                        <div className="doc-type-icon" style={{ background: `${config.color}20`, color: config.color }}>
                          <Icon size={20} />
                        </div>
                        <div className="doc-card-info">
                          <h4>{config.label}</h4>
                          <p>{doc.file_name}</p>
                          {stats.total > 0 && (
                            <div className="doc-card-stats">
                              {stats.matches > 0 && <span className="text-success">✓{stats.matches}</span>}
                              {stats.mismatches > 0 && <span className="text-error">✗{stats.mismatches}</span>}
                              {stats.uncertain > 0 && <span className="text-warning">?{stats.uncertain}</span>}
                            </div>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            className="doc-view-btn"
                            title="Preview original document"
                            onClick={(e) => { e.stopPropagation(); setViewerDoc(doc); }}
                          >
                            <Eye size={16} />
                          </button>
                          {status === 'success' && <CheckCircle size={18} className="text-success" />}
                          {status === 'error' && <XCircle size={18} className="text-error" />}
                          {status === 'warning' && <AlertTriangle size={18} className="text-warning" />}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Document Info */}
              {selectedDoc && (
                <div className="glass-panel p-4">
                  <h4 className="doc-nav-title">Document Info</h4>
                  <div className="doc-info-grid">
                    <div className="doc-info-row">
                      <span className="text-muted">Type</span>
                      <span style={{ fontWeight: 500 }}>{DOC_TYPE_CONFIG[selectedDoc.document_type]?.label || selectedDoc.document_type}</span>
                    </div>
                    <div className="doc-info-row">
                      <span className="text-muted">Confidence</span>
                      {confidenceBadge(selectedDoc.extraction_confidence_avg)}
                    </div>
                    <div className="doc-info-row">
                      <span className="text-muted">Processing</span>
                      <span className="flex items-center gap-1" style={{ color: 'var(--text-secondary)' }}>
                        <Clock size={12} /> {(selectedDoc.processing_time_ms / 1000).toFixed(1)}s
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* RIGHT: Results Panel */}
            <div className="results-panel">
              {selectedDoc ? (
                <div className="glass-panel p-6">
                  {/* Document Header */}
                  <div className="results-doc-header">
                    <h3 className="section-title" style={{ marginBottom: 0 }}>
                      {(() => {
                        const config = DOC_TYPE_CONFIG[selectedDoc.document_type];
                        const Icon = config?.icon || FileText;
                        return (
                          <>
                            <Icon size={20} style={{ color: config?.color }} />
                            {config?.label || selectedDoc.document_type}
                          </>
                        );
                      })()}
                    </h3>
                    <div className="flex gap-2">
                      {(() => {
                        const stats = getDocStats(selectedDoc, detail.validations);
                        return (
                          <>
                            {stats.matches > 0 && <span className="badge badge-success">{stats.matches} Match</span>}
                            {stats.mismatches > 0 && <span className="badge badge-error">{stats.mismatches} Mismatch</span>}
                            {stats.uncertain > 0 && <span className="badge badge-warning">{stats.uncertain} Uncertain</span>}
                          </>
                        );
                      })()}
                    </div>
                  </div>

                  {/* Fields Table */}
                  <FieldResultsTable doc={selectedDoc} validations={detail.validations} />
                </div>
              ) : (
                <div className="glass-panel p-6" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '400px' }}>
                  <p className="text-muted">Select a document to view results</p>
                </div>
              )}
            </div>
          </div>

          {/* Consolidated Results Toggle */}
          <button
            className="consolidated-toggle"
            onClick={() => setShowConsolidated(!showConsolidated)}
          >
            {showConsolidated ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
            {showConsolidated ? 'Hide' : 'Show'} Consolidated Results & Actions
          </button>

          {/* Consolidated Section */}
          {showConsolidated && (
            <div className="space-y-6 consolidated-content">
              {/* Decision */}
              <div
                className="glass-panel p-6"
                style={{
                  borderLeft: `4px solid ${
                    detail.decision === 'approved'
                      ? 'var(--status-success)'
                      : detail.decision === 'amendment_required'
                        ? 'var(--status-error)'
                        : 'var(--status-warning)'
                  }`,
                }}
              >
                <div className="flex items-center justify-between mb-4">
                  <h3 className="section-title" style={{ marginBottom: 0 }}>Agent Decision</h3>
                  {decisionBadge(detail.decision)}
                </div>
                <div className="reasoning-block font-mono">
                  {detail.decision_reasoning}
                </div>
              </div>

              {/* Cross-Document Discrepancies */}
              {detail.cross_validation && <CrossDocTable crossValidation={detail.cross_validation} />}

              {/* Draft Email */}
              <DraftEmailPanel
                decision={detail.decision}
                draftEmail={draftEmail}
                onDraftChange={setDraftEmail}
                onApprove={handleApprove}
                onSendAmendment={handleSendAmendment}
              />
            </div>
          )}
        </>
      )}

      {/* ===== DOCUMENT PREVIEW MODAL ===== */}
      {viewerDoc && (
        <div className="pdf-modal-overlay" onClick={() => setViewerDoc(null)}>
          <div className="pdf-modal" onClick={(e) => e.stopPropagation()}>
            <div className="pdf-modal-header">
              <span className="flex items-center gap-2" style={{ fontWeight: 600, minWidth: 0 }}>
                <FileText size={18} style={{ color: 'var(--accent-primary)', flexShrink: 0 }} />
                <span className="cell-truncate">{viewerDoc.file_name}</span>
              </span>
              <div className="flex items-center gap-2">
                <a
                  href={documentFileUrl(viewerDoc.id)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="doc-view-btn"
                  title="Open in new tab"
                >
                  <ExternalLink size={16} />
                </a>
                <button className="doc-view-btn" title="Close" onClick={() => setViewerDoc(null)}>
                  <X size={18} />
                </button>
              </div>
            </div>
            <iframe
              className="pdf-modal-frame"
              src={documentFileUrl(viewerDoc.id)}
              title={viewerDoc.file_name}
            />
          </div>
        </div>
      )}
    </div>
  );
}
