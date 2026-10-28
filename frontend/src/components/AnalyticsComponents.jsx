import React, { useState, useEffect, useRef } from 'react';
import { BarChart3, ChevronDown, ChevronUp, Table, Eye, Download } from 'lucide-react';

export const InlineChart = ({ chartData }) => {
  const chartRef = useRef(null);

  useEffect(() => {
    if (!chartRef.current || !chartData?.plotly_json) return;

    const renderChart = () => {
      if (!window.Plotly) return;
      const rawLayout = chartData.plotly_json.layout || {};
      const layout = {
        ...rawLayout,
        autosize: true,
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'rgba(15, 23, 42, 0.4)',
        font: { color: '#cbd5e1', family: 'Inter, system-ui, sans-serif' },
        margin: { l: 55, r: 25, t: 40, b: 50 },
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
          filename: chartData.title || 'analytics_chart',
          height: 500,
          width: 800,
          scale: 2,
        },
      };

      window.Plotly.newPlot(chartRef.current, chartData.plotly_json.data, layout, config);
    };

    renderChart();

    const handleResize = () => {
      if (window.Plotly && chartRef.current) {
        window.Plotly.Plots.resize(chartRef.current);
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [chartData]);

  if (!chartData) return null;

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
      <div ref={chartRef} style={{ width: '100%', minHeight: '380px' }} />
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
          color: '#94a3b8',
          fontSize: '12px',
          fontWeight: '500',
          cursor: 'pointer',
        }}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Table size={14} color="#818cf8" />
          Source Data Preview ({rawData.length} rows, {columns.length} columns)
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#818cf8' }}>
          {expanded ? 'Collapse' : 'Show Rows'} {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </span>
      </button>

      {expanded && (
        <div style={{ overflowX: 'auto', maxHeight: '300px', padding: '8px' }}>
          <table className="data-table" style={{ fontSize: '12px', width: '100%' }}>
            <thead>
              <tr>
                {columns.map((col, idx) => (
                  <th key={idx} style={{ padding: '6px 10px', background: 'rgba(15, 15, 26, 0.8)', color: '#a5b4fc', textAlign: 'left' }}>
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rIdx) => (
                <tr key={rIdx} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                  {Object.values(row).map((val, cIdx) => (
                    <td key={cIdx} style={{ padding: '6px 10px', color: '#cbd5e1' }}>
                      {String(val ?? '')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {rawData.length > 5 && (
            <div style={{ textAlign: 'center', padding: '6px', color: '#64748b', fontSize: '11px' }}>
              Showing {rows.length} of {rawData.length} rows
            </div>
          )}
        </div>
      )}
    </div>
  );
};
