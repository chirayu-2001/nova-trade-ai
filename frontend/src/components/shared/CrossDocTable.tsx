import { AlertTriangle } from 'lucide-react';
import type { ShipmentDetail } from '../../lib/api';
import { statusIcon, fieldLabel } from '../../lib/helpers';

interface Props {
  crossValidation: NonNullable<ShipmentDetail['cross_validation']>;
}

/** Cross-document consistency table — same field (consignee, HS code,
 * weight, ...) compared across every attachment in the shipment. This is
 * the Part 2 "cross-validate" requirement made visible to the CG operator. */
export default function CrossDocTable({ crossValidation }: Props) {
  if (!crossValidation.has_cross_doc_issues) return null;

  return (
    <div className="glass-panel p-6" style={{ borderLeft: '4px solid var(--status-error)' }}>
      <h3 className="section-title" style={{ color: 'var(--status-error)', marginBottom: '1rem' }}>
        <AlertTriangle size={20} /> Cross-Document Discrepancies
      </h3>
      <table className="data-grid">
        <thead>
          <tr>
            <th>Field</th>
            {crossValidation.field_results[0] &&
              Object.keys(crossValidation.field_results[0].values_by_doc).map(doc => (
                <th key={doc}>{fieldLabel(doc)}</th>
              ))
            }
            <th style={{ textAlign: 'center' }}>Status</th>
          </tr>
        </thead>
        <tbody>
          {crossValidation.field_results.map((f, i) => (
            <tr key={i} className={f.status === 'mismatch' ? 'grid-row-error' : ''}>
              <td style={{ fontWeight: 600 }}>{fieldLabel(f.field_name)}</td>
              {Object.entries(f.values_by_doc).map(([doc, val]) => (
                <td
                  key={doc}
                  className="font-mono"
                  style={{
                    color: f.mismatching_documents.includes(doc) ? 'var(--status-error)' : 'inherit',
                    fontWeight: f.mismatching_documents.includes(doc) ? 700 : 400,
                  }}
                >
                  {val || '—'}
                </td>
              ))}
              <td style={{ textAlign: 'center' }}>{statusIcon(f.status)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
