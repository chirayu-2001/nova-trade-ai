import { Mail, Paperclip, Clock } from 'lucide-react';
import type { InboxItem } from '../../lib/api';

interface Props {
  item: InboxItem;
}

/**
 * Renders the raw incoming SU email — from, subject, received time, body,
 * and attachment names — the way a CG operator would actually read it in
 * a mailbox, before any agent verification results are shown.
 */
export default function EmailPreview({ item }: Props) {
  return (
    <div className="glass-panel p-6">
      <div className="flex items-center gap-2 mb-3">
        <Mail size={18} style={{ color: '#8B5CF6' }} />
        <h3 className="section-title" style={{ marginBottom: 0 }}>
          {item.subject || 'Shipment Documents'}
        </h3>
      </div>

      <div className="text-muted" style={{ fontSize: '0.85rem', marginBottom: '1rem' }}>
        <div>
          <strong style={{ color: 'var(--text-secondary)' }}>From:</strong>{' '}
          {item.sender || 'unknown sender'}
        </div>
        {item.received_at && (
          <div className="flex items-center gap-1 mt-1">
            <Clock size={12} /> {new Date(item.received_at).toLocaleString()}
          </div>
        )}
      </div>

      {item.body && <div className="reasoning-block mb-4">{item.body}</div>}

      {!!item.attachments?.length && (
        <div className="flex gap-2" style={{ flexWrap: 'wrap' }}>
          {item.attachments.map(name => (
            <span key={name} className="badge badge-neutral">
              <Paperclip size={11} /> {name}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
