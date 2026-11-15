import React, { useState } from 'react';
import { Play, Check, Zap, Layers, RefreshCw, Volume2, Search, Edit3 } from 'lucide-react';

export default function BlockReviewView({
  project,
  voices,
  onPlayAudio,
  onUpdateBlock,
  onFastRepack,
  isRepacking,
}) {
  const [filterQuery, setFilterQuery] = useState('');
  const [editingBlockId, setEditingBlockId] = useState(null);
  const [editText, setEditText] = useState('');
  const [renderingBlockId, setRenderingBlockId] = useState(null);

  if (!project || !project.blocks || project.blocks.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
        <div className="w-16 h-16 rounded-2xl bg-dark-900 border border-dark-800 flex items-center justify-center text-slate-500 mb-4">
          <Layers className="w-8 h-8" />
        </div>
        <h3 className="text-base font-bold text-white mb-1">No Active Project Loaded</h3>
        <p className="text-xs text-slate-400 max-w-sm mb-4">
          Generate an audio project in the Studio Workspace first, or load an existing project from Projects & History.
        </p>
      </div>
    );
  }

  const filteredBlocks = project.blocks.filter((b) =>
    !filterQuery || b.text.toLowerCase().includes(filterQuery.toLowerCase())
  );

  const startEdit = (block) => {
    setEditingBlockId(block.id);
    setEditText(block.text);
  };

  const saveEdit = async (blockId) => {
    if (!editText.trim()) return;
    setRenderingBlockId(blockId);
    await onUpdateBlock(blockId, { text: editText.trim() });
    setEditingBlockId(null);
    setRenderingBlockId(null);
  };

  const handleVoiceChange = async (blockId, voiceKey) => {
    setRenderingBlockId(blockId);
    await onUpdateBlock(blockId, { voice_key: voiceKey });
    setRenderingBlockId(null);
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden p-6">
      {/* Top Header Bar */}
      <div className="flex items-center justify-between gap-4 pb-5 shrink-0">
        <div>
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <Layers className="w-5 h-5 text-brand-light" />
            Block Review & Dialogue Studio
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Project: <strong className="text-slate-200">{project.name}</strong> • {project.blocks.length} sentence blocks
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative w-64">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
            <input
              type="text"
              value={filterQuery}
              onChange={(e) => setFilterQuery(e.target.value)}
              placeholder="Filter blocks..."
              className="w-full bg-dark-900 border border-dark-800 rounded-xl pl-9 pr-3.5 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-brand"
            />
          </div>

          <button
            onClick={onFastRepack}
            disabled={isRepacking}
            className="py-2 px-4 bg-brand hover:bg-brand-hover text-white text-xs font-bold rounded-xl shadow-md shadow-brand/20 flex items-center gap-2 transition-all active:scale-98 disabled:opacity-50"
          >
            <Zap className={`w-3.5 h-3.5 ${isRepacking ? 'animate-spin' : 'fill-current'}`} />
            {isRepacking ? 'Re-Packing Master...' : '⚡ Fast Re-Pack Master'}
          </button>
        </div>
      </div>

      {/* Blocks Cards Timeline */}
      <div className="flex-1 overflow-y-auto space-y-3 pr-2">
        {filteredBlocks.map((block) => {
          const isEditing = editingBlockId === block.id;
          const isRendering = renderingBlockId === block.id;
          const hasAudio = Boolean(block.audio_file);

          return (
            <div
              key={block.id}
              className="bg-dark-900 border border-dark-800 rounded-2xl p-4 transition-all card-hover flex flex-col sm:flex-row sm:items-center justify-between gap-4"
            >
              {/* Left: ID & Content */}
              <div className="flex items-start gap-3.5 flex-1">
                <span className="w-8 h-8 rounded-xl bg-dark-800 text-brand-light border border-dark-700/60 font-mono text-xs font-bold flex items-center justify-center shrink-0">
                  #{block.id}
                </span>

                <div className="flex-1">
                  {isEditing ? (
                    <div className="space-y-2">
                      <textarea
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                        className="w-full bg-dark-950 border border-brand/50 rounded-xl p-2.5 text-xs text-white focus:outline-none resize-none"
                        rows={2}
                      />
                      <div className="flex gap-2">
                        <button
                          onClick={() => saveEdit(block.id)}
                          className="px-3 py-1 bg-brand text-white text-xs font-semibold rounded-lg"
                        >
                          Save & Render
                        </button>
                        <button
                          onClick={() => setEditingBlockId(null)}
                          className="px-3 py-1 bg-dark-800 text-slate-400 text-xs rounded-lg"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <p
                      onDoubleClick={() => startEdit(block)}
                      className="text-xs sm:text-sm text-slate-200 leading-relaxed cursor-text group"
                      title="Double-click to edit text"
                    >
                      {block.text}
                      <Edit3 className="w-3 h-3 text-slate-500 inline-block ml-2 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </p>
                  )}

                  {/* Badges row */}
                  <div className="flex items-center gap-3 mt-2 text-[11px]">
                    <span className={`px-2 py-0.5 rounded-full font-bold uppercase tracking-wider text-[10px] ${
                      block.status === 'completed'
                        ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                        : block.status === 'failed'
                        ? 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
                        : 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                    }`}>
                      {block.status}
                    </span>

                    {block.duration > 0 && (
                      <span className="text-slate-400 font-mono">
                        ⏱ {block.duration.toFixed(2)}s
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* Right: Multi-Voice assignment & Actions */}
              <div className="flex items-center gap-3 shrink-0 self-end sm:self-center">
                {/* Voice selector per block */}
                <select
                  value={block.voice_key || ''}
                  onChange={(e) => handleVoiceChange(block.id, e.target.value)}
                  className="bg-dark-950 border border-dark-700/80 rounded-xl px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-brand cursor-pointer max-w-[140px] truncate"
                >
                  <option value="">Default Voice</option>
                  {voices.map((v) => (
                    <option key={v.key} value={v.key}>
                      {v.name}
                    </option>
                  ))}
                </select>

                {/* Play Button */}
                <button
                  onClick={() => {
                    if (block.audio_file) {
                      onPlayAudio(`/api/audio?path=${project.project_dir}/${block.audio_file}`, `Block #${block.id}`);
                    }
                  }}
                  disabled={!hasAudio || isRendering}
                  className="p-2 rounded-xl bg-dark-800 hover:bg-dark-700 text-brand-light hover:text-white border border-dark-700/60 disabled:opacity-30 disabled:cursor-not-allowed transition-all active:scale-95"
                  title="Play Block Audio"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                </button>

                {/* Re-render Button */}
                <button
                  onClick={() => saveEdit(block.id)}
                  disabled={isRendering}
                  className="p-2 rounded-xl bg-dark-800 hover:bg-dark-700 text-slate-400 hover:text-amber-400 border border-dark-700/60 disabled:opacity-50 transition-all active:scale-95"
                  title="Re-render this block"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isRendering ? 'animate-spin text-amber-400' : ''}`} />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
