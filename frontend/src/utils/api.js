import axios from 'axios';

// VITE_API_URL overrides; otherwise production builds use the deployed
// backend and dev builds use the local FastAPI default (localhost:8000).
const API_URL = import.meta.env.VITE_API_URL
  || (import.meta.env.PROD
    ? 'https://meetingmindai-4ncr.onrender.com/api'
    : 'http://localhost:8000/api');

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor to add JWT token to all requests
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

export default api;
