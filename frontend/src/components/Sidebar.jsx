import React from 'react';
import { Mic, Sliders, Layers, Globe, FolderArchive, Sparkles, ShieldCheck } from 'lucide-react';

export default function Sidebar({ activeTab, setActiveTab, currentProject }) {
  const navItems = [
    { id: 'studio', label: 'Studio Workspace', icon: Mic, badge: null },
    { id: 'blocks', label: 'Block Review', icon: Layers, badge: currentProject ? `${currentProject.blocks?.length || 0}` : null },
    { id: 'mixer', label: 'Podcast & Mixer', icon: Sliders, badge: null },
    { id: 'gallery', label: 'Voice Gallery', icon: Globe, badge: null },
    { id: 'projects', label: 'Projects & History', icon: FolderArchive, badge: null },
  ];

  return (
    <aside className="w-64 bg-dark-900 border-r border-dark-800 flex flex-col justify-between p-4 select-none shrink-0">
      <div>
        {/* Brand Header */}
        <div className="flex items-center gap-3 px-2 py-3 mb-6">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-brand to-brand-accent flex items-center justify-center shadow-lg shadow-brand/20">
            <Mic className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="font-bold text-base tracking-tight text-white flex items-center gap-1.5">
              Voice Studio
              <span className="text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded bg-brand/20 text-brand-light">AI</span>
            </h1>
            <p className="text-xs text-slate-400 font-medium">Local & Offline Studio</p>
          </div>
        </div>

        {/* Navigation List */}
        <nav className="space-y-1.5">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all ${
                  isActive
                    ? 'bg-brand text-white shadow-md shadow-brand/25 font-semibold'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-dark-800'
                }`}
              >
                <div className="flex items-center gap-3">
                  <Icon className={`w-4 h-4 ${isActive ? 'text-white' : 'text-slate-400'}`} />
                  <span>{item.label}</span>
                </div>
                {item.badge && (
                  <span className={`text-[11px] px-2 py-0.5 rounded-full font-bold ${
                    isActive ? 'bg-white/20 text-white' : 'bg-dark-800 text-slate-400'
                  }`}>
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Bottom Info Box */}
      <div className="p-3.5 rounded-xl bg-dark-850 border border-dark-800 space-y-2">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
          <ShieldCheck className="w-4 h-4 text-emerald-400" />
          <span>100% Offline & Private</span>
        </div>
        <p className="text-[11px] text-slate-500 leading-relaxed">
          Inference runs locally on CPU/ONNX. Zero cloud latency or API billing.
        </p>
      </div>
    </aside>
  );
}
