import { useState } from 'react';
import { Loader2, Search, ChevronDown, ChevronUp } from 'lucide-react';
import { queryNL, type QueryResult } from '../lib/api';

export default function QueryTab() {
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
        <h3 className="section-title"><Search size={20} /> Query the Knowledge Base</h3>
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
            style={{ padding: '0 2rem', whiteSpace: 'nowrap' }}
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
                <pre className="input-field font-mono" style={{ background: 'rgba(0,0,0,0.4)', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{result.sql}</pre>
                <p className="text-muted" style={{ marginTop: '0.5rem', fontSize: '0.85rem' }}>{result.explanation}</p>
              </div>
            )}
          </div>

          {result.results.length > 0 && (
            <div className="glass-panel p-6" style={{ overflowX: 'auto' }}>
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
                <p className="text-muted" style={{ textAlign: 'center', marginTop: '1rem', fontSize: '0.85rem' }}>
                  Showing 20 of {result.results.length} results
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
