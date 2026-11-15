import React from 'react';
import { FolderArchive, Play, Layers, Sliders, Calendar, FileAudio } from 'lucide-react';

export default function ProjectsView({
  projects,
  onLoadProject,
  onPlayAudio,
}) {
  if (!projects || projects.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
        <div className="w-16 h-16 rounded-2xl bg-dark-900 border border-dark-800 flex items-center justify-center text-slate-500 mb-4">
          <FolderArchive className="w-8 h-8" />
        </div>
        <h3 className="text-base font-bold text-white mb-1">No Projects Found</h3>
        <p className="text-xs text-slate-400 max-w-sm">
          Your synthesized stories and audiobooks will automatically be saved and organized here.
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden p-6 max-w-6xl mx-auto w-full">
      {/* Header */}
      <div className="pb-5 shrink-0">
        <h2 className="text-lg font-bold text-white flex items-center gap-2">
          <FolderArchive className="w-5 h-5 text-brand-light" />
          Projects & Story Library
        </h2>
        <p className="text-xs text-slate-400 mt-0.5">
          Review, play, and re-pack past audiobooks and synthesized narration files.
        </p>
      </div>

      {/* Grid of Projects */}
      <div className="flex-1 overflow-y-auto pr-2 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 auto-rows-max">
        {projects.map((proj) => {
          const dateStr = proj.updated_at ? proj.updated_at.split('T')[0] : 'Recent';

          return (
            <div
              key={proj.id}
              className="bg-dark-900 border border-dark-800 rounded-2xl p-5 flex flex-col justify-between gap-5 card-hover shadow-xl"
            >
              <div>
                <div className="flex items-center justify-between gap-2 mb-2">
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-dark-800 text-brand-light border border-dark-700/60">
                    {proj.blocks} blocks
                  </span>
                  <span className="flex items-center gap-1 text-[11px] text-slate-500">
                    <Calendar className="w-3 h-3" />
                    {dateStr}
                  </span>
                </div>

                <h3 className="text-base font-bold text-white truncate" title={proj.name}>
                  {proj.name}
                </h3>
                <p className="text-xs text-slate-400 mt-1 flex items-center gap-1.5">
                  <FileAudio className="w-3.5 h-3.5 text-slate-500" />
                  Voice: {proj.voice_key || 'Default'}
                </p>
              </div>

              {/* Action Buttons */}
              <div className="pt-3 border-t border-dark-800 flex items-center gap-2">
                <button
                  onClick={() => onLoadProject(proj.id, 'blocks')}
                  className="flex-1 py-2 px-3 bg-dark-800 hover:bg-dark-700 border border-dark-700/60 rounded-xl text-xs font-semibold text-slate-300 hover:text-white flex items-center justify-center gap-1.5 transition-all"
                >
                  <Layers className="w-3.5 h-3.5 text-brand-light" />
                  Review Blocks
                </button>
                <button
                  onClick={() => onLoadProject(proj.id, 'mixer')}
                  className="p-2 bg-dark-800 hover:bg-dark-700 border border-dark-700/60 rounded-xl text-xs font-semibold text-slate-300 hover:text-white transition-all"
                  title="Mixer Studio"
                >
                  <Sliders className="w-3.5 h-3.5 text-amber-400" />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
