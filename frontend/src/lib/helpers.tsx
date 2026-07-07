import { CheckCircle, XCircle, AlertTriangle } from 'lucide-react';

export function confidenceBadge(conf: number) {
  if (conf >= 0.85) return <span className="badge badge-success">{(conf * 100).toFixed(0)}%</span>;
  if (conf >= 0.6) return <span className="badge badge-warning">{(conf * 100).toFixed(0)}%</span>;
  return <span className="badge badge-error">{(conf * 100).toFixed(0)}%</span>;
}

export function statusIcon(result: string) {
  if (result === 'match') return <CheckCircle className="text-success" size={16} />;
  if (result === 'mismatch') return <XCircle className="text-error" size={16} />;
  return <AlertTriangle className="text-warning" size={16} />;
}

export function decisionBadge(decision: string | null) {
  if (decision === 'approved') return <span className="badge badge-success">APPROVED</span>;
  if (decision === 'amendment_required') return <span className="badge badge-error">AMENDMENT REQUIRED</span>;
  if (decision === 'flagged') return <span className="badge badge-warning">FLAGGED FOR REVIEW</span>;
  return <span className="badge badge-neutral">{decision || 'PENDING'}</span>;
}

export function severityBadge(sev: string) {
  const cls = sev === 'critical' ? 'badge-error' : sev === 'high' ? 'badge-warning' : sev === 'medium' ? 'badge-info' : 'badge-neutral';
  return <span className={`badge ${cls}`}>{sev.toUpperCase()}</span>;
}

export function fieldLabel(name: string) {
  return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}
