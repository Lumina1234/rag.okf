import React, { useState, useEffect, useRef } from 'react';
import { BarChart3, ChevronDown, ChevronUp, Table, Eye, Download, AlertCircle, RefreshCw } from 'lucide-react';

export const InlineChart = ({ chartData }) => {
  const chartRef = useRef(null);
  const [plotlyJson, setPlotlyJson] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // 1. Resolve plotly JSON (either from chartData or by fetching chart_url)
  useEffect(() => {
    let isMounted = true;

    const resolveData = async () => {
      if (!chartData) return;
      setError(null);
      setLoading(true);

      let pJson = chartData.plotly_json;
      if (typeof pJson === 'string') {
        try {
          pJson = JSON.parse(pJson);
        } catch (e) {
          console.warn('Could not parse chartData.plotly_json string:', e);
        }
      }

      // If plotly_json is already an object with data, use it directly
      if (pJson && typeof pJson === 'object' && Array.isArray(pJson.data)) {
        if (isMounted) {
          setPlotlyJson(pJson);
          setLoading(false);
        }
        return;
      }

      // If not present but chart_url exists, fetch it
      if (chartData.chart_url) {
        try {
          const res = await fetch(chartData.chart_url);
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const fetched = await res.json();
          if (isMounted) {
            setPlotlyJson(fetched);
            setLoading(false);
          }
          return;
        } catch (err) {
          console.warn('Failed to fetch chart JSON from chart_url:', err);
        }
      }

      if (isMounted) {
        setPlotlyJson(pJson);
        setLoading(false);
      }
    };

    resolveData();
    return () => { isMounted = false; };
  }, [chartData]);

  // 2. Ensure Plotly script is loaded and render chart
  useEffect(() => {
    if (!chartRef.current || !plotlyJson) return;

    let cancelled = false;
    let pollCount = 0;

    const loadAndRender = () => {
      // Check if Plotly is available on window
      if (window.Plotly) {
        doRender();
        return;
      }

      // Ensure script tag exists if not loaded
      if (!document.getElementById('plotly-local-script')) {
        const script = document.createElement('script');
        script.id = 'plotly-local-script';
        script.src = '/plotly.min.js';
        script.async = true;
        document.head.appendChild(script);
      }

      // Poll until window.Plotly is ready
      const interval = setInterval(() => {
        if (cancelled) {
          clearInterval(interval);
          return;
        }
        pollCount++;
        if (window.Plotly) {
          clearInterval(interval);
          doRender();
        } else if (pollCount > 50) { // 50 * 150ms = 7.5s
          clearInterval(interval);
          if (!cancelled) {
            setError('Visualization engine timed out loading.');
          }
        }
      }, 150);
    };

    const doRender = () => {
      if (!chartRef.current || !plotlyJson || cancelled) return;

      try {
        const rawLayout = plotlyJson.layout || {};
        const layout = {
          ...rawLayout,
          autosize: true,
          paper_bgcolor: 'transparent',
          plot_bgcolor: 'rgba(15, 23, 42, 0.4)',
          font: { color: '#cbd5e1', family: 'Inter, system-ui, sans-serif' },
          margin: { l: 55, r: 25, t: 30, b: 50 },
          xaxis: {
            ...(rawLayout.xaxis || {}),
            gridcolor: 'rgba(255, 255, 255, 0.08)',
            tickfont: { color: '#94a3b8' },
          },
          yaxis: {
            ...(rawLayout.yaxis || {}),
            gridcolor: 'rgba(255, 255, 255, 0.08)',
            tickfont: { color: '#94a3b8' },
          },
        };

        const config = {
          responsive: true,
          displayModeBar: true,
          displaylogo: false,
          modeBarButtonsToRemove: ['lasso2d', 'select2d'],
          toImageButtonOptions: {
            format: 'png',
            filename: chartData?.title || 'analytics_chart',
            height: 500,
            width: 800,
            scale: 2,
          },
        };

        const data = Array.isArray(plotlyJson.data) ? plotlyJson.data : [];
        window.Plotly.newPlot(chartRef.current, data, layout, config);
        setError(null);
      } catch (err) {
        console.error('Error rendering Plotly chart:', err);
        setError('Error rendering chart: ' + err.message);
      }
    };

    loadAndRender();

    const handleResize = () => {
      if (window.Plotly && chartRef.current) {
        window.Plotly.Plots.resize(chartRef.current);
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      cancelled = true;
      window.removeEventListener('resize', handleResize);
    };
  }, [plotlyJson]);

  if (!chartData) return null;

  // Fallback data extraction for simple HTML bar visualization if Plotly fails or is loading
  const firstTrace = plotlyJson?.data?.[0];
  const hasFallbackData = firstTrace?.x && firstTrace?.y && Array.isArray(firstTrace.x);

  return (
    <div style={{
      background: 'rgba(15, 23, 42, 0.85)',
      border: '1px solid rgba(99, 102, 241, 0.3)',
      borderRadius: '12px',
      padding: '16px',
      marginTop: '16px',
      marginBottom: '16px',
      boxShadow: '0 8px 24px rgba(0, 0, 0, 0.35)',
    }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '12px',
        paddingBottom: '8px',
        borderBottom: '1px solid rgba(255, 255, 255, 0.06)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <BarChart3 size={16} color="#818cf8" />
          <span style={{ fontSize: '14px', fontWeight: '600', color: '#e2e8f0' }}>
            {chartData.title || 'Data Visualization'}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{
            fontSize: '11px',
            background: 'rgba(99, 102, 241, 0.15)',
            border: '1px solid rgba(99, 102, 241, 0.3)',
            padding: '2px 8px',
            borderRadius: '4px',
            color: '#a5b4fc',
            textTransform: 'uppercase',
            fontWeight: '600'
          }}>
            {chartData.chart_type || 'Plotly'}
          </span>
          {chartData.chart_url && (
            <a
              href={chartData.chart_url}
              target="_blank"
              rel="noreferrer"
              style={{
                fontSize: '11px',
                color: '#94a3b8',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                textDecoration: 'none',
                padding: '2px 6px',
                borderRadius: '4px',
                background: 'rgba(255, 255, 255, 0.05)'
              }}
              title="Open Raw Chart JSON"
            >
              <Eye size={12} /> JSON
            </a>
          )}
        </div>
      </div>

      {/* Main Plotly Chart Container */}
      <div 
        ref={chartRef} 
        style={{ 
          width: '100%', 
          minHeight: '380px',
          display: error ? 'none' : 'block'
        }} 
      />

      {/* Loading indicator if script/data is taking time */}
      {loading && !error && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '240px',
          color: '#94a3b8',
          fontSize: '13px',
          gap: '8px'
        }}>
          <RefreshCw size={16} className="animate-spin" />
          <span>Rendering interactive chart…</span>
        </div>
      )}

      {/* Fallback Bar chart if error or Plotly unavailable */}
      {error && hasFallbackData && (
        <div style={{ padding: '16px 8px' }}>
          <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '12px' }}>
            Displaying direct data visualization:
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {firstTrace.x.map((label, idx) => {
              const val = firstTrace.y[idx];
              const maxVal = Math.max(...firstTrace.y);
              const pct = maxVal > 0 ? (val / maxVal) * 100 : 0;
              return (
                <div key={idx} style={{ fontSize: '12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <span style={{ color: '#e2e8f0', fontWeight: 500 }}>{label}</span>
                    <span style={{ color: '#818cf8', fontWeight: 600 }}>{val}</span>
                  </div>
                  <div style={{
                    width: '100%',
                    height: '8px',
                    background: 'rgba(255, 255, 255, 0.08)',
                    borderRadius: '4px',
                    overflow: 'hidden'
                  }}>
                    <div style={{
                      width: `${pct}%`,
                      height: '100%',
                      background: 'linear-gradient(90deg, #6366f1, #8b5cf6)',
                      borderRadius: '4px'
                    }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

export const DataTablePreview = ({ rawData }) => {
  const [expanded, setExpanded] = useState(false);
  if (!rawData || !Array.isArray(rawData) || rawData.length === 0) return null;

  const columns = Object.keys(rawData[0]);
  const rows = expanded ? rawData : rawData.slice(0, 5);

  return (
    <div style={{
      marginTop: '14px',
      marginBottom: '14px',
      background: 'rgba(15, 23, 42, 0.6)',
      border: '1px solid rgba(255, 255, 255, 0.08)',
      borderRadius: '10px',
      overflow: 'hidden'
    }}>
      <button
        onClick={() => setExpanded(v => !v)}
        style={{
          width: '100%',
          padding: '10px 14px',
          background: 'rgba(255, 255, 255, 0.03)',
          border: 'none',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          cursor: 'pointer',
          color: '#cbd5e1',
          fontSize: '13px',
          fontWeight: '500'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Table size={15} color="#818cf8" />
          <span>Source Data Preview ({rawData.length} rows, {columns.length} columns)</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px', color: '#94a3b8' }}>
          <span>{expanded ? 'Collapse' : 'Show Rows'}</span>
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </div>
      </button>

      {expanded && (
        <div style={{ overflowX: 'auto', maxHeight: '350px' }}>
          <table style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: '12px',
            textAlign: 'left',
          }}>
            <thead>
              <tr style={{ background: 'rgba(30, 41, 59, 0.8)', borderBottom: '1px solid rgba(255, 255, 255, 0.08)' }}>
                {columns.map(col => (
                  <th key={col} style={{ padding: '8px 12px', color: '#94a3b8', fontWeight: '600', whiteSpace: 'nowrap' }}>
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.03)', background: i % 2 === 0 ? 'transparent' : 'rgba(255, 255, 255, 0.015)' }}>
                  {columns.map(col => (
                    <td key={col} style={{ padding: '6px 12px', color: '#e2e8f0', whiteSpace: 'nowrap' }}>
                      {String(row[col] !== null && row[col] !== undefined ? row[col] : '—')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
