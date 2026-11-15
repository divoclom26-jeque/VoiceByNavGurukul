import React, { useState } from 'react';
import { Sliders, Music, Disc, BookOpen, Sparkles, CheckCircle2, Loader2 } from 'lucide-react';

export default function MixerView({ project, onProduceMaster, isProducing }) {
  const [musicPath, setMusicPath] = useState('');
  const [musicVol, setMusicVol] = useState(22);
  const [duckingRatio, setDuckingRatio] = useState(6.0);
  const [format, setFormat] = useState('m4b');
  const [title, setTitle] = useState(project?.name || 'My Audiobook');
  const [author, setAuthor] = useState('Voice Studio Creator');
  const [narrator, setNarrator] = useState(project?.voice_key || 'Pratham (Hindi)');

  if (!project) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
        <div className="w-16 h-16 rounded-2xl bg-dark-900 border border-dark-800 flex items-center justify-center text-slate-500 mb-4">
          <Sliders className="w-8 h-8" />
        </div>
        <h3 className="text-base font-bold text-white mb-1">No Project Available to Master</h3>
        <p className="text-xs text-slate-400 max-w-sm">
          Please synthesize a script in the Studio Workspace first to enable music mixing and audiobook mastering.
        </p>
      </div>
    );
  }

  const handleProduce = () => {
    onProduceMaster({
      format,
      music_file: musicPath.trim() || null,
      music_volume: musicVol / 100.0,
      ducking_ratio: duckingRatio,
      title,
      author,
      narrator,
    });
  };

  return (
    <div className="flex-1 flex flex-col overflow-y-auto p-6 max-w-5xl mx-auto w-full">
      {/* Header */}
      <div className="pb-5 shrink-0">
        <h2 className="text-lg font-bold text-white flex items-center gap-2">
          <Sliders className="w-5 h-5 text-brand-light" />
          Podcast & Music Studio (Post-Processing)
        </h2>
        <p className="text-xs text-slate-400 mt-0.5">
          Project: <strong className="text-slate-200">{project.name}</strong> • Mix ambient music, auto-ducking, and export standard M4B audiobooks.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 flex-1">
        {/* Left Card: Music & Ducking */}
        <div className="bg-dark-900 border border-dark-800 rounded-2xl p-5 shadow-xl space-y-5 flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2 mb-4">
              <Music className="w-4 h-4 text-brand-light" />
              Ambient Music & Auto-Ducking
            </h3>

            {/* Music file input */}
            <div className="space-y-1.5">
              <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block">
                Background Music File Path
              </label>
              <input
                type="text"
                value={musicPath}
                onChange={(e) => setMusicPath(e.target.value)}
                placeholder="/absolute/path/to/ambient_music.mp3 (optional)"
                className="w-full bg-dark-950 border border-dark-700/80 rounded-xl px-3.5 py-2 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-brand font-mono"
              />
              <p className="text-[10px] text-slate-500">
                Music automatically loops to match speech length and fades out gracefully.
              </p>
            </div>

            {/* Music Volume */}
            <div className="mt-4">
              <div className="flex justify-between items-center text-xs font-medium text-slate-300 mb-1.5">
                <span>Music Volume</span>
                <span className="font-mono font-bold text-brand-light">{musicVol}%</span>
              </div>
              <input
                type="range"
                min="5"
                max="60"
                step="1"
                value={musicVol}
                onChange={(e) => setMusicVol(parseInt(e.target.value))}
                className="w-full accent-brand h-1.5 bg-dark-800 rounded-lg appearance-none cursor-pointer"
              />
            </div>

            {/* Ducking Intensity */}
            <div className="mt-4">
              <div className="flex justify-between items-center text-xs font-medium text-slate-300 mb-1.5">
                <span>Auto-Ducking Speech Priority</span>
                <span className="font-mono font-bold text-brand-light">{duckingRatio.toFixed(1)}x</span>
              </div>
              <input
                type="range"
                min="3"
                max="14"
                step="0.5"
                value={duckingRatio}
                onChange={(e) => setDuckingRatio(parseFloat(e.target.value))}
                className="w-full accent-brand h-1.5 bg-dark-800 rounded-lg appearance-none cursor-pointer"
              />
              <p className="text-[10px] text-slate-500 mt-1">
                Whenever speech begins, background music automatically lowers in real time.
              </p>
            </div>
          </div>
        </div>

        {/* Right Card: Metadata */}
        <div className="bg-dark-900 border border-dark-800 rounded-2xl p-5 shadow-xl space-y-4 flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2 mb-4">
              <BookOpen className="w-4 h-4 text-brand-light" />
              Audiobook & Podcast Metadata
            </h3>

            <div className="space-y-3">
              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block mb-1">
                  Book / Episode Title
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full bg-dark-950 border border-dark-700/80 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-brand"
                />
              </div>

              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block mb-1">
                  Author / Creator
                </label>
                <input
                  type="text"
                  value={author}
                  onChange={(e) => setAuthor(e.target.value)}
                  className="w-full bg-dark-950 border border-dark-700/80 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-brand"
                />
              </div>

              <div>
                <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block mb-1">
                  Narrator / Voice
                </label>
                <input
                  type="text"
                  value={narrator}
                  onChange={(e) => setNarrator(e.target.value)}
                  className="w-full bg-dark-950 border border-dark-700/80 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-brand"
                />
              </div>
            </div>
          </div>

          {/* Format Selection */}
          <div>
            <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block mb-1.5">
              Target Container
            </label>
            <div className="grid grid-cols-2 gap-2">
              {[
                { id: 'm4b', label: 'M4B Audiobook (Chapters)' },
                { id: 'mp3', label: 'MP3 Podcast (ID3 Tags)' },
                { id: 'flac', label: 'FLAC Lossless Master' },
                { id: 'wav', label: 'WAV Studio Wave' },
              ].map((fmt) => (
                <button
                  key={fmt.id}
                  type="button"
                  onClick={() => setFormat(fmt.id)}
                  className={`py-2 px-3 rounded-xl text-xs font-semibold border transition-all text-left ${
                    format === fmt.id
                      ? 'bg-brand/20 border-brand text-brand-light'
                      : 'bg-dark-950 border-dark-800 text-slate-400 hover:border-dark-700'
                  }`}
                >
                  {fmt.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Production Action Bar */}
      <div className="mt-6 pt-4 border-t border-dark-800 flex items-center justify-end">
        <button
          onClick={handleProduce}
          disabled={isProducing}
          className="py-3 px-6 bg-gradient-to-r from-brand to-brand-accent hover:from-brand-hover hover:to-brand text-white font-bold text-sm rounded-xl shadow-lg shadow-brand/25 flex items-center gap-2 transition-all active:scale-98 disabled:opacity-50"
        >
          {isProducing ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Mastering Audio Track...
            </>
          ) : (
            <>
              <Sparkles className="w-4 h-4" />
              Produce Final Mastered Audio
            </>
          )}
        </button>
      </div>
    </div>
  );
}
