import React, { useState } from 'react';
import { Sparkles, Play, Volume2, Clock, FileText, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';

export default function StudioView({
  text,
  setText,
  projectName,
  setProjectName,
  voices,
  selectedVoice,
  setSelectedVoice,
  speed,
  setSpeed,
  pauseMs,
  setPauseMs,
  onGenerate,
  isGenerating,
  generationProgress,
  onTestVoice,
}) {
  const [format, setFormat] = useState('wav');
  const [normalize, setNormalize] = useState(true);

  // Live Metrics
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;
  const chars = text.length;
  const estSeconds = Math.round((words / 150) * 60);
  const estMin = Math.floor(estSeconds / 60);
  const estSec = estSeconds % 60;
  const estTimeStr = estMin > 0 ? `${estMin}m ${estSec}s` : `${estSec}s`;

  return (
    <div className="flex-1 flex overflow-hidden p-6 gap-6">
      {/* Left Column: Script / Text Editor */}
      <div className="flex-1 flex flex-col bg-dark-900 border border-dark-800 rounded-2xl p-5 shadow-xl overflow-hidden">
        {/* Editor Header */}
        <div className="flex items-center justify-between gap-4 pb-4 border-b border-dark-800 shrink-0">
          <div className="flex-1 max-w-md">
            <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block mb-1">
              Project Title
            </label>
            <input
              type="text"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              placeholder="e.g. The Cosmic Traveler - Chapter 1"
              className="w-full bg-dark-950/80 border border-dark-700/80 rounded-xl px-3.5 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-brand transition-all"
            />
          </div>

          <div className="flex items-center gap-2 self-end">
            <button
              onClick={() => setText('')}
              className="px-3 py-2 text-xs font-medium text-slate-400 hover:text-rose-400 hover:bg-dark-800 rounded-xl transition-all"
            >
              Clear Editor
            </button>
          </div>
        </div>

        {/* Text Area */}
        <div className="flex-1 py-3 overflow-hidden">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Write or paste your script, chapter, or podcast dialogue here...&#10;&#10;Supports Hindi and English. Markdown headers (#), bold text, quotes, and punctuation are automatically normalized."
            className="w-full h-full bg-transparent text-sm leading-relaxed text-slate-200 placeholder-slate-600 resize-none focus:outline-none font-sans"
          />
        </div>

        {/* Bottom Metrics Bar */}
        <div className="pt-3 border-t border-dark-800 flex items-center justify-between text-xs text-slate-400 shrink-0 font-medium">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5 text-brand-light" />
              <strong className="text-white">{words.toLocaleString()}</strong> words
            </span>
            <span>•</span>
            <span>
              <strong className="text-white">{chars.toLocaleString()}</strong> characters
            </span>
            <span>•</span>
            <span className="flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-amber-400" />
              Est. read: <strong className="text-white">~{estTimeStr}</strong>
            </span>
          </div>

          <div className="text-[11px] text-slate-500">
            Smart Punctuation Chunker active (280 chars/block)
          </div>
        </div>
      </div>

      {/* Right Column: Audio & Voice Controls */}
      <div className="w-80 flex flex-col bg-dark-900 border border-dark-800 rounded-2xl p-5 shadow-xl shrink-0 overflow-y-auto">
        <h2 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
          <Volume2 className="w-4 h-4 text-brand-light" />
          Voice & Studio Settings
        </h2>

        <div className="space-y-5 flex-1">
          {/* Voice Selector */}
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block mb-1.5">
              Speaker Voice Model
            </label>
            <select
              value={selectedVoice}
              onChange={(e) => setSelectedVoice(e.target.value)}
              className="w-full bg-dark-950 border border-dark-700 rounded-xl px-3 py-2.5 text-sm text-white focus:outline-none focus:border-brand transition-all cursor-pointer"
            >
              {voices.map((v) => {
                const isHindi = v.language.startsWith('hi');
                return (
                  <option key={v.key} value={v.key}>
                    {isHindi ? '🇮🇳' : '🇺🇸'} {v.name} ({v.language})
                  </option>
                );
              })}
            </select>

            <button
              onClick={() => onTestVoice(selectedVoice, speed)}
              className="w-full mt-2 py-2 px-3 bg-dark-800 hover:bg-dark-700 border border-dark-700/60 rounded-xl text-xs font-semibold text-slate-300 hover:text-white flex items-center justify-center gap-2 transition-all active:scale-98"
            >
              <Play className="w-3 h-3 fill-current" />
              Test Voice Sample
            </button>
          </div>

          {/* Speed Slider */}
          <div>
            <div className="flex justify-between items-center text-xs font-medium text-slate-300 mb-1.5">
              <span>Speech Speed</span>
              <span className="font-mono font-bold text-brand-light">{speed.toFixed(2)}x</span>
            </div>
            <input
              type="range"
              min="0.5"
              max="2.0"
              step="0.05"
              value={speed}
              onChange={(e) => setSpeed(parseFloat(e.target.value))}
              className="w-full accent-brand h-1.5 bg-dark-800 rounded-lg appearance-none cursor-pointer"
            />
          </div>

          {/* Pause Between Chunks */}
          <div>
            <div className="flex justify-between items-center text-xs font-medium text-slate-300 mb-1.5">
              <span>Sentence Pause</span>
              <span className="font-mono font-bold text-brand-light">{pauseMs} ms</span>
            </div>
            <input
              type="range"
              min="100"
              max="1000"
              step="50"
              value={pauseMs}
              onChange={(e) => setPauseMs(parseInt(e.target.value))}
              className="w-full accent-brand h-1.5 bg-dark-800 rounded-lg appearance-none cursor-pointer"
            />
          </div>

          {/* Master Format */}
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block mb-1.5">
              Master Format
            </label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setFormat('wav')}
                className={`py-2 px-3 rounded-xl text-xs font-semibold border transition-all ${
                  format === 'wav'
                    ? 'bg-brand/20 border-brand text-brand-light'
                    : 'bg-dark-950 border-dark-800 text-slate-400 hover:border-dark-700'
                }`}
              >
                WAV (Lossless)
              </button>
              <button
                type="button"
                onClick={() => setFormat('mp3')}
                className={`py-2 px-3 rounded-xl text-xs font-semibold border transition-all ${
                  format === 'mp3'
                    ? 'bg-brand/20 border-brand text-brand-light'
                    : 'bg-dark-950 border-dark-800 text-slate-400 hover:border-dark-700'
                }`}
              >
                MP3 (192 kbps)
              </button>
            </div>
          </div>

          {/* EBU R128 Loudnorm */}
          <label className="flex items-center gap-2.5 p-3 rounded-xl bg-dark-950 border border-dark-800/80 cursor-pointer">
            <input
              type="checkbox"
              checked={normalize}
              onChange={(e) => setNormalize(e.target.checked)}
              className="rounded accent-brand w-4 h-4 cursor-pointer"
            />
            <div className="text-xs">
              <span className="font-semibold text-white block">EBU R128 Loudnorm</span>
              <span className="text-[11px] text-slate-400">Broadcast standard levels</span>
            </div>
          </label>
        </div>

        {/* Action Button & Active Progress */}
        <div className="pt-4 border-t border-dark-800 shrink-0">
          {isGenerating ? (
            <div className="space-y-2 p-3 bg-dark-950 rounded-xl border border-brand/30">
              <div className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-2 font-medium text-brand-light">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  {generationProgress.message || 'Synthesizing...'}
                </span>
                <span className="font-mono text-slate-400">
                  {generationProgress.current} / {generationProgress.total}
                </span>
              </div>
              <div className="w-full h-1.5 bg-dark-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-brand transition-all duration-300 rounded-full"
                  style={{
                    width: `${generationProgress.total > 0 ? (generationProgress.current / generationProgress.total) * 100 : 0}%`,
                  }}
                />
              </div>
            </div>
          ) : (
            <button
              onClick={() => onGenerate({ format, normalize })}
              disabled={!text.trim()}
              className="w-full py-3.5 px-4 bg-gradient-to-r from-brand to-brand-accent hover:from-brand-hover hover:to-brand text-white font-bold text-sm rounded-xl shadow-lg shadow-brand/25 transition-all flex items-center justify-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed active:scale-98"
            >
              <Sparkles className="w-4 h-4" />
              Generate Studio Audio
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
