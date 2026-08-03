import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import WaveSurfer from 'wavesurfer.js';
import api from '../utils/api';
import { exportActionItemsCSV, exportActionItemsXLSX, exportTranscriptMarkdown } from '../utils/export';
import {
  FileText,
  Sparkles,
  ListTodo,
  Gavel,
  MessageSquare,
  Download,
  Copy,
  Save,
  Edit,
  Check,
  Trash2,
  Loader2,
  Send,
  PieChart as PieIcon,
  HelpCircle,
  FileCheck,
  AlertTriangle,
  RotateCw,
  Play,
  Pause,
  FileSpreadsheet,
  Sheet
} from 'lucide-react';
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend
} from 'recharts';

const GREETING = { role: 'assistant', text: 'Hi! Ask me anything about this meeting\'s contents, discussions, decisions, or deadlines.' };

const MeetingDetails = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [meeting, setMeeting] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('summary');
  
  // Transcript edit state
  const [isEditingTranscript, setIsEditingTranscript] = useState(false);
  const [editedTranscript, setEditedTranscript] = useState('');
  const [savingTranscript, setSavingTranscript] = useState(false);
  const [copiedTranscript, setCopiedTranscript] = useState(false);

  // Chat state
  const [chatInput, setChatInput] = useState('');
  const [chatHistory, setChatHistory] = useState([GREETING]);
  const [chatLoading, setChatLoading] = useState(false);
  const [clearingChat, setClearingChat] = useState(false);
  const chatEndRef = useRef(null);

  // Action Items editing state
  const [editingActionId, setEditingActionId] = useState(null);
  const [actionEdits, setActionEdits] = useState({});
  const [savingActionId, setSavingActionId] = useState(null);

  // PDF Download state
  const [downloadingPDF, setDownloadingPDF] = useState(false);

  // Audio waveform player state
  const waveformRef = useRef(null);
  const wavesurferRef = useRef(null);
  const audioUrlRef = useRef(null);
  const [audioAvailable, setAudioAvailable] = useState(false);
  const [waveReady, setWaveReady] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  // Fetch the audio (auth'd, as a blob so the JWT header applies) and render a
  // WaveSurfer waveform. Waits until the meeting has loaded so the waveform
  // container is mounted. Cleaned up on unmount / id change.
  useEffect(() => {
    if (loading || !waveformRef.current) return;
    let cancelled = false;

    const setup = async () => {
      try {
        const res = await api.get(`/meeting/${id}/audio`, { responseType: 'blob' });
        if (cancelled) return;
        const url = URL.createObjectURL(res.data);
        audioUrlRef.current = url;
        setAudioAvailable(true);

        const ws = WaveSurfer.create({
          container: waveformRef.current,
          height: 60,
          waveColor: '#64748b',
          progressColor: '#3b82f6',
          cursorColor: '#6366f1',
          barWidth: 2,
          barGap: 1,
          barRadius: 2,
          url,
        });
        wavesurferRef.current = ws;
        ws.on('ready', () => { if (!cancelled) { setDuration(ws.getDuration()); setWaveReady(true); } });
        ws.on('timeupdate', (t) => { if (!cancelled) setCurrentTime(t); });
        ws.on('play', () => { if (!cancelled) setIsPlaying(true); });
        ws.on('pause', () => { if (!cancelled) setIsPlaying(false); });
        ws.on('finish', () => { if (!cancelled) setIsPlaying(false); });
      } catch {
        // 404 (file removed / mock) or network error — hide the player gracefully.
        if (!cancelled) setAudioAvailable(false);
      }
    };
    setup();

    return () => {
      cancelled = true;
      if (wavesurferRef.current) {
        try { wavesurferRef.current.destroy(); } catch { /* already gone */ }
        wavesurferRef.current = null;
      }
      if (audioUrlRef.current) {
        URL.revokeObjectURL(audioUrlRef.current);
        audioUrlRef.current = null;
      }
      setWaveReady(false);
      setIsPlaying(false);
      setCurrentTime(0);
      setDuration(0);
    };
  }, [id, loading]);

  const formatTime = (secs) => {
    if (!secs || !isFinite(secs)) return '0:00';
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m}:${String(s).padStart(2, '0')}`;
  };

  const togglePlay = () => wavesurferRef.current?.playPause();

  // Approximate seek: map a transcript line to a point in the audio by its
  // character offset (the stored transcript has no per-line timestamps, so this
  // is proportional rather than exact).
  const transcriptLines = meeting?.transcript ? meeting.transcript.split('\n') : [];
  const lineFraction = (index) => {
    const total = transcriptLines.reduce((n, l) => n + l.length + 1, 0) || 1;
    let before = 0;
    for (let i = 0; i < index; i++) before += transcriptLines[i].length + 1;
    return Math.min(0.999, before / total);
  };
  const seekToLine = (index) => {
    const ws = wavesurferRef.current;
    if (!ws || !waveReady) return;
    ws.seekTo(lineFraction(index));
    ws.play();
  };

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory]);

  const fetchMeetingDetails = useCallback(async () => {
    try {
      const res = await api.get(`/meeting/${id}`);
      setMeeting(res.data);
      setEditedTranscript(res.data.transcript || '');
    } catch (err) {
      console.error("Error fetching meeting:", err);
      alert("Failed to load meeting details.");
      navigate('/');
    } finally {
      setLoading(false);
    }
  }, [id, navigate]);

  const fetchChatHistory = useCallback(async () => {
    try {
      const res = await api.get(`/meeting/${id}/chat-history`);
      if (Array.isArray(res.data) && res.data.length > 0) {
        setChatHistory([
          GREETING,
          ...res.data.map((m) => ({ role: m.role, text: m.content })),
        ]);
      }
    } catch (err) {
      console.error('Failed to load chat history:', err);
    }
  }, [id]);

  const handleClearChat = async () => {
    setClearingChat(true);
    try {
      await api.delete(`/meeting/${id}/chat-history`);
      setChatHistory([GREETING]);
    } catch (err) {
      console.error('Failed to clear chat history:', err);
      alert('Failed to clear chat history.');
    } finally {
      setClearingChat(false);
    }
  };

  useEffect(() => {
    fetchMeetingDetails();
    fetchChatHistory();
  }, [fetchMeetingDetails, fetchChatHistory]);

  const handleDownloadPDF = async () => {
    setDownloadingPDF(true);
    try {
      const response = await api.post('/generate-report', { meeting_id: parseInt(id) }, {
        responseType: 'blob'
      });
      const blob = new Blob([response.data], { type: 'application/pdf' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `${meeting.title.replace(/\s+/g, '_')}_Report.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      console.error("PDF download failed:", err);
      alert("Failed to download PDF report.");
    } finally {
      setDownloadingPDF(false);
    }
  };

  const handleCopyTranscript = () => {
    navigator.clipboard.writeText(meeting.transcript);
    setCopiedTranscript(true);
    setTimeout(() => setCopiedTranscript(false), 2000);
  };

  const handleDownloadTxt = () => {
    const element = document.createElement("a");
    const file = new Blob([meeting.transcript], {type: 'text/plain'});
    element.href = URL.createObjectURL(file);
    element.download = `${meeting.title.replace(/\s+/g, '_')}_transcript.txt`;
    document.body.appendChild(element);
    element.click();
    element.remove();
  };

  const handleSaveTranscript = async () => {
    setSavingTranscript(true);
    try {
      const res = await api.put(`/meeting/${id}/transcript`, { transcript: editedTranscript });
      setMeeting(res.data);
      setIsEditingTranscript(false);
    } catch {
      alert("Failed to save transcript.");
    } finally {
      setSavingTranscript(false);
    }
  };

  const handleSendMessage = async (e) => {
    if (e) e.preventDefault();
    if (!chatInput.trim() || chatLoading) return;

    const userMessage = chatInput;
    setChatHistory(prev => [...prev, { role: 'user', text: userMessage }]);
    setChatInput('');
    setChatLoading(true);

    try {
      const res = await api.post('/chat', {
        meeting_id: parseInt(id),
        message: userMessage
      });
      setChatHistory(prev => [...prev, { role: 'assistant', text: res.data.response }]);
    } catch {
      setChatHistory(prev => [...prev, { role: 'assistant', text: 'Sorry, I encountered an error searching the transcript.' }]);
    } finally {
      setChatLoading(false);
    }
  };

  const handleStartEditAction = (action) => {
    setEditingActionId(action.id);
    setActionEdits({ ...action });
  };

  const handleActionEditChange = (field, val) => {
    setActionEdits(prev => ({ ...prev, [field]: val }));
  };

  const handleSaveActionItem = async (actionId) => {
    setSavingActionId(actionId);
    try {
      const res = await api.put(`/action-item/${actionId}`, actionEdits);
      setMeeting(prev => ({
        ...prev,
        action_items: prev.action_items.map(item => item.id === actionId ? res.data : item)
      }));
      setEditingActionId(null);
    } catch {
      alert("Failed to save action item.");
    } finally {
      setSavingActionId(null);
    }
  };

  const handleToggleActionStatus = async (action) => {
    const newStatus = action.status === 'Completed' ? 'Pending' : 'Completed';
    try {
      const res = await api.put(`/action-item/${action.id}`, { status: newStatus });
      setMeeting(prev => ({
        ...prev,
        action_items: prev.action_items.map(item => item.id === action.id ? res.data : item)
      }));
    } catch {
      alert("Failed to update status.");
    }
  };

  if (loading) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center gap-4">
        <Loader2 className="w-10 h-10 text-primary-500 animate-spin" />
        <p className="text-slate-400 font-semibold">Loading meeting details...</p>
      </div>
    );
  }

  const sentimentData = [
    { name: 'Positive', value: Math.round(meeting.sentiment_positive * 100) },
    { name: 'Neutral', value: Math.round(meeting.sentiment_neutral * 100) },
    { name: 'Negative', value: Math.round(meeting.sentiment_negative * 100) }
  ].filter(s => s.value > 0);

  const sentimentColors = {
    'Positive': '#10B981',
    'Neutral': '#64748B',
    'Negative': '#EF4444'
  };

  const quickQuestions = [
    "Summarize this meeting",
    "What tasks were assigned?",
    "What deadlines were discussed?",
    "What decisions were made?"
  ];

  return (
    <div className="space-y-8 animate-fade-in max-w-6xl mx-auto relative">
      <div className="glow-spot-blue -top-20 -left-20"></div>
      <div className="glow-spot-purple -bottom-20 -right-20"></div>

      {/* Exporter & Navigation toolbar */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-slate-900 pb-6">
        <div>
          <button 
            onClick={() => navigate('/')} 
            className="text-xs text-slate-500 hover:text-slate-350 transition-colors flex items-center gap-1 font-bold"
          >
            ← Back to Dashboard
          </button>
          <h1 className="text-2xl md:text-3xl font-extrabold text-white mt-2 max-w-xl truncate bg-gradient-to-r from-white to-slate-300 bg-clip-text text-transparent">
            {meeting.title}
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Date Uploaded: {new Date(meeting.created_at).toLocaleString()} | File: {meeting.filename}
          </p>
        </div>

        <button
          onClick={handleDownloadPDF}
          disabled={downloadingPDF}
          className="flex items-center gap-2 bg-gradient-to-r from-primary-600 to-indigo-600 hover:from-primary-500 hover:to-indigo-500 disabled:from-slate-800 disabled:to-slate-850 disabled:text-slate-650 text-on-accent px-5 py-3 rounded-2xl font-bold text-sm transition-all shadow-lg glow-primary focus:outline-none"
        >
          {downloadingPDF ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Generating PDF Report...</span>
            </>
          ) : (
            <>
              <Download className="w-4 h-4" />
              <span>Export PDF Report</span>
            </>
          )}
        </button>
      </div>

      {/* Main Grid: Details Tab Workspaces vs. AI Chat Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Left Side: Workspaces tabs */}
        <div className="lg:col-span-2 space-y-6">

          {/* Audio waveform player (container stays mounted; card hides until ready) */}
          <div className={`glass-panel p-4 rounded-3xl border border-slate-800 shadow-2xl ${audioAvailable ? '' : 'hidden'}`}>
            <div className="flex items-center gap-4">
              <button
                onClick={togglePlay}
                disabled={!waveReady}
                title={isPlaying ? 'Pause' : 'Play'}
                className="shrink-0 w-11 h-11 rounded-full bg-primary-600 hover:bg-primary-500 disabled:bg-slate-800 text-on-accent flex items-center justify-center transition-colors shadow-lg glow-primary"
              >
                {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5 ml-0.5" />}
              </button>
              <div ref={waveformRef} className="flex-1 min-w-0" />
              <span className="shrink-0 text-xs text-slate-400 font-mono tabular-nums whitespace-nowrap">
                {formatTime(currentTime)} / {formatTime(duration)}
              </span>
            </div>
            <p className="text-[10px] text-slate-500 mt-2 flex items-center gap-1">
              <FileText className="w-3 h-3" />
              Click any line in the Transcript tab to jump to that point (approximate).
            </p>
          </div>

          {/* Tab buttons */}
          <div className="flex gap-2 overflow-x-auto pb-1 border-b border-slate-900 scrollbar-none">
            {[
              { id: 'summary', label: 'AI Summary', icon: Sparkles },
              { id: 'transcript', label: 'Transcript', icon: FileText },
              { id: 'actions', label: 'Action Items', icon: ListTodo },
              { id: 'decisions', label: 'Decisions', icon: Gavel },
              { id: 'sentiment', label: 'Sentiment', icon: PieIcon }
            ].map(tab => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 px-4 py-3 text-sm font-bold transition-all border-b-2 outline-none whitespace-nowrap ${
                    activeTab === tab.id
                      ? 'tab-active'
                      : 'border-transparent text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>

          {/* Details Card Panel */}
          <div className="glass-panel p-6 md:p-8 rounded-3xl border border-slate-800 shadow-2xl min-h-[460px]">
            
            {/* AI Summary Tab */}
            {activeTab === 'summary' && (
              <div className="space-y-6 animate-fade-in">
                <div>
                  <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-3">Executive Summary</h3>
                  <p className="text-slate-100 leading-relaxed bg-slate-900/40 p-5 rounded-2xl border border-slate-850 text-sm">
                    {meeting.summary_executive || "AI summary processing..."}
                  </p>
                </div>
                <div>
                  <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-3">Detailed Discussion</h3>
                  <p className="text-slate-300 leading-relaxed text-sm">
                    {meeting.summary_detailed || "Detailed summary not computed yet."}
                  </p>
                </div>
                {meeting.summary_highlights && (
                  <div>
                    <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-3">Meeting Highlights</h3>
                    <div className="space-y-2.5 text-sm text-slate-350 bg-slate-950/20 p-5 rounded-2xl border border-slate-850">
                      {meeting.summary_highlights.split('\n').map((line, idx) => (
                        <p key={idx} className="leading-relaxed">{line}</p>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Transcript Tab (Editable) */}
            {activeTab === 'transcript' && (
              <div className="space-y-4 animate-fade-in">
                <div className="flex justify-between items-center bg-slate-900/40 px-4 py-3 rounded-2xl border border-slate-850 text-xs">
                  <span className="text-slate-400 font-semibold">Speech-to-text transcript</span>
                  <div className="flex items-center gap-2">
                    <button 
                      onClick={handleCopyTranscript}
                      className="p-2 rounded-lg bg-slate-950 text-slate-400 hover:text-white border border-slate-800 hover:bg-slate-900 transition-colors"
                      title="Copy to Clipboard"
                    >
                      {copiedTranscript ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
                    </button>
                    <button
                      onClick={handleDownloadTxt}
                      className="p-2 rounded-lg bg-slate-950 text-slate-400 hover:text-white border border-slate-800 hover:bg-slate-900 transition-colors"
                      title="Download Text File (.txt)"
                    >
                      <Download className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => exportTranscriptMarkdown(meeting)}
                      className="flex items-center gap-1.5 px-2.5 py-2 rounded-lg bg-slate-950 text-slate-400 hover:text-white border border-slate-800 hover:bg-slate-900 transition-colors text-[10px] font-bold"
                      title="Download as Markdown (.md)"
                    >
                      <FileText className="w-3.5 h-3.5" />
                      MD
                    </button>
                    <button 
                      onClick={() => setIsEditingTranscript(!isEditingTranscript)}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold border border-slate-800 ${
                        isEditingTranscript 
                          ? 'bg-amber-600 text-on-accent border-transparent'
                          : 'bg-slate-950 text-slate-300 hover:text-white hover:bg-slate-900'
                      } transition-colors`}
                    >
                      <Edit className="w-3.5 h-3.5" />
                      <span>{isEditingTranscript ? 'Cancel' : 'Edit'}</span>
                    </button>
                  </div>
                </div>

                {isEditingTranscript ? (
                  <div className="space-y-3">
                    <textarea
                      value={editedTranscript}
                      onChange={(e) => setEditedTranscript(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-850 rounded-2xl p-4 h-80 text-sm text-slate-100 outline-none focus:border-primary-500 font-mono leading-relaxed"
                    />
                    <div className="flex justify-end">
                      <button
                        onClick={handleSaveTranscript}
                        disabled={savingTranscript}
                        className="flex items-center gap-2 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-on-accent font-bold text-xs px-5 py-2.5 rounded-xl transition-colors shadow-lg glow-emerald focus:outline-none"
                      >
                        {savingTranscript ? (
                          <>
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            <span>Saving Changes...</span>
                          </>
                        ) : (
                          <>
                            <Save className="w-3.5 h-3.5" />
                            <span>Save Transcript</span>
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="bg-slate-950/25 border border-slate-850 p-6 rounded-2xl max-h-80 overflow-y-auto text-sm text-slate-300 space-y-4 leading-relaxed font-sans">
                    {meeting.transcript ? (
                      transcriptLines.map((line, idx) => {
                        const clickable = waveReady && !!line.trim();
                        return (
                          <p
                            key={idx}
                            onClick={clickable ? () => seekToLine(idx) : undefined}
                            title={clickable ? `Jump to ~${formatTime(lineFraction(idx) * duration)}` : undefined}
                            className={clickable ? 'cursor-pointer rounded-lg -mx-2 px-2 py-1 hover:bg-primary-500/10 hover:text-white transition-colors' : ''}
                          >
                            {line}
                          </p>
                        );
                      })
                    ) : (
                      <p className="text-slate-500 italic text-center py-12">No transcript generated.</p>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Action Items Tab */}
            {activeTab === 'actions' && (
              <div className="space-y-6 animate-fade-in">
                <div className="flex justify-between items-center gap-3 pb-2 border-b border-slate-900">
                  <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest">Action Assignments</h3>
                  <div className="flex items-center gap-2">
                    <span className="hidden sm:inline text-[10px] text-slate-500 bg-slate-950 px-2 py-1 rounded border border-slate-850">
                      Auto-saves
                    </span>
                    <button
                      onClick={() => exportActionItemsCSV(meeting)}
                      disabled={!meeting.action_items?.length}
                      title="Export action items as CSV"
                      className="flex items-center gap-1.5 text-[11px] font-bold px-2.5 py-1.5 rounded-lg bg-slate-950 border border-slate-850 text-slate-300 hover:text-white hover:border-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                      <Sheet className="w-3.5 h-3.5" />
                      CSV
                    </button>
                    <button
                      onClick={() => exportActionItemsXLSX(meeting).catch(() => alert('Failed to export Excel file.'))}
                      disabled={!meeting.action_items?.length}
                      title="Export action items as Excel (.xlsx)"
                      className="flex items-center gap-1.5 text-[11px] font-bold px-2.5 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                      <FileSpreadsheet className="w-3.5 h-3.5" />
                      Excel
                    </button>
                  </div>
                </div>

                {meeting.action_items?.length === 0 ? (
                  <div className="text-center py-16 text-slate-500 border border-dashed border-slate-850 rounded-2xl">
                    No action items extracted for this meeting.
                  </div>
                ) : (
                  <div className="overflow-x-auto border border-slate-850 rounded-2xl bg-slate-950/20">
                    <table className="w-full text-left border-collapse text-xs md:text-sm">
                      <thead>
                        <tr className="bg-slate-900/50 border-b border-slate-800 text-slate-400 text-[10px] font-bold uppercase tracking-wider">
                          <th className="py-3 px-4 w-10 text-center">Done</th>
                          <th className="py-3 px-4">Task</th>
                          <th className="py-3 px-4 w-32">Assignee</th>
                          <th className="py-3 px-4 w-28">Deadline</th>
                          <th className="py-3 px-4 w-24">Priority</th>
                          <th className="py-3 px-4 w-16 text-center">Edit</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-850 text-slate-200">
                        {meeting.action_items.map((act) => {
                          const isEditing = editingActionId === act.id;
                          
                          let priorityColor = "text-slate-400 bg-slate-500/10 border-slate-500/20";
                          if (act.priority === 'High') priorityColor = "text-red-400 bg-red-500/10 border-red-500/20";
                          if (act.priority === 'Medium') priorityColor = "text-amber-400 bg-amber-500/10 border-amber-500/20";
                          if (act.priority === 'Low') priorityColor = "text-blue-400 bg-blue-500/10 border-blue-500/20";

                          return (
                            <tr key={act.id} className="hover:bg-slate-900/10 transition-colors">
                              <td className="py-3 px-4 text-center">
                                <input
                                  type="checkbox"
                                  checked={act.status === 'Completed'}
                                  onChange={() => handleToggleActionStatus(act)}
                                  className="w-4 h-4 rounded border-slate-800 text-primary-500 focus:ring-primary-500/30 bg-slate-950 cursor-pointer transition-all"
                                />
                              </td>
                              
                              <td className="py-3 px-4 font-medium">
                                {isEditing ? (
                                  <input
                                    type="text"
                                    value={actionEdits.task || ''}
                                    onChange={(e) => handleActionEditChange('task', e.target.value)}
                                    className="bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 w-full text-white text-xs premium-input"
                                  />
                                ) : (
                                  <span className={act.status === 'Completed' ? 'line-through text-slate-500' : ''}>
                                    {act.task}
                                  </span>
                                )}
                              </td>

                              <td className="py-3 px-4">
                                {isEditing ? (
                                  <input
                                    type="text"
                                    value={actionEdits.owner || ''}
                                    onChange={(e) => handleActionEditChange('owner', e.target.value)}
                                    className="bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 w-full text-white text-xs premium-input"
                                  />
                                ) : (
                                  <span className="font-semibold text-slate-350">{act.owner}</span>
                                )}
                              </td>

                              <td className="py-3 px-4 text-slate-400 text-xs">
                                {isEditing ? (
                                  <input
                                    type="text"
                                    value={actionEdits.deadline || ''}
                                    onChange={(e) => handleActionEditChange('deadline', e.target.value)}
                                    className="bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 w-full text-white text-xs premium-input"
                                  />
                                ) : (
                                  act.deadline || 'N/A'
                                )}
                              </td>

                              <td className="py-3 px-4">
                                {isEditing ? (
                                  <select
                                    value={actionEdits.priority || 'Medium'}
                                    onChange={(e) => handleActionEditChange('priority', e.target.value)}
                                    className="bg-slate-950 border border-slate-800 rounded px-1 py-1.5 text-white text-xs w-full premium-input"
                                  >
                                    <option value="High">High</option>
                                    <option value="Medium">Medium</option>
                                    <option value="Low">Low</option>
                                  </select>
                                ) : (
                                  <span className={`px-2 py-0.5 rounded border text-[10px] font-bold tracking-wide ${priorityColor}`}>
                                    {act.priority}
                                  </span>
                                )}
                              </td>

                              <td className="py-3 px-4 text-center">
                                {isEditing ? (
                                  <button
                                    onClick={() => handleSaveActionItem(act.id)}
                                    disabled={savingActionId === act.id}
                                    className="p-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-on-accent transition-colors"
                                  >
                                    {savingActionId === act.id ? (
                                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                    ) : (
                                      <Check className="w-3.5 h-3.5" />
                                    )}
                                  </button>
                                ) : (
                                  <button
                                    onClick={() => handleStartEditAction(act)}
                                    className="p-1.5 rounded hover:bg-slate-900 text-slate-500 hover:text-white transition-colors"
                                  >
                                    <Edit className="w-3.5 h-3.5" />
                                  </button>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* Decisions & Risks Tab */}
            {activeTab === 'decisions' && (
              <div className="space-y-6 animate-fade-in">
                <div>
                  <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-3 flex items-center gap-2">
                    <FileCheck className="w-4 h-4 text-emerald-400" />
                    Decisions Taken
                  </h3>
                  {meeting.decisions?.length === 0 ? (
                    <p className="text-sm text-slate-500 italic">No key decisions extracted.</p>
                  ) : (
                    <ul className="space-y-3">
                      {meeting.decisions?.map((dec) => (
                        <li 
                          key={dec.id} 
                          className="bg-emerald-500/5 border border-emerald-500/10 p-4 rounded-2xl text-slate-200 text-sm leading-relaxed"
                        >
                          {dec.decision_text}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-4 border-t border-slate-900">
                  <div>
                    <h4 className="text-xs font-bold text-red-400 uppercase tracking-widest mb-2.5 flex items-center gap-1.5">
                      <AlertTriangle className="w-3.5 h-3.5" />
                      Identified Risks
                    </h4>
                    <div className="bg-slate-950/25 border border-slate-850 p-4 rounded-2xl text-slate-350 text-xs min-h-24 leading-relaxed">
                      {meeting.risks ? (
                        <ul className="list-disc pl-4 space-y-1.5">
                          {meeting.risks.split('\n').filter(Boolean).map((risk, idx) => (
                            <li key={idx}>{risk}</li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-slate-500 italic">No critical risks flagged during discussion.</p>
                      )}
                    </div>
                  </div>

                  <div>
                    <h4 className="text-xs font-bold text-primary-400 uppercase tracking-widest mb-2.5 flex items-center gap-1.5">
                      <RotateCw className="w-3.5 h-3.5" />
                      Actionable Follow-Ups
                    </h4>
                    <div className="bg-slate-950/25 border border-slate-850 p-4 rounded-2xl text-slate-350 text-xs min-h-24 leading-relaxed">
                      {meeting.follow_ups ? (
                        <ul className="list-disc pl-4 space-y-1.5">
                          {meeting.follow_ups.split('\n').filter(Boolean).map((item, idx) => (
                            <li key={idx}>{item}</li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-slate-500 italic">No follow-ups extracted for this meeting.</p>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Sentiment Tab */}
            {activeTab === 'sentiment' && (
              <div className="space-y-6 animate-fade-in flex flex-col md:flex-row items-center justify-around py-6">
                <div className="h-64 w-full md:w-1/2">
                  {sentimentData.length === 0 ? (
                    <div className="flex items-center justify-center h-full text-slate-500 text-sm">
                      Sentiment calculations are pending.
                    </div>
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={sentimentData}
                          cx="50%"
                          cy="50%"
                          innerRadius={55}
                          outerRadius={75}
                          paddingAngle={4}
                          dataKey="value"
                        >
                          {sentimentData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={sentimentColors[entry.name]} />
                          ))}
                        </Pie>
                        <Tooltip 
                          contentStyle={{ backgroundColor: '#090d16', border: '1px solid #1e293b', borderRadius: 12 }}
                          itemStyle={{ color: '#fff' }}
                        />
                        <Legend iconSize={8} formatter={(val) => <span className="text-xs text-slate-400 font-bold">{val}</span>} />
                      </PieChart>
                    </ResponsiveContainer>
                  )}
                </div>

                <div className="md:w-1/2 space-y-4 max-w-sm">
                  <h4 className="text-sm font-bold text-white uppercase tracking-wider">Sentiment Audit</h4>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    Visual distribution of dialogue sentiment. High positive indicators reflect task alignment and optimistic workflow progress. High negative signals highlight technical risks, blocking issues, or scheduling friction.
                  </p>
                  <div className="grid grid-cols-3 gap-3">
                    <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-2xl text-center">
                      <p className="text-[10px] font-bold text-slate-500 uppercase">Positive</p>
                      <p className="text-lg font-black text-emerald-400 mt-1">{Math.round(meeting.sentiment_positive * 100)}%</p>
                    </div>
                    <div className="p-3 bg-slate-550/10 border border-slate-500/20 rounded-2xl text-center">
                      <p className="text-[10px] font-bold text-slate-500 uppercase">Neutral</p>
                      <p className="text-lg font-black text-slate-300 mt-1">{Math.round(meeting.sentiment_neutral * 100)}%</p>
                    </div>
                    <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-2xl text-center">
                      <p className="text-[10px] font-bold text-slate-500 uppercase">Negative</p>
                      <p className="text-lg font-black text-red-400 mt-1">{Math.round(meeting.sentiment_negative * 100)}%</p>
                    </div>
                  </div>
                </div>
              </div>
            )}

          </div>
        </div>

        {/* Right Column: AI RAG Chatbot */}
        <div className="space-y-6">
          <div className="glass-panel rounded-3xl border border-slate-800 flex flex-col h-[530px] overflow-hidden shadow-2xl">
            
            {/* Chatbot Header */}
            <div className="p-4 border-b border-slate-900 bg-gradient-to-r from-slate-900/60 to-slate-950/60 flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-primary-600/10 text-primary-400 border border-primary-500/20 flex items-center justify-center">
                <MessageSquare className="w-5 h-5" />
              </div>
              <div className="flex-1">
                <h3 className="font-bold text-sm text-white">MeetingMind Agent</h3>
                <p className="text-[10px] text-slate-500 font-semibold">Semantic Context Search active</p>
              </div>
              {chatHistory.length > 1 && (
                <button
                  onClick={handleClearChat}
                  disabled={clearingChat}
                  title="Clear conversation history"
                  className="p-2 rounded-lg text-slate-500 hover:text-red-400 hover:bg-slate-900 disabled:opacity-50 transition-all"
                >
                  {clearingChat
                    ? <Loader2 className="w-4 h-4 animate-spin" />
                    : <Trash2 className="w-4 h-4" />}
                </button>
              )}
            </div>

            {/* Chat Messages */}
            <div className="flex-1 p-4 overflow-y-auto space-y-4 text-xs">
              {chatHistory.map((msg, idx) => (
                <div 
                  key={idx} 
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div className={`p-3.5 rounded-2xl max-w-[85%] leading-relaxed shadow-md ${
                    msg.role === 'user'
                      ? 'bg-gradient-to-tr from-primary-600 to-indigo-650 text-on-accent rounded-tr-none'
                      : 'bg-slate-900 text-slate-200 border border-slate-850 rounded-tl-none'
                  }`}>
                    {msg.text.split('\n').map((para, i) => (
                      <p key={i} className={i > 0 ? 'mt-1.5' : ''}>{para}</p>
                    ))}
                  </div>
                </div>
              ))}
              {chatLoading && (
                <div className="flex justify-start">
                  <div className="bg-slate-900 border border-slate-850 p-3 rounded-2xl rounded-tl-none flex items-center gap-2 text-slate-400">
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-primary-500" />
                    <span>Searching database...</span>
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            {/* Quick Suggestions */}
            {chatHistory.length <= 1 && (
              <div className="px-4 py-3 border-t border-slate-850 bg-slate-950/20 space-y-2">
                <p className="text-[9px] font-bold text-slate-500 uppercase tracking-widest flex items-center gap-1">
                  <HelpCircle className="w-3 h-3 text-slate-500" />
                  Suggested Prompts
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {quickQuestions.map((q) => (
                    <button
                      key={q}
                      onClick={() => {
                        setChatInput(q);
                      }}
                      className="text-[10px] bg-slate-950 border border-slate-850 text-slate-400 hover:text-white hover:border-slate-700 px-2.5 py-1 rounded-xl transition-all"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Message Input Form */}
            <form 
              onSubmit={handleSendMessage}
              className="p-3 border-t border-slate-900 bg-slate-900/30 flex gap-2"
            >
              <input
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder="Ask details (e.g. deadlines discussed)..."
                className="flex-1 bg-slate-950 border border-slate-850 rounded-xl px-3.5 py-2.5 text-xs text-white outline-none focus:border-primary-500 transition-all premium-input"
              />
              <button
                type="submit"
                disabled={chatLoading}
                className="p-3 rounded-xl bg-primary-600 hover:bg-primary-500 disabled:bg-slate-800 text-on-accent transition-all shadow-lg glow-primary"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </form>

          </div>
        </div>

      </div>
    </div>
  );
};

export default MeetingDetails;
