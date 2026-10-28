/**
 * Summarization API helper.
 * Calls POST /api/summarize with streaming SSE (same pattern as streamChat).
 */
export async function streamSummarize({
  inputType = 'auto',
  content = null,
  url = null,
  documentId = null,
  workspaceId = null,
  summaryType = 'quick',
  onSources,
  onToken,
  onDone,
  onError,
}) {
  const token = localStorage.getItem('token');

  try {
    const response = await fetch('/api/summarize', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        input_type: inputType,
        content,
        url,
        document_id: documentId,
        workspace_id: workspaceId,
        summary_type: summaryType,
      }),
    });

    if (!response.ok) {
      onError?.(`Server error: ${response.status}`);
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        if (buffer.trim()) {
          const line = buffer.trim();
          if (line.startsWith('{"type":') && line.includes('"sources"')) {
            try { onSources?.(JSON.parse(line).data); } catch (_) {}
          } else {
            onToken?.(line);
          }
        }
        break;
      }

      buffer += decoder.decode(value, { stream: true });

      let lineEnd;
      while ((lineEnd = buffer.indexOf('\n')) !== -1) {
        const raw = buffer.slice(0, lineEnd).replace(/\r$/, '');
        buffer = buffer.slice(lineEnd + 1);
        if (!raw.trim()) continue;

        if (raw.trim().startsWith('{"type":') && raw.includes('"sources"')) {
          try { onSources?.(JSON.parse(raw.trim()).data); } catch (_) {}
        } else {
          onToken?.(raw);
        }
      }
    }

    onDone?.();
  } catch (err) {
    onError?.(err.message);
  }
}
