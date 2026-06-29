import axios from "axios"

const TOKEN_KEY = "phia_token"

export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const setToken = (t: string) => localStorage.setItem(TOKEN_KEY, t)
export const clearToken = () => localStorage.removeItem(TOKEN_KEY)

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE ?? "/api",
})

// Attach the JWT to every request.
api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// On 401, clear the token and bounce to login.
api.interceptors.response.use(
  (r) => r,
  (error) => {
    if (error.response?.status === 401) {
      clearToken()
      if (window.location.pathname !== "/login") {
        window.location.href = "/login"
      }
    }
    return Promise.reject(error)
  }
)
