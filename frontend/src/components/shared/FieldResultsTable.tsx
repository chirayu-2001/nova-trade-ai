import { Fragment, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { DocumentDetail, FieldValidation } from '../../lib/api';
import { getMergedFields } from '../../lib/shipmentHelpers';
import { confidenceBadge, statusIcon, severityBadge, fieldLabel } from '../../lib/helpers';

interface Props {
  doc: DocumentDetail;
  validations: FieldValidation[];
}

/**
 * Field-by-field extraction + validation table for one document. Clicking a
 * flagged row expands into the "Discrepancy Detail" view — found vs
 * expected vs the exact source snippet from the document — which is the
 * Part 2 "Discrepancy detail" UI state. Shared by the manual Pipeline view
 * and the CG Inbox view so both stay in sync.
 */
export default function FieldResultsTable({ doc, validations }: Props) {
  const [expandedField, setExpandedField] = useState<string | null>(null);
  const mergedFields = getMergedFields(doc, validations);

  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="data-grid">
        <thead>
          <tr>
            <th style={{ width: '36px' }}></th>
            <th>Field</th>
            <th>Extracted Value</th>
            <th style={{ textAlign: 'center', width: '90px' }}>Confidence</th>
            <th>Expected (Rule)</th>
            <th style={{ textAlign: 'center', width: '90px' }}>Severity</th>
          </tr>
        </thead>
        <tbody>
          {mergedFields.map(field => {
            const isExpanded = expandedField === field.name;
            const hasIssue = field.validation && field.validation.result !== 'match';
            const rowClass = field.validation?.result === 'mismatch'
              ? 'grid-row-error'
              : field.validation?.result === 'uncertain'
                ? 'grid-row-warning'
                : '';

            return (
              <Fragment key={field.name}>
                <tr
                  className={`${rowClass} field-row`}
                  onClick={() => setExpandedField(isExpanded ? null : field.name)}
                >
                  <td>
                    {field.validation
                      ? statusIcon(field.validation.result)
                      : <span className="text-muted">—</span>
                    }
                  </td>
                  <td style={{ fontWeight: 500 }}>
                    <span className="flex items-center gap-1">
                      {fieldLabel(field.name)}
                      {hasIssue && (
                        <ChevronDown
                          size={12}
                          style={{
                            color: 'var(--text-muted)',
                            transform: isExpanded ? 'rotate(180deg)' : '',
                            transition: 'transform 0.2s',
                          }}
                        />
                      )}
                    </span>
                  </td>
                  <td className="font-mono cell-truncate" style={{ color: hasIssue ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
                    {field.value || <span className="text-muted">—</span>}
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    {confidenceBadge(field.confidence)}
                  </td>
                  <td className="font-mono cell-truncate" style={{ color: 'var(--text-secondary)' }}>
                    {field.validation?.expected || <span className="text-muted">—</span>}
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    {field.validation ? severityBadge(field.validation.severity) : <span className="text-muted">—</span>}
                  </td>
                </tr>

                {isExpanded && field.validation && (
                  <tr className="field-detail-row">
                    <td colSpan={6} style={{ padding: 0 }}>
                      <div className="field-detail">
                        <div className="field-detail-grid">
                          <div className="field-detail-col">
                            <p className="field-detail-title">Discrepancy Detail</p>
                            <div className="field-detail-items">
                              <div>
                                <span className="text-muted">Found: </span>
                                <span className="font-mono" style={{ color: 'var(--status-error)' }}>{field.value || 'Not found'}</span>
                              </div>
                              <div>
                                <span className="text-muted">Expected: </span>
                                <span className="font-mono" style={{ color: 'var(--status-success)' }}>{field.validation.expected || 'N/A'}</span>
                              </div>
                              <div>
                                <span className="text-muted">Reasoning: </span>
                                <span style={{ color: 'var(--text-secondary)' }}>{field.validation.reasoning || 'No reasoning provided'}</span>
                              </div>
                            </div>
                          </div>
                          {field.sourceSnippet && (
                            <div className="field-detail-col">
                              <p className="field-detail-title">Source in Document</p>
                              <div className="field-detail-snippet font-mono">
                                "{field.sourceSnippet}"
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
