import React, { useEffect, useRef, useState } from 'react';
import WaveSurfer from 'wavesurfer.js';
import { Play, Pause, Square, Volume2, VolumeX, Download, Disc3 } from 'lucide-react';

export default function AudioPlayerBar({ audioUrl, title }) {
  const containerRef = useRef(null);
  const wavesurferRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState('00:00');
  const [duration, setDuration] = useState('00:00');
  const [volume, setVolume] = useState(0.85);
  const [isMuted, setIsMuted] = useState(false);

  const formatTime = (seconds) => {
    if (isNaN(seconds) || seconds < 0) return '00:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  };

  useEffect(() => {
    if (!containerRef.current || !audioUrl) return;

    // Destroy prior instance
    if (wavesurferRef.current) {
      wavesurferRef.current.destroy();
    }

    const ws = WaveSurfer.create({
      container: containerRef.current,
      waveColor: '#383e58',
      progressColor: '#818cf8',
      cursorColor: '#c084fc',
      barWidth: 2,
      barGap: 2,
      barRadius: 2,
      height: 40,
      url: audioUrl,
      normalize: true,
    });

    ws.on('ready', () => {
      setDuration(formatTime(ws.getDuration()));
      ws.setVolume(volume);
      ws.play();
    });

    ws.on('play', () => setIsPlaying(true));
    ws.on('pause', () => setIsPlaying(false));
    ws.on('timeupdate', (curr) => {
      setCurrentTime(formatTime(curr));
    });
    ws.on('finish', () => {
      setIsPlaying(false);
      setCurrentTime('00:00');
    });

    wavesurferRef.current = ws;

    return () => {
      ws.destroy();
    };
  }, [audioUrl]);

  const togglePlay = () => {
    if (!wavesurferRef.current) return;
    wavesurferRef.current.playPause();
  };

  const handleStop = () => {
    if (!wavesurferRef.current) return;
    wavesurferRef.current.stop();
    setIsPlaying(false);
    setCurrentTime('00:00');
  };

  const handleVolumeChange = (e) => {
    const val = parseFloat(e.target.value);
    setVolume(val);
    setIsMuted(val === 0);
    if (wavesurferRef.current) {
      wavesurferRef.current.setVolume(val);
    }
  };

  const toggleMute = () => {
    if (!wavesurferRef.current) return;
    if (isMuted) {
      wavesurferRef.current.setVolume(volume || 0.8);
      setIsMuted(false);
    } else {
      wavesurferRef.current.setVolume(0);
      setIsMuted(true);
    }
  };

  if (!audioUrl) return null;

  return (
    <footer className="h-20 bg-dark-900 border-t border-dark-800 px-6 flex items-center justify-between gap-6 shrink-0 z-40 select-none shadow-2xl">
      {/* Title & Info */}
      <div className="w-56 flex items-center gap-3 shrink-0">
        <div className="w-10 h-10 rounded-lg bg-dark-800 border border-dark-700 flex items-center justify-center shrink-0">
          <Disc3 className={`w-5 h-5 text-brand-light ${isPlaying ? 'animate-spin' : ''}`} />
        </div>
        <div className="truncate">
          <p className="text-xs font-semibold text-white truncate">{title || 'Master Audio'}</p>
          <p className="text-[11px] text-slate-400 font-mono mt-0.5">{currentTime} / {duration}</p>
        </div>
      </div>

      {/* Main Controls & Waveform */}
      <div className="flex-1 flex items-center gap-4 max-w-3xl">
        <div className="flex items-center gap-2">
          <button
            onClick={togglePlay}
            className="w-10 h-10 rounded-full bg-brand hover:bg-brand-hover text-white flex items-center justify-center transition-all shadow-md shadow-brand/30 active:scale-95"
            title={isPlaying ? 'Pause' : 'Play'}
          >
            {isPlaying ? <Pause className="w-4 h-4 fill-current" /> : <Play className="w-4 h-4 fill-current ml-0.5" />}
          </button>
          <button
            onClick={handleStop}
            className="w-8 h-8 rounded-full bg-dark-800 hover:bg-dark-700 text-slate-300 flex items-center justify-center transition-all active:scale-95"
            title="Stop"
          >
            <Square className="w-3.5 h-3.5 fill-current" />
          </button>
        </div>

        {/* Waveform Scrubber */}
        <div className="flex-1 h-10 bg-dark-950/60 rounded-lg px-2 border border-dark-800/80 flex items-center overflow-hidden">
          <div ref={containerRef} className="w-full cursor-pointer" />
        </div>
      </div>

      {/* Volume & Download */}
      <div className="flex items-center gap-3 shrink-0">
        <button
          onClick={toggleMute}
          className="text-slate-400 hover:text-slate-200 transition-colors"
        >
          {isMuted ? <VolumeX className="w-4 h-4 text-rose-400" /> : <Volume2 className="w-4 h-4" />}
        </button>
        <input
          type="range"
          min="0"
          max="1"
          step="0.02"
          value={isMuted ? 0 : volume}
          onChange={handleVolumeChange}
          className="w-20 accent-brand h-1.5 bg-dark-800 rounded-lg appearance-none cursor-pointer"
        />
        <a
          href={audioUrl}
          download={title || 'master.wav'}
          className="p-2 rounded-lg bg-dark-800 hover:bg-dark-700 text-slate-300 hover:text-white transition-all ml-2"
          title="Download File"
        >
          <Download className="w-4 h-4" />
        </a>
      </div>
    </footer>
  );
}
