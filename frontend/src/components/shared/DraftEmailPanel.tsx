import { Send, CheckCircle } from 'lucide-react';

interface Props {
  decision: string | null;
  draftEmail: string;
  onDraftChange: (value: string) => void;
  onApprove: () => void;
  onSendAmendment: () => void;
  /** SU address this reply would go to — shown in Part 2's email-framed UI. */
  recipientEmail?: string | null;
}

/**
 * Editable draft reply — the Part 2 "Draft reply" state. The agent only
 * ever proposes text here; nothing is transmitted until a human clicks one
 * of the buttons below, which call the same CG-only approve/send-amendment
 * endpoints the backend exposes. There is no code path from the pipeline
 * itself to an outbound send.
 */
export default function DraftEmailPanel({
  decision, draftEmail, onDraftChange, onApprove, onSendAmendment, recipientEmail,
}: Props) {
  if (!draftEmail) {
    return decision ? (
      <div className="glass-panel p-6 flex gap-4">
        <button onClick={onApprove} className="btn-success">
          <CheckCircle size={16} /> Mark as Approved
        </button>
      </div>
    ) : null;
  }

  return (
    <div className="glass-panel p-6">
      <h3 className="section-title">
        <Send size={20} /> Draft Reply {recipientEmail ? `to ${recipientEmail}` : '(Editable)'}
      </h3>
      <p className="text-muted mb-4" style={{ fontSize: '0.85rem' }}>
        Review and edit the draft below before sending. The agent never sends emails automatically —
        a CG operator must click Send.
      </p>
      <textarea
        value={draftEmail}
        onChange={e => onDraftChange(e.target.value)}
        className="input-field font-mono"
        style={{ minHeight: '200px' }}
      />
      <div className="flex gap-4 mt-4">
        {decision === 'amendment_required' && (
          <button onClick={onSendAmendment} className="btn-danger">
            <Send size={16} /> Send Amendment to Supplier
          </button>
        )}
        <button onClick={onApprove} className="btn-success">
          <CheckCircle size={16} /> {decision === 'approved' ? 'Confirm Approval' : 'Force Approve'}
        </button>
      </div>
    </div>
  );
}
