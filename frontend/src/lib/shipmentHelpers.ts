import { FileText, Anchor, Receipt, ClipboardList, Award } from 'lucide-react';
import type { DocumentDetail, FieldValidation } from './api';

export const DOC_TYPE_CONFIG: Record<string, { icon: typeof FileText; label: string; color: string }> = {
  bill_of_lading: { icon: Anchor, label: 'Bill of Lading', color: '#3B82F6' },
  commercial_invoice: { icon: Receipt, label: 'Commercial Invoice', color: '#8B5CF6' },
  packing_list: { icon: ClipboardList, label: 'Packing List', color: '#10B981' },
  certificate_of_origin: { icon: Award, label: 'Certificate of Origin', color: '#F59E0B' },
};

export interface MergedField {
  name: string;
  value: string | null;
  confidence: number;
  sourceSnippet: string | null;
  validation: {
    result: string;
    expected: string | null;
    severity: string;
    reasoning: string | null;
    sourceSnippet: string | null;
  } | null;
}

function docValidationsFor(doc: DocumentDetail, validations: FieldValidation[]): FieldValidation[] {
  return validations.filter(v =>
    v.document_id === doc.id || (!v.document_id && v.document_type === doc.document_type)
  );
}

/** Merge extracted fields with their validation outcome, issues surfaced first. */
export function getMergedFields(doc: DocumentDetail, validations: FieldValidation[]): MergedField[] {
  const docValidations = docValidationsFor(doc, validations);

  const fields: MergedField[] = [];
  for (const [fieldName, fieldData] of Object.entries(doc.extracted_data || {})) {
    if (fieldName === 'document_type') continue;
    const val = docValidations.find(v => v.field_name === fieldName);
    fields.push({
      name: fieldName,
      value: fieldData?.value ?? null,
      confidence: fieldData?.confidence ?? 0,
      sourceSnippet: fieldData?.source_snippet ?? null,
      validation: val ? {
        result: val.match_result,
        expected: val.expected_value,
        severity: val.severity,
        reasoning: val.reasoning,
        sourceSnippet: val.source_snippet,
      } : null,
    });
  }

  fields.sort((a, b) => {
    const aIssue = a.validation && a.validation.result !== 'match' ? 1 : 0;
    const bIssue = b.validation && b.validation.result !== 'match' ? 1 : 0;
    if (aIssue !== bIssue) return bIssue - aIssue;
    return a.name.localeCompare(b.name);
  });

  return fields;
}

export function getDocStats(doc: DocumentDetail, validations: FieldValidation[]) {
  const docVals = docValidationsFor(doc, validations);
  return {
    matches: docVals.filter(v => v.match_result === 'match').length,
    mismatches: docVals.filter(v => v.match_result === 'mismatch').length,
    uncertain: docVals.filter(v => v.match_result === 'uncertain').length,
    total: docVals.length,
  };
}

export function getDocStatus(doc: DocumentDetail, validations: FieldValidation[]): 'success' | 'error' | 'warning' {
  const docVals = docValidationsFor(doc, validations);
  if (docVals.some(v => v.match_result === 'mismatch' && (v.severity === 'critical' || v.severity === 'high'))) return 'error';
  if (docVals.some(v => v.match_result === 'uncertain' || v.match_result === 'mismatch')) return 'warning';
  return 'success';
}
