import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'
import { visualizer } from 'rollup-plugin-visualizer'
import externalGlobals from 'rollup-plugin-external-globals'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue(), visualizer()],
  resolve: {
    alias: {
      '@': resolve(__dirname, './src'),
    },
  },
  base: './',
  build: {
    rollupOptions: {
      external: ['vue', 'vue-router', 'chart.xkcd'],
      plugins: [
        externalGlobals({
          vue: 'Vue',
          'vue-router': 'VueRouter',
          'chart.xkcd': 'chartXkcd',
        }),
      ],
    },
  },
})
