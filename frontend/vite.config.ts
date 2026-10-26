import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development the React app runs on :5173 and proxies /api to the FastAPI backend on :8040.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8040' } },
})
