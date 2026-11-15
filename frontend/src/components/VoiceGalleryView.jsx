import React, { useState } from 'react';
import { Globe, Download, Check, Search, Sparkles, Loader2 } from 'lucide-react';

export default function VoiceGalleryView({
  installedVoices,
  remoteCatalog,
  onDownloadVoice,
  downloadingVoiceKey,
}) {
  const [search, setSearch] = useState('');

  const installedKeys = new Set(installedVoices.map((v) => v.key));

  const catalogEntries = Object.entries(remoteCatalog || {});
  const filtered = catalogEntries.filter(([key, data]) => {
    const q = search.toLowerCase().trim();
    if (!q) return true;
    const langCode = data?.language?.code?.toLowerCase() || '';
    const langName = data?.language?.name_english?.toLowerCase() || '';
    return key.toLowerCase().includes(q) || langCode.includes(q) || langName.includes(q);
  });

  // Sort: Installed first, then Hindi & English
  filtered.sort(([a], [b]) => {
    const aInst = installedKeys.has(a);
    const bInst = installedKeys.has(b);
    if (aInst !== bInst) return aInst ? -1 : 1;
    const aHi = a.startsWith('hi');
    const bHi = b.startsWith('hi');
    if (aHi !== bHi) return aHi ? -1 : 1;
    return a.localeCompare(b);
  });

  return (
    <div className="flex-1 flex flex-col overflow-hidden p-6 max-w-6xl mx-auto w-full">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 pb-5 shrink-0">
        <div>
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            <Globe className="w-5 h-5 text-brand-light" />
            Hugging Face Voice Gallery
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Discover and install lightweight Piper neural voice models directly to your local drive.
          </p>
        </div>

        <div className="relative w-72">
          <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search Hindi, English, Spanish..."
            className="w-full bg-dark-900 border border-dark-800 rounded-xl pl-9 pr-3.5 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-brand"
          />
        </div>
      </div>

      {/* Grid of Voices */}
      <div className="flex-1 overflow-y-auto pr-2 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 auto-rows-max">
        {filtered.map(([key, data]) => {
          const isInstalled = installedKeys.has(key);
          const isDownloading = downloadingVoiceKey === key;
          const langName = data?.language?.name_english || 'Unknown';
          const langCode = data?.language?.code || '';
          const quality = data?.quality || 'medium';
          const isHindi = key.startsWith('hi');

          return (
            <div
              key={key}
              className="bg-dark-900 border border-dark-800 rounded-2xl p-4 flex flex-col justify-between gap-4 card-hover shadow-lg"
            >
              <div>
                <div className="flex items-center justify-between gap-2 mb-2">
                  <span className="text-base">{isHindi ? '🇮🇳' : '🇺🇸'}</span>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-dark-800 text-slate-400 border border-dark-700">
                    {quality}
                  </span>
                </div>

                <h4 className="text-sm font-bold text-white truncate" title={key}>
                  {key}
                </h4>
                <p className="text-xs text-slate-400 mt-0.5">
                  {langName} ({langCode})
                </p>
              </div>

              <div className="pt-3 border-t border-dark-800/80 flex items-center justify-between">
                <span className="text-[11px] text-slate-500 font-mono">
                  {data?.num_speakers || 1} speaker(s)
                </span>

                {isInstalled ? (
                  <span className="flex items-center gap-1.5 text-xs font-semibold text-emerald-400">
                    <Check className="w-3.5 h-3.5" />
                    Installed
                  </span>
                ) : (
                  <button
                    onClick={() => onDownloadVoice(key)}
                    disabled={Boolean(downloadingVoiceKey)}
                    className="py-1.5 px-3 bg-dark-800 hover:bg-brand text-slate-300 hover:text-white rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-all active:scale-95 disabled:opacity-50"
                  >
                    {isDownloading ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        Downloading...
                      </>
                    ) : (
                      <>
                        <Download className="w-3.5 h-3.5" />
                        Install
                      </>
                    )}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
