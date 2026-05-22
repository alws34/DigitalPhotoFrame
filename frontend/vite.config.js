import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    // Use jsdom so React components have a DOM environment.
    environment: 'jsdom',
    // Import jest-dom matchers (toBeInTheDocument, etc.) in every test file.
    setupFiles: ['./src/__tests__/setup.js'],
    globals: true,
  },
})
