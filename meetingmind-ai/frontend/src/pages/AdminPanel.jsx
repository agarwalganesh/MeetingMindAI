import React, { useState, useEffect } from 'react';
import api from '../utils/api';
import { 
  ShieldAlert, 
  Users as UsersIcon, 
  FileAudio, 
  Trash2, 
  BarChart, 
  Activity, 
  Cpu, 
  Loader2,
  Calendar
} from 'lucide-react';

const AdminPanel = () => {
  const [analytics, setAnalytics] = useState(null);
  const [users, setUsers] = useState([]);
  const [meetings, setMeetings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('users');

  useEffect(() => {
    fetchAdminData();
  }, []);

  const fetchAdminData = async () => {
    setLoading(true);
    try {
      const [analyticsRes, usersRes, meetingsRes] = await Promise.all([
        api.get('/admin/analytics'),
        api.get('/admin/users'),
        api.get('/admin/meetings')
      ]);

      setAnalytics(analyticsRes.data);
      setUsers(usersRes.data);
      setMeetings(meetingsRes.data);
    } catch (err) {
      console.error("Failed to fetch admin dashboard records:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteUser = async (userId) => {
    if (window.confirm("WARNING: Deleting this user will permanently destroy all their meeting files, transcripts, vector indexes, and action items. Proceed?")) {
      try {
        await api.delete(`/admin/users/${userId}`);
        setUsers(users.filter(u => u.id !== userId));
        // Refresh analytics
        const analyticRes = await api.get('/admin/analytics');
        setAnalytics(analyticRes.data);
      } catch (err) {
        alert(err.response?.data?.detail || "Failed to delete user.");
      }
    }
  };

  const handleDeleteMeeting = async (meetingId) => {
    if (window.confirm("Are you sure you want to delete this meeting?")) {
      try {
        await api.delete(`/admin/meetings/${meetingId}`);
        setMeetings(meetings.filter(m => m.id !== meetingId));
        // Refresh analytics
        const analyticRes = await api.get('/admin/analytics');
        setAnalytics(analyticRes.data);
      } catch (err) {
        alert("Failed to delete meeting.");
      }
    }
  };

  if (loading) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center gap-4">
        <Loader2 className="w-10 h-10 text-primary-500 animate-spin" />
        <p className="text-slate-400">Loading admin controller panels...</p>
      </div>
    );
  }

  return (
    <div className="space-y-10 animate-fade-in">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="p-3 bg-red-500/10 rounded-2xl text-red-400">
          <ShieldAlert className="w-8 h-8" />
        </div>
        <div>
          <h1 className="text-3xl font-extrabold text-white tracking-tight">Admin Control Panel</h1>
          <p className="text-slate-400 mt-1">Global platform usage monitors and database cleanup controls</p>
        </div>
      </div>

      {/* Analytics Dashboard Widgets */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="glass-card p-6 rounded-2xl flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Total Active Users</p>
            <p className="text-3xl font-bold text-white mt-1">{analytics?.total_users}</p>
          </div>
          <div className="p-3 bg-primary-500/10 text-primary-400 rounded-xl">
            <UsersIcon className="w-6 h-6" />
          </div>
        </div>

        <div className="glass-card p-6 rounded-2xl flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Processed Meetings</p>
            <p className="text-3xl font-bold text-white mt-1">{analytics?.total_meetings}</p>
          </div>
          <div className="p-3 bg-emerald-500/10 text-emerald-400 rounded-xl">
            <FileAudio className="w-6 h-6" />
          </div>
        </div>

        <div className="glass-card p-6 rounded-2xl flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">AI Operations Run</p>
            <p className="text-3xl font-bold text-white mt-1">{analytics?.total_meetings * 3}</p>
          </div>
          <div className="p-3 bg-purple-500/10 text-purple-400 rounded-xl">
            <Cpu className="w-6 h-6" />
          </div>
        </div>
      </div>

      {/* Tab Switcher */}
      <div className="border-b border-slate-800 flex gap-2">
        <button
          onClick={() => setActiveTab('users')}
          className={`flex items-center gap-2 px-5 py-3 text-sm font-semibold transition-all border-b-2 outline-none ${
            activeTab === 'users'
              ? 'border-primary-500 text-primary-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <UsersIcon className="w-4 h-4" />
          <span>User Accounts ({users.length})</span>
        </button>
        <button
          onClick={() => setActiveTab('meetings')}
          className={`flex items-center gap-2 px-5 py-3 text-sm font-semibold transition-all border-b-2 outline-none ${
            activeTab === 'meetings'
              ? 'border-primary-500 text-primary-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <FileAudio className="w-4 h-4" />
          <span>All Meeting Logs ({meetings.length})</span>
        </button>
        <button
          onClick={() => setActiveTab('usage')}
          className={`flex items-center gap-2 px-5 py-3 text-sm font-semibold transition-all border-b-2 outline-none ${
            activeTab === 'usage'
              ? 'border-primary-500 text-primary-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Activity className="w-4 h-4" />
          <span>AI Usage Metrics</span>
        </button>
      </div>

      {/* Control Area Panels */}
      <div className="glass-panel p-6 rounded-2xl border border-slate-800">
        
        {/* USERS ADMIN TAB */}
        {activeTab === 'users' && (
          <div className="space-y-4 animate-fade-in">
            <h3 className="text-lg font-bold text-white mb-2">Registered Accounts</h3>
            <div className="overflow-x-auto rounded-xl border border-slate-850">
              <table className="w-full text-left border-collapse text-sm">
                <thead>
                  <tr className="bg-slate-900/60 border-b border-slate-800 text-slate-400 text-xs font-semibold uppercase">
                    <th className="py-3 px-4">Name</th>
                    <th className="py-3 px-4">Email</th>
                    <th className="py-3 px-4">Role</th>
                    <th className="py-3 px-4">Meetings</th>
                    <th className="py-3 px-4">Joined Date</th>
                    <th className="py-3 px-4 text-center">Controls</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-850 text-slate-300">
                  {users.map((u) => (
                    <tr key={u.id} className="hover:bg-slate-900/10">
                      <td className="py-3 px-4 font-semibold text-white">{u.name}</td>
                      <td className="py-3 px-4">{u.email}</td>
                      <td className="py-3 px-4">
                        <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                          u.role === 'admin' 
                            ? 'bg-red-500/10 text-red-400 border border-red-500/20' 
                            : 'bg-primary-500/10 text-primary-400 border border-primary-500/20'
                        }`}>
                          {u.role}
                        </span>
                      </td>
                      <td className="py-3 px-4">{u.meeting_count}</td>
                      <td className="py-3 px-4">{new Date(u.created_at).toLocaleDateString()}</td>
                      <td className="py-3 px-4 text-center">
                        <button
                          onClick={() => handleDeleteUser(u.id)}
                          className="p-1.5 rounded bg-red-500/10 text-red-400 hover:bg-red-500 hover:text-white transition-colors"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* MEETINGS ADMIN TAB */}
        {activeTab === 'meetings' && (
          <div className="space-y-4 animate-fade-in">
            <h3 className="text-lg font-bold text-white mb-2">Uploaded Audio Index</h3>
            {meetings.length === 0 ? (
              <p className="text-slate-500 italic py-6 text-center">No meetings logged across the platform.</p>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-slate-850">
                <table className="w-full text-left border-collapse text-sm">
                  <thead>
                    <tr className="bg-slate-900/60 border-b border-slate-800 text-slate-400 text-xs font-semibold uppercase">
                      <th className="py-3 px-4">Title</th>
                      <th className="py-3 px-4">File Name</th>
                      <th className="py-3 px-4">Uploaded By</th>
                      <th className="py-3 px-4">Upload Date</th>
                      <th className="py-3 px-4 text-center">Controls</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-850 text-slate-300">
                    {meetings.map((m) => (
                      <tr key={m.id} className="hover:bg-slate-900/10">
                        <td className="py-3 px-4 font-semibold text-white">{m.title}</td>
                        <td className="py-3 px-4 max-w-xs truncate text-xs text-slate-500">{m.filename}</td>
                        <td className="py-3 px-4">
                          <div>
                            <p className="font-semibold text-white">{m.user_name}</p>
                            <p className="text-xs text-slate-550">{m.user_email}</p>
                          </div>
                        </td>
                        <td className="py-3 px-4">{new Date(m.created_at).toLocaleDateString()}</td>
                        <td className="py-3 px-4 text-center">
                          <button
                            onClick={() => handleDeleteMeeting(m.id)}
                            className="p-1.5 rounded bg-red-500/10 text-red-400 hover:bg-red-500 hover:text-white transition-colors"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* AI USAGE MONITOR TAB */}
        {activeTab === 'usage' && (
          <div className="space-y-6 animate-fade-in py-4">
            <h3 className="text-lg font-bold text-white mb-2">AI Operations & Tokens</h3>
            <p className="text-slate-400 text-sm">
              Displays resource analytics for active API connections. The system monitors pipeline usage across speech-to-text, summaries, and semantic database indexes.
            </p>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-4">
              <div className="p-5 bg-slate-900/40 border border-slate-850 rounded-xl space-y-3">
                <div className="flex items-center gap-2 text-primary-400 font-bold text-sm">
                  <Cpu className="w-4 h-4" />
                  Whisper transcription
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-bold text-white">{analytics?.total_meetings}</span>
                  <span className="text-xs text-slate-550">audio files</span>
                </div>
                <p className="text-[11px] text-slate-500 leading-relaxed">
                  Usage reflects total API calls dispatched to the OpenAI transcription server.
                </p>
              </div>

              <div className="p-5 bg-slate-900/40 border border-slate-850 rounded-xl space-y-3">
                <div className="flex items-center gap-2 text-emerald-400 font-bold text-sm">
                  <BarChart className="w-4 h-4" />
                  Gemini & GPT Summarizer
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-bold text-white">{analytics?.total_meetings * 2}</span>
                  <span className="text-xs text-slate-550">syntheses</span>
                </div>
                <p className="text-[11px] text-slate-500 leading-relaxed">
                  Reflects parsing workloads for meeting executive summaries, structural highlights, and actionable table details.
                </p>
              </div>

              <div className="p-5 bg-slate-900/40 border border-slate-850 rounded-xl space-y-3">
                <div className="flex items-center gap-2 text-purple-400 font-bold text-sm">
                  <Activity className="w-4 h-4" />
                  ChromaDB Embeddings
                </div>
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-bold text-white">{analytics?.total_meetings * 5}</span>
                  <span className="text-xs text-slate-550">indexes stored</span>
                </div>
                <p className="text-[11px] text-slate-500 leading-relaxed">
                  Reflects the database embedding vectors loaded into the semantic search engine (ChromaDB/Fallback engine).
                </p>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
};

export default AdminPanel;
