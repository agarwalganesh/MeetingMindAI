import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../utils/api';
import { trackJob } from '../utils/jobs';
import { 
  FileAudio, 
  ListTodo, 
  CheckCircle, 
  Clock, 
  Upload, 
  Trash2, 
  ChevronRight, 
  Loader2, 
  AlertCircle,
  TrendingUp,
  Smile,
  Zap,
  Activity,
  Plus
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
  PieChart,
  Pie,
  Legend
} from 'recharts';

const Dashboard = () => {
  const navigate = useNavigate();
  const [meetings, setMeetings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({
    totalMeetings: 0,
    totalActions: 0,
    pendingTasks: 0,
    completedTasks: 0
  });

  // Upload state
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStage, setUploadStage] = useState('');
  const [uploadError, setUploadError] = useState('');
  const [dragActive, setDragActive] = useState(false);

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      const res = await api.get('/meetings');
      const meetingsList = res.data;
      setMeetings(meetingsList);

      let totalActions = 0;
      let pending = 0;
      let completed = 0;
      
      const detailPromises = meetingsList.map(m => api.get(`/meeting/${m.id}`));
      const details = await Promise.all(detailPromises);
      
      details.forEach(resDetail => {
        const m = resDetail.data;
        totalActions += m.action_items.length;
        m.action_items.forEach(act => {
          if (act.status === 'Completed') completed++;
          else pending++;
        });
      });

      setStats({
        totalMeetings: meetingsList.length,
        totalActions,
        pendingTasks: pending,
        completedTasks: completed
      });
    } catch (err) {
      console.error("Error fetching dashboard details:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      await uploadFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = async (e) => {
    if (e.target.files && e.target.files[0]) {
      await uploadFile(e.target.files[0]);
    }
  };

  const uploadFile = async (file) => {
    const fileExt = file.name.split('.').pop().toLowerCase();
    if (!['mp3', 'wav', 'm4a', 'aac', 'ogg'].includes(fileExt)) {
      setUploadError('Unsupported format. Please upload MP3, WAV, M4A, AAC, or OGG.');
      return;
    }

    setUploadError('');
    setUploading(true);
    setUploadProgress(0);
    setUploadStage('Uploading file');

    const formData = new FormData();
    formData.append('file', file);

    try {
      // 1. Upload the raw audio (real byte-level progress, capped at 10%).
      const uploadRes = await api.post('/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          if (e.total) {
            setUploadProgress(Math.min(10, Math.round((e.loaded / e.total) * 10)));
          }
        }
      });

      const { filename, title } = uploadRes.data;
      setUploadProgress(10);
      setUploadStage('Queued for processing');

      // 2. Hand off to the async pipeline — returns immediately with a task_id.
      const procRes = await api.post('/process', { filename, title });
      const taskId = procRes.data.task_id;

      // 3. Track real backend progress via SSE (falls back to polling).
      trackJob(taskId, {
        onUpdate: (data) => {
          if (typeof data.progress === 'number') {
            setUploadProgress(Math.max(10, data.progress));
          }
          if (data.stage) setUploadStage(data.stage);
        },
        onComplete: (data) => {
          setUploadProgress(100);
          setUploadStage('Ready');
          setTimeout(() => {
            setUploading(false);
            setUploadProgress(0);
            setUploadStage('');
            if (data.meeting_id) navigate(`/meeting/${data.meeting_id}`);
            else fetchDashboardData();
          }, 600);
        },
        onError: (err) => {
          console.error('Processing failed:', err);
          setUploadError(err.message || 'An error occurred during processing.');
          setUploading(false);
          setUploadProgress(0);
          setUploadStage('');
        }
      });

    } catch (err) {
      console.error("Upload workflow failed:", err);
      setUploadError(err.response?.data?.detail || 'An error occurred during file processing.');
      setUploading(false);
      setUploadProgress(0);
      setUploadStage('');
    }
  };

  const handleDeleteMeeting = async (id, e) => {
    e.stopPropagation();
    if (window.confirm("Are you sure you want to delete this meeting?")) {
      try {
        await api.delete(`/meeting/${id}`);
        setMeetings(meetings.filter(m => m.id !== id));
        fetchDashboardData();
      } catch (err) {
        alert("Failed to delete meeting.");
      }
    }
  };

  const taskChartData = [
    { name: 'Pending', count: stats.pendingTasks },
    { name: 'Completed', count: stats.completedTasks }
  ];

  const getAverageSentiment = () => {
    if (meetings.length === 0) return [{ name: 'Neutral', value: 1 }];
    let pos = 0, neu = 0, neg = 0;
    meetings.forEach(m => {
      pos += m.sentiment_positive;
      neu += m.sentiment_neutral;
      neg += m.sentiment_negative;
    });
    const total = meetings.length;
    return [
      { name: 'Positive', value: Math.round((pos / total) * 100) },
      { name: 'Neutral', value: Math.round((neu / total) * 100) },
      { name: 'Negative', value: Math.round((neg / total) * 100) }
    ];
  };

  const sentimentColors = ['#10B981', '#64748B', '#EF4444'];

  return (
    <div className="space-y-10 animate-fade-in relative">
      {/* Ambient background glows */}
      <div className="glow-spot-blue -top-40 -left-40"></div>
      <div className="glow-spot-purple -bottom-40 -right-40"></div>

      {/* Header Banner */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-slate-900 pb-6">
        <div>
          <h1 className="text-3xl md:text-4xl font-extrabold text-white tracking-tight bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">
            Dashboard Workspace
          </h1>
          <p className="text-slate-400 mt-1 text-sm md:text-base">Review meeting analytics, speech-to-text transcripts, and actions items</p>
        </div>
        <div className="flex items-center gap-2 bg-slate-900/50 px-4 py-2 rounded-2xl border border-slate-800 backdrop-blur-sm">
          <Activity className="w-4 h-4 text-primary-500 animate-pulse" />
          <span className="text-xs font-semibold text-slate-300">Live Workspace Monitoring</span>
        </div>
      </div>

      {/* Metrics Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="glass-card p-6 rounded-3xl glow-primary flex items-center gap-5">
          <div className="p-4 rounded-2xl bg-primary-500/10 text-primary-400">
            <FileAudio className="w-6 h-6" />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Total Meetings</p>
            <p className="text-3xl font-extrabold text-white mt-1">{stats.totalMeetings}</p>
          </div>
        </div>

        <div className="glass-card p-6 rounded-3xl flex items-center gap-5">
          <div className="p-4 rounded-2xl bg-amber-500/10 text-amber-400">
            <ListTodo className="w-6 h-6" />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Total Actions</p>
            <p className="text-3xl font-extrabold text-white mt-1">{stats.totalActions}</p>
          </div>
        </div>

        <div className="glass-card p-6 rounded-3xl flex items-center gap-5 hover:border-red-500/20">
          <div className="p-4 rounded-2xl bg-red-500/10 text-red-400">
            <Clock className="w-6 h-6" />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Pending Tasks</p>
            <p className="text-3xl font-extrabold text-white mt-1">{stats.pendingTasks}</p>
          </div>
        </div>

        <div className="glass-card p-6 rounded-3xl flex items-center gap-5 hover:border-emerald-500/20">
          <div className="p-4 rounded-2xl bg-emerald-500/10 text-emerald-400">
            <CheckCircle className="w-6 h-6" />
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Completed Tasks</p>
            <p className="text-3xl font-extrabold text-white mt-1">{stats.completedTasks}</p>
          </div>
        </div>
      </div>

      {/* Two Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Left Column (Upload & Recent Meetings) */}
        <div className="lg:col-span-2 space-y-8">
          
          {/* Upload card */}
          <div className="glass-panel p-6 rounded-3xl border border-slate-800 shadow-2xl relative overflow-hidden">
            <div className="absolute top-0 right-0 w-24 h-24 bg-gradient-to-bl from-primary-500/5 to-transparent rounded-bl-full"></div>
            <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
              <Zap className="w-4 h-4 text-primary-400" />
              Upload Audio Recording
            </h2>
            
            {uploadError && (
              <div className="mb-4 p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex gap-2 items-center">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{uploadError}</span>
              </div>
            )}

            <div
              onDragEnter={handleDrag}
              onDragOver={handleDrag}
              onDragLeave={handleDrag}
              onDrop={handleDrop}
              className={`border-2 border-dashed rounded-2xl p-10 text-center transition-all duration-300 relative ${
                dragActive 
                  ? 'border-primary-500 bg-primary-500/5 upload-active' 
                  : 'border-slate-800 hover:border-slate-700 bg-slate-900/15'
              }`}
            >
              {uploading ? (
                <div className="space-y-4 py-6">
                  <Loader2 className="w-12 h-12 text-primary-500 animate-spin mx-auto" />
                  <div>
                    <p className="font-semibold text-white text-lg">{uploadStage || 'Processing Audio File...'}</p>
                    <p className="text-xs text-slate-400 mt-1">Live status streamed from the backend as your recording is processed.</p>
                  </div>
                  <div className="w-full max-w-sm bg-slate-850 rounded-full h-2 mx-auto overflow-hidden">
                    <div
                      className="bg-gradient-to-r from-primary-500 to-indigo-500 h-2 rounded-full transition-all duration-300"
                      style={{ width: `${uploadProgress}%` }}
                    />
                  </div>
                  <p className="text-xs text-primary-400 font-bold">{uploadProgress}% Complete</p>
                </div>
              ) : (
                <div className="space-y-4 py-4">
                  <div className="w-14 h-14 rounded-2xl bg-slate-900/80 flex items-center justify-center mx-auto text-slate-300 border border-slate-800">
                    <Upload className="w-6 h-6 text-primary-400" />
                  </div>
                  <div>
                    <label className="cursor-pointer">
                      <span className="text-primary-400 font-bold hover:text-primary-350 transition-colors hover:underline">Click to upload</span>
                      <span className="text-slate-400"> or drag and drop</span>
                      <input
                        type="file"
                        className="hidden"
                        accept=".mp3,.wav,.m4a,.aac,.ogg"
                        onChange={handleFileChange}
                      />
                    </label>
                    <p className="text-xs text-slate-500 mt-2">Supports MP3, WAV, M4A, AAC, and OGG up to 50MB</p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Recent Meetings Table */}
          <div className="glass-panel p-6 rounded-3xl border border-slate-800 shadow-2xl">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <FileAudio className="w-4 h-4 text-indigo-400" />
                Recent Transcripts
              </h2>
              <span className="text-xs text-slate-500 bg-slate-900/50 px-2.5 py-1 rounded-full border border-slate-850">
                {meetings.length} Total Logs
              </span>
            </div>

            {loading ? (
              <div className="py-16 flex justify-center">
                <Loader2 className="w-10 h-10 text-primary-500 animate-spin" />
              </div>
            ) : meetings.length === 0 ? (
              <div className="text-center py-16 text-slate-500 border border-dashed border-slate-850 rounded-2xl bg-slate-900/5">
                No meetings uploaded yet. Use the upload box above to start!
              </div>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-slate-850">
                <table className="w-full text-left border-collapse text-sm">
                  <thead>
                    <tr className="bg-slate-900/40 border-b border-slate-800 text-slate-400 text-xs font-semibold uppercase">
                      <th className="py-3.5 px-4">Meeting Title</th>
                      <th className="py-3.5 px-4 w-32">Date</th>
                      <th className="py-3.5 px-4 w-28">Sentiment</th>
                      <th className="py-3.5 px-4 w-24 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-850">
                    {meetings.slice(0, 5).map((m) => {
                      const dateStr = new Date(m.created_at).toLocaleDateString('en-US', {
                        month: 'short',
                        day: 'numeric',
                        year: 'numeric'
                      });

                      let sentimentLabel = "Neutral";
                      let sentimentClass = "bg-slate-500/10 text-slate-400 border border-slate-500/20";
                      
                      if (m.sentiment_positive > m.sentiment_neutral && m.sentiment_positive > m.sentiment_negative) {
                        sentimentLabel = "Positive";
                        sentimentClass = "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
                      } else if (m.sentiment_negative > m.sentiment_positive && m.sentiment_negative > m.sentiment_neutral) {
                        sentimentLabel = "Negative";
                        sentimentClass = "bg-red-500/10 text-red-400 border border-red-500/20";
                      }

                      return (
                        <tr
                          key={m.id}
                          onClick={() => navigate(`/meeting/${m.id}`)}
                          className="group hover:bg-slate-900/20 cursor-pointer transition-colors"
                        >
                          <td className="py-4 px-4 font-semibold text-white group-hover:text-primary-400 transition-colors max-w-xs truncate">
                            {m.title}
                          </td>
                          <td className="py-4 px-4 text-xs text-slate-400">
                            {dateStr}
                          </td>
                          <td className="py-4 px-4">
                            <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${sentimentClass}`}>
                              {sentimentLabel}
                            </span>
                          </td>
                          <td className="py-4 px-4 text-right">
                            <div className="flex justify-end gap-2 items-center">
                              <button
                                onClick={(e) => handleDeleteMeeting(m.id, e)}
                                className="p-1.5 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                              >
                                <Trash2 className="w-4 h-4" />
                              </button>
                              <ChevronRight className="w-4 h-4 text-slate-500 group-hover:translate-x-1 transition-transform" />
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Right Column (Analytics & Charts) */}
        <div className="space-y-8">
          
          {/* Action Items Status Chart */}
          <div className="glass-panel p-6 rounded-3xl border border-slate-800 shadow-2xl">
            <h3 className="text-xs font-bold text-white mb-6 uppercase tracking-wider flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-primary-400" />
              Action Items Status
            </h3>
            <div className="h-60">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={taskChartData} margin={{ top: 10, right: 10, left: -25, bottom: 0 }}>
                  <XAxis dataKey="name" stroke="#64748B" fontSize={11} tickLine={false} />
                  <YAxis stroke="#64748B" fontSize={11} tickLine={false} allowDecimals={false} />
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#090d16', border: '1px solid #1e293b', borderRadius: 12 }}
                    labelStyle={{ color: '#fff', fontWeight: 'bold' }}
                    itemStyle={{ color: '#3b82f6' }}
                  />
                  <Bar dataKey="count" fill="#3b82f6" radius={[6, 6, 0, 0]}>
                    <Cell fill="#ef4444" />
                    <Cell fill="#10b981" />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Sentiment Distribution Pie Chart */}
          <div className="glass-panel p-6 rounded-3xl border border-slate-800 shadow-2xl">
            <h3 className="text-xs font-bold text-white mb-6 uppercase tracking-wider flex items-center gap-2">
              <Smile className="w-4 h-4 text-emerald-400" />
              Aggregated Sentiment
            </h3>
            <div className="h-60 relative">
              {meetings.length === 0 ? (
                <div className="absolute inset-0 flex items-center justify-center text-slate-500 text-sm">
                  Upload files to analyze sentiment
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={getAverageSentiment()}
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={80}
                      paddingAngle={5}
                      dataKey="value"
                    >
                      {getAverageSentiment().map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={sentimentColors[index % sentimentColors.length]} />
                      ))}
                    </Pie>
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#090d16', border: '1px solid #1e293b', borderRadius: 12 }}
                      itemStyle={{ color: '#fff' }}
                    />
                    <Legend 
                      verticalAlign="bottom" 
                      height={36} 
                      iconSize={8}
                      formatter={(value) => <span className="text-xs text-slate-400 font-semibold">{value}</span>}
                    />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>
        </div>

      </div>
    </div>
  );
};

export default Dashboard;
