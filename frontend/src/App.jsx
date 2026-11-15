import React, { useEffect, useState } from 'react';
import Sidebar from './components/Sidebar';
import StudioView from './components/StudioView';
import BlockReviewView from './components/BlockReviewView';
import MixerView from './components/MixerView';
import VoiceGalleryView from './components/VoiceGalleryView';
import ProjectsView from './components/ProjectsView';
import AudioPlayerBar from './components/AudioPlayerBar';

export default function App() {
  const [activeTab, setActiveTab] = useState('studio');
  const [voices, setVoices] = useState([]);
  const [remoteCatalog, setRemoteCatalog] = useState({});
  const [selectedVoice, setSelectedVoice] = useState('hi_IN-pratham-medium');
  const [speed, setSpeed] = useState(1.0);
  const [pauseMs, setPauseMs] = useState(350);
  const [text, setText] = useState(
    'एक समय की बात है। एक छोटे से गाँव में एक जिज्ञासु बालक रहता था।\n' +
    'उसका सपना था कि वह एक दिन पूरी दुनिया की सैर करेगा और नई चीजें सीखेगा।\n' +
    'हर शाम वह गाँव के किनारे बैठकर दूर क्षितिज को देखता था।'
  );
  const [projectName, setProjectName] = useState('The Curious Traveler');

  const [currentProject, setCurrentProject] = useState(null);
  const [projectsList, setProjectsList] = useState([]);

  // Audio Player state
  const [audioUrl, setAudioUrl] = useState(null);
  const [audioTitle, setAudioTitle] = useState('');

  // Generation state
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationProgress, setGenerationProgress] = useState({ current: 0, total: 0, message: '' });

  // Download state
  const [downloadingVoiceKey, setDownloadingVoiceKey] = useState(null);

  // Repack state
  const [isRepacking, setIsRepacking] = useState(false);
  const [isProducing, setIsProducing] = useState(false);

  // Fetch initial voices and projects
  const fetchVoices = async () => {
    try {
      const res = await fetch('/api/voices');
      const data = await res.json();
      setVoices(data.installed || []);
      setRemoteCatalog(data.remote_catalog || {});
      if (data.installed?.length > 0 && !selectedVoice) {
        setSelectedVoice(data.installed[0].key);
      }
    } catch (e) {
      console.error('Failed fetching voices:', e);
    }
  };

  const fetchProjects = async () => {
    try {
      const res = await fetch('/api/projects');
      const data = await res.json();
      setProjectsList(data || []);
    } catch (e) {
      console.error('Failed fetching projects:', e);
    }
  };

  useEffect(() => {
    fetchVoices();
    fetchProjects();
  }, []);

  // Handlers
  const handleTestVoice = async (voiceKey, spd) => {
    try {
      const res = await fetch('/api/voices/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ voice_key: voiceKey, speed: spd }),
      });
      const data = await res.json();
      if (data.audio_url) {
        setAudioUrl(data.audio_url);
        setAudioTitle(`Test Sample: ${voiceKey}`);
      }
    } catch (e) {
      alert(`Voice test failed: ${e.message}`);
    }
  };

  const handleGenerate = async ({ format, normalize }) => {
    if (!text.trim()) return;
    setIsGenerating(true);
    setGenerationProgress({ current: 0, total: 10, message: 'Creating project and parsing text...' });

    try {
      // 1. Create project
      const createRes = await fetch('/api/projects/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: projectName,
          text,
          voice_key: selectedVoice,
          speed,
          max_chars: 280,
        }),
      });
      const projData = await createRes.json();
      const slug = projData.slug;

      // 2. Start synthesis
      const synRes = await fetch(`/api/projects/${slug}/synthesize`, { method: 'POST' });
      const synData = await synRes.json();
      const taskId = synData.task_id;

      // 3. Poll task status
      const pollInterval = setInterval(async () => {
        try {
          const tRes = await fetch(`/api/tasks/${taskId}`);
          const tData = await tRes.json();

          setGenerationProgress({
            current: tData.current || 0,
            total: tData.total || 1,
            message: tData.message || 'Processing...',
          });

          if (tData.status === 'completed') {
            clearInterval(pollInterval);
            setIsGenerating(false);

            // Fetch loaded project
            const pRes = await fetch(`/api/projects/${slug}`);
            const fullProj = await pRes.json();
            setCurrentProject(fullProj);
            fetchProjects();

            if (tData.master_url) {
              setAudioUrl(tData.master_url);
              setAudioTitle(`${projectName} (Master Audio)`);
            }
          } else if (tData.status === 'failed') {
            clearInterval(pollInterval);
            setIsGenerating(false);
            alert(`Synthesis failed: ${tData.error}`);
          }
        } catch (err) {
          clearInterval(pollInterval);
          setIsGenerating(false);
        }
      }, 750);
    } catch (e) {
      setIsGenerating(false);
      alert(`Error: ${e.message}`);
    }
  };

  const handleUpdateBlock = async (blockId, updatePayload) => {
    if (!currentProject) return;
    try {
      const res = await fetch(`/api/projects/${currentProject.slug}/block/${blockId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updatePayload),
      });
      const data = await res.json();

      // Update state
      setCurrentProject((prev) => ({
        ...prev,
        blocks: prev.blocks.map((b) => (b.id === blockId ? data.block : b)),
      }));

      if (data.audio_url) {
        setAudioUrl(data.audio_url);
        setAudioTitle(`Block #${blockId} (Updated)`);
      }
    } catch (e) {
      alert(`Failed to update block: ${e.message}`);
    }
  };

  const handleFastRepack = async () => {
    if (!currentProject) return;
    setIsRepacking(true);
    try {
      const res = await fetch(`/api/projects/${currentProject.slug}/repack`, { method: 'POST' });
      const data = await res.json();
      if (data.master_url) {
        setAudioUrl(data.master_url);
        setAudioTitle(`${currentProject.name} (Re-packed Master)`);
      }
    } catch (e) {
      alert(`Repack error: ${e.message}`);
    } finally {
      setIsRepacking(false);
    }
  };

  const handleProduceMaster = async (payload) => {
    if (!currentProject) return;
    setIsProducing(true);
    try {
      const res = await fetch(`/api/projects/${currentProject.slug}/produce_master`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.file_url) {
        setAudioUrl(data.file_url);
        setAudioTitle(data.filename);
      }
    } catch (e) {
      alert(`Mastering failed: ${e.message}`);
    } finally {
      setIsProducing(false);
    }
  };

  const handleDownloadVoice = async (voiceKey) => {
    setDownloadingVoiceKey(voiceKey);
    try {
      const res = await fetch('/api/voices/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ voice_key: voiceKey }),
      });
      const data = await res.json();
      const taskId = data.task_id;

      const poll = setInterval(async () => {
        const tRes = await fetch(`/api/tasks/${taskId}`);
        const tData = await tRes.json();
        if (tData.status === 'completed') {
          clearInterval(poll);
          setDownloadingVoiceKey(null);
          fetchVoices();
          alert(`Voice ${voiceKey} installed successfully!`);
        } else if (tData.status === 'failed') {
          clearInterval(poll);
          setDownloadingVoiceKey(null);
          alert(`Download failed: ${tData.error}`);
        }
      }, 1000);
    } catch (e) {
      setDownloadingVoiceKey(null);
      alert(`Error starting download: ${e.message}`);
    }
  };

  const handleLoadProject = async (slug, targetTab = 'blocks') => {
    try {
      const res = await fetch(`/api/projects/${slug}`);
      const data = await res.json();
      setCurrentProject(data);
      setProjectName(data.name);
      setText(data.blocks?.map((b) => b.text).join('\n\n') || '');
      setActiveTab(targetTab);
    } catch (e) {
      alert(`Could not load project: ${e.message}`);
    }
  };

  return (
    <div className="h-screen w-screen flex flex-col bg-dark-950 overflow-hidden font-sans">
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} currentProject={currentProject} />

        {/* Main Content Area */}
        <main className="flex-1 flex flex-col overflow-hidden bg-dark-950">
          {activeTab === 'studio' && (
            <StudioView
              text={text}
              setText={setText}
              projectName={projectName}
              setProjectName={setProjectName}
              voices={voices}
              selectedVoice={selectedVoice}
              setSelectedVoice={setSelectedVoice}
              speed={speed}
              setSpeed={setSpeed}
              pauseMs={pauseMs}
              setPauseMs={setPauseMs}
              onGenerate={handleGenerate}
              isGenerating={isGenerating}
              generationProgress={generationProgress}
              onTestVoice={handleTestVoice}
            />
          )}

          {activeTab === 'blocks' && (
            <BlockReviewView
              project={currentProject}
              voices={voices}
              onPlayAudio={(url, ttl) => {
                setAudioUrl(url);
                setAudioTitle(ttl);
              }}
              onUpdateBlock={handleUpdateBlock}
              onFastRepack={handleFastRepack}
              isRepacking={isRepacking}
            />
          )}

          {activeTab === 'mixer' && (
            <MixerView
              project={currentProject}
              onProduceMaster={handleProduceMaster}
              isProducing={isProducing}
            />
          )}

          {activeTab === 'gallery' && (
            <VoiceGalleryView
              installedVoices={voices}
              remoteCatalog={remoteCatalog}
              onDownloadVoice={handleDownloadVoice}
              downloadingVoiceKey={downloadingVoiceKey}
            />
          )}

          {activeTab === 'projects' && (
            <ProjectsView
              projects={projectsList}
              onLoadProject={handleLoadProject}
              onPlayAudio={(url, ttl) => {
                setAudioUrl(url);
                setAudioTitle(ttl);
              }}
            />
          )}
        </main>
      </div>

      {/* Floating Bottom Audio Player */}
      <AudioPlayerBar audioUrl={audioUrl} title={audioTitle} />
    </div>
  );
}
