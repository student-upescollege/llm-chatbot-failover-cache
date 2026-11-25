import React, { useState, useEffect, useRef } from 'react';

// Generates a random session id, e.g. s-7f3a
function generateSessionId() {
  const rand = Math.random().toString(36).substring(2, 8);
  return `s-${rand}`;
}

export default function App() {
  const [sessionId, setSessionId] = useState('');
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('You are a helpful and concise AI assistant.');
  const [showSystemPrompt, setShowSystemPrompt] = useState(false);
  const [simulateFailure, setSimulateFailure] = useState('');
  const [loading, setLoading] = useState(false);
  const [backendUrl, setBackendUrl] = useState(
    import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'
  );

  const messagesEndRef = useRef(null);

  // Initialize a new session on page load
  useEffect(() => {
    const newId = generateSessionId();
    setSessionId(newId);
  }, []);

  // Auto scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleNewSession = () => {
    const newId = generateSessionId();
    setSessionId(newId);
    setMessages([]);
  };

  const handleSendMessage = async (e) => {
    if (e) e.preventDefault();
    const trimmed = inputMessage.trim();
    if (!trimmed || loading) return;

    // Add user message to UI immediately
    const userMsg = {
      role: 'user',
      content: trimmed
    };
    setMessages((prev) => [...prev, userMsg]);
    setInputMessage('');
    setLoading(true);

    try {
      const headers = {
        'Content-Type': 'application/json'
      };
      if (simulateFailure.trim()) {
        headers['X-Simulate-Failure'] = simulateFailure.trim();
      }

      const payload = {
        session_id: sessionId,
        message: trimmed,
        system_prompt: systemPrompt.trim() ? systemPrompt.trim() : undefined
      };

      const res = await fetch(`${backendUrl}/chat`, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        const detailMsg = errorData.detail 
          ? (typeof errorData.detail === 'string' ? errorData.detail : JSON.stringify(errorData.detail))
          : `HTTP Error ${res.status}`;

        // Show error as a readable message in the chat, never a blank screen
        setMessages((prev) => [
          ...prev,
          {
            role: 'error',
            content: `Error (${res.status}): ${detailMsg}`
          }
        ]);
        return;
      }

      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.reply,
          metadata: data.metadata
        }
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'error',
          content: `Network / Gateway Error: ${err.message}`
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', maxWidth: '1000px', margin: '0 auto', padding: '16px', boxSizing: 'border-box' }}>
      {/* Top Header */}
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', background: '#1e293b', borderRadius: '12px', marginBottom: '12px', border: '1px solid #334155' }}>
        <div>
          <h1 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#38bdf8', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span>⚡</span> LLM Gateway Chatbot
          </h1>
          <p style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
            Key Failover Pool &bull; Response Caching &bull; SQLite Multi-Turn
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <span style={{ fontSize: '0.75rem', background: '#0f172a', padding: '4px 8px', borderRadius: '6px', color: '#cbd5e1', border: '1px solid #334155' }}>
            Session: <code style={{ color: '#38bdf8' }}>{sessionId}</code>
          </span>
          <button
            onClick={handleNewSession}
            style={{ padding: '6px 12px', background: '#2563eb', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontSize: '0.8rem', fontWeight: 600 }}
          >
            + New Chat
          </button>
        </div>
      </header>

      {/* Control Panel: System Prompt & Failure Simulation */}
      <div style={{ background: '#1e293b', padding: '10px 14px', borderRadius: '8px', marginBottom: '12px', border: '1px solid #334155', fontSize: '0.85rem' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              type="button"
              onClick={() => setShowSystemPrompt(!showSystemPrompt)}
              style={{ background: 'transparent', border: '1px solid #475569', color: '#cbd5e1', padding: '4px 8px', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem' }}
            >
              {showSystemPrompt ? 'Hide System Prompt' : '⚙️ Custom System Prompt'}
            </button>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <label style={{ color: '#94a3b8', fontSize: '0.8rem' }}>Simulate Failure:</label>
            <select
              value={simulateFailure}
              onChange={(e) => setSimulateFailure(e.target.value)}
              style={{ background: '#0f172a', color: '#f8fafc', border: '1px solid #475569', borderRadius: '4px', padding: '4px 8px', fontSize: '0.8rem' }}
            >
              <option value="">None (Normal Execution)</option>
              <option value="key_1=429">key_1=429 (Failover to Key 2)</option>
              <option value="key_1=500">key_1=500 (Failover to Key 2)</option>
              <option value="*=429">*=429 (All Keys Fail -&gt; 503)</option>
            </select>
          </div>
        </div>

        {showSystemPrompt && (
          <div style={{ marginTop: '8px' }}>
            <input
              data-testid="system-prompt-input"
              type="text"
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="Set custom system prompt for this session..."
              style={{ width: '100%', padding: '8px 10px', background: '#0f172a', border: '1px solid #475569', borderRadius: '6px', color: '#f8fafc', fontSize: '0.85rem' }}
            />
          </div>
        )}
      </div>

      {/* Chat Messages List */}
      <div style={{ flex: 1, overflowY: 'auto', background: '#111827', padding: '16px', borderRadius: '12px', border: '1px solid #1f2937', display: 'flex', flexDirection: 'column', gap: '14px' }}>
        {messages.length === 0 && (
          <div style={{ textAlign: 'center', margin: 'auto', color: '#64748b' }}>
            <p style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '6px' }}>Ready for multi-turn conversation</p>
            <p style={{ fontSize: '0.85rem' }}>Send a message to test inference, caching, and failover.</p>
          </div>
        )}

        {messages.map((msg, index) => {
          if (msg.role === 'user') {
            return (
              <div key={index} style={{ alignSelf: 'flex-end', maxWidth: '80%' }}>
                <div style={{ background: '#2563eb', color: '#ffffff', padding: '10px 14px', borderRadius: '14px 14px 2px 14px', fontSize: '0.95rem', lineHeight: '1.5' }}>
                  {msg.content}
                </div>
              </div>
            );
          }

          if (msg.role === 'error') {
            return (
              <div key={index} style={{ alignSelf: 'flex-start', maxWidth: '85%' }}>
                <div style={{ background: '#7f1d1d', border: '1px solid #ef4444', color: '#fecaca', padding: '10px 14px', borderRadius: '14px 14px 14px 2px', fontSize: '0.9rem' }}>
                  <strong>⚠️ Gateway Error:</strong> {msg.content}
                </div>
              </div>
            );
          }

          // Assistant message with REQUIRED data-testid attributes
          const meta = msg.metadata || {};
          const isCache = meta.resolution_source === 'LLM_CACHE';

          return (
            <div key={index} data-testid="assistant-message" style={{ alignSelf: 'flex-start', maxWidth: '85%', background: '#1e293b', border: '1px solid #334155', borderRadius: '14px 14px 14px 2px', padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div style={{ color: '#f8fafc', fontSize: '0.95rem', lineHeight: '1.6', whiteSpace: 'pre-wrap' }}>
                {msg.content}
              </div>

              {/* Required Metadata Elements */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center', paddingTop: '8px', borderTop: '1px solid #334155', fontSize: '0.75rem' }}>
                {/* Resolution Source */}
                <span
                  data-testid="meta-source"
                  style={{
                    padding: '2px 8px',
                    borderRadius: '4px',
                    fontWeight: 700,
                    background: isCache ? '#065f46' : '#581c87',
                    color: isCache ? '#34d399' : '#e9d5ff',
                    border: `1px solid ${isCache ? '#059669' : '#7e22ce'}`
                  }}
                >
                  {meta.resolution_source}
                </span>

                {/* Model */}
                <span style={{ color: '#94a3b8' }}>
                  Model: <span data-testid="meta-model" style={{ color: '#e2e8f0', fontWeight: 600 }}>{meta.model}</span>
                </span>

                {/* Latency */}
                <span style={{ color: '#94a3b8' }}>
                  Latency: <span data-testid="meta-latency" style={{ color: '#38bdf8', fontWeight: 600 }}>{meta.latency_ms} ms</span>
                </span>

                {/* Tokens */}
                <span style={{ color: '#94a3b8' }}>
                  Tokens: In <span data-testid="meta-input-tokens" style={{ color: '#fbbf24', fontWeight: 600 }}>{meta.input_tokens}</span> / Out <span data-testid="meta-output-tokens" style={{ color: '#fbbf24', fontWeight: 600 }}>{meta.output_tokens}</span>
                </span>

                {/* Key ID & Fallback (Optional display for extra clarity) */}
                {meta.key_id && (
                  <span style={{ color: '#94a3b8' }}>
                    Key: <code style={{ color: '#a78bfa' }}>{meta.key_id}</code>
                  </span>
                )}
                {meta.fallback_attempts > 0 && (
                  <span style={{ color: '#f87171', fontWeight: 600 }}>
                    (Failed over: {meta.fallback_attempts} key{meta.fallback_attempts > 1 ? 's' : ''})
                  </span>
                )}
              </div>
            </div>
          );
        })}

        {loading && (
          <div style={{ alignSelf: 'flex-start', color: '#94a3b8', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 12px' }}>
            <span style={{ display: 'inline-block', animation: 'spin 1s linear infinite' }}>⏳</span> Calling Gateway...
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Box Form */}
      <form onSubmit={handleSendMessage} style={{ marginTop: '12px', display: 'flex', gap: '8px' }}>
        <textarea
          data-testid="chat-input"
          value={inputMessage}
          onChange={(e) => setInputMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type your message... (Press Enter to send)"
          rows={2}
          style={{
            flex: 1,
            padding: '10px 14px',
            background: '#1e293b',
            border: '1px solid #334155',
            borderRadius: '8px',
            color: '#f8fafc',
            resize: 'none',
            fontSize: '0.95rem'
          }}
        />
        <button
          data-testid="send-button"
          type="submit"
          disabled={loading || !inputMessage.trim()}
          style={{
            padding: '0 20px',
            background: loading || !inputMessage.trim() ? '#475569' : '#2563eb',
            color: '#ffffff',
            border: 'none',
            borderRadius: '8px',
            cursor: loading || !inputMessage.trim() ? 'not-allowed' : 'pointer',
            fontWeight: 600,
            fontSize: '0.95rem'
          }}
        >
          Send
        </button>
      </form>
    </div>
  );
}
