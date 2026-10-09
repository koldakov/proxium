import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import babel from '@rolldown/plugin-babel'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), babel({ presets: [reactCompilerPreset()] })],
  resolve: {
    alias: [
      // react-admin imports named parse/stringify, query-string 9 (see overrides in package.json) has them only in
      // base.js. Drop both once react-admin moves off query-string 7.
      {
        find: /^query-string$/,
        replacement: fileURLToPath(new URL('node_modules/query-string/base.js', import.meta.url)),
      },
    ],
  },
})
