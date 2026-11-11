import axios from 'axios';

const getApiBase = () => {
  const envUrl = import.meta.env.VITE_API_URL;
  if (typeof window !== 'undefined') {
    const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    // Si estamos en un servidor remoto (ej. 18.191.207.20), usar siempre la ruta relativa '/api/'
    // para evitar que apunte erróneamente al localhost de la máquina del cliente
    if (!isLocalhost && (!envUrl || envUrl.includes('localhost') || envUrl.includes('127.0.0.1'))) {
      return '/api/';
    }
  }
  return envUrl || 'http://localhost:8000/api/';
};

const API_BASE = getApiBase();

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  if (/^\/?ai\//.test(config.url || '')) {
    config.timeout = config.timeout || 200000;
  }
  if (config.data instanceof FormData) {
    delete config.headers['Content-Type'];
  }
  return config;
}, (error) => Promise.reject(error));

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const isAuthUrl = originalRequest?.url?.includes('auth/login') || originalRequest?.url?.includes('auth/register');

    if (error.response?.status === 401 && !originalRequest?._retry && !isAuthUrl) {
      originalRequest._retry = true;
      try {
        const refreshToken = localStorage.getItem('refresh_token');
        if (!refreshToken) throw new Error('No refresh token');
        
        const refreshEndpoint = API_BASE.endsWith('/')
          ? `${API_BASE}auth/refresh/`
          : `${API_BASE}/auth/refresh/`;
        const res = await axios.post(refreshEndpoint, {
          refresh: refreshToken
        });
        
        localStorage.setItem('access_token', res.data.access);
        originalRequest.headers.Authorization = `Bearer ${res.data.access}`;
        return api(originalRequest);
      } catch (refreshError) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        if (window.location.pathname !== '/login' && window.location.pathname !== '/register') {
          window.location.href = '/login';
        }
        return Promise.reject(error);
      }
    }
    return Promise.reject(error);
  }
);

export default api;
