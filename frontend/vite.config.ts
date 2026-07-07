/// <reference types="vitest" />
import { fileURLToPath, URL } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    // 멀티 엔트리: 메인 앱(index.html) + 독립 테스트 현황 앱(status.html).
    // dist/assets는 공유되고, 백엔드가 각 앱의 SPA fallback을 엔트리별로 서빙한다.
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        status: fileURLToPath(new URL('./status.html', import.meta.url)),
      },
    },
  },
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: true,
  },
})
