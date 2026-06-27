const API = '/api';

export interface UploadResponse {
  shipment_id: string;
  status: string;
  message: string;
}

export interface ShipmentSummary {
  id: string;
  customer_id: string;
  customer_name: string;
  status: string;
  decision: string | null;
  decision_reasoning: string | null;
  draft_email: string | null;
  overall_confidence: number;
  document_count: number;
  created_at: string;
}

export interface FieldValidation {
  field_name: string;
  found_value: string | null;
  expected_value: string | null;
  match_result: string;
  match_confidence: number;
  extraction_confidence: number;
  severity: string;
  reasoning: string | null;
  source_snippet: string | null;
  document_type: string | null;
  document_id: string | null;
}

export interface DocumentDetail {
  id: string;
  document_type: string;
  file_name: string;
  file_path?: string;
  extracted_data: Record<string, { value: string | null; confidence: number; source_snippet: string | null }>;
  extraction_confidence_avg: number;
  processing_time_ms: number;
}

export interface ShipmentDetail extends ShipmentSummary {
  documents: DocumentDetail[];
  validations: FieldValidation[];
  cross_validation?: {
    field_results: Array<{
      field_name: string;
      values_by_doc: Record<string, string | null>;
      status: string;
      mismatching_documents: string[];
      severity: string;
      master_value: string | null;
    }>;
    has_cross_doc_issues: boolean;
    summary: string;
  };
}

export interface QueryResult {
  question: string;
  sql: string;
  explanation: string;
  results: Record<string, unknown>[];
  answer: string;
  error: string | null;
}

export interface SampleShipment {
  id: string;
  route: string;
  trade: string;
  quality: string;
  errors: string[];
  description: string;
  shipper: string;
  consignee: string;
}

export async function uploadDocuments(files: File[], customerId: string): Promise<UploadResponse> {
  const form = new FormData();
  files.forEach(f => form.append('files', f));
  form.append('customer_id', customerId);
  const res = await fetch(`${API}/upload`, { method: 'POST', body: form });
  return res.json();
}

export async function processSample(folder: string, customerId: string) {
  const form = new FormData();
  form.append('shipment_folder', folder);
  form.append('customer_id', customerId);
  const res = await fetch(`${API}/process-sample`, { method: 'POST', body: form });
  return res.json();
}

export function documentFileUrl(documentId: string): string {
  return `${API}/documents/${documentId}/file`;
}

export async function getShipments(): Promise<ShipmentSummary[]> {
  const res = await fetch(`${API}/shipments`);
  return res.json();
}

export async function getShipmentDetail(id: string): Promise<ShipmentDetail> {
  const res = await fetch(`${API}/shipments/${id}`);
  return res.json();
}

export async function approveShipment(id: string) {
  return fetch(`${API}/shipments/${id}/approve`, { method: 'PUT' }).then(r => r.json());
}

export async function sendAmendment(id: string, email: string) {
  return fetch(`${API}/shipments/${id}/send-amendment`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ edited_email: email }),
  }).then(r => r.json());
}

export async function queryNL(question: string): Promise<QueryResult> {
  const res = await fetch(`${API}/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  });
  return res.json();
}

export async function getSampleShipments(): Promise<Record<string, SampleShipment>> {
  const res = await fetch(`${API}/sample-shipments`);
  return res.json();
}

export async function getCustomers(): Promise<Array<{ customer_id: string; customer_name: string; rule_count: number }>> {
  const res = await fetch(`${API}/customers`);
  return res.json();
}

export function subscribePipelineStatus(shipmentId: string, onEvent: (data: Record<string, unknown>) => void): EventSource {
  const es = new EventSource(`${API}/pipeline/${shipmentId}/status`);
  es.onmessage = (e) => {
    try {
      onEvent(JSON.parse(e.data));
    } catch { /* ignore parse errors */ }
  };
  return es;
}
