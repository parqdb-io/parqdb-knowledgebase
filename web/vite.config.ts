import { readFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import type { Plugin } from 'vite'
import { defineConfig } from 'vite'

const webRoot = dirname(fileURLToPath(import.meta.url))
const parqdbRoot = resolve(process.env.PARQDB_ROOT ?? resolve(webRoot, '../../parqdb'))
const wasmPath = resolve(parqdbRoot, 'target/wasm32-unknown-unknown/release/parqdb_browser_kernels.wasm')

function runtimeAssets(): Plugin {
  return {
    name: 'runtime-assets',
    async generateBundle() {
      this.emitFile({
        type: 'asset',
        fileName: 'parqdb_browser_kernels.wasm',
        source: await readFile(wasmPath),
      })
    },
  }
}

export default defineConfig({
  root: webRoot,
  base: './',
  publicDir: resolve(webRoot, 'public'),
  resolve: {
    alias: {
      '@parqdb/index': resolve(parqdbRoot, 'browser/src/index.ts'),
      '@parqdb/http': resolve(parqdbRoot, 'browser/src/http.ts'),
    },
  },
  plugins: [runtimeAssets()],
  build: {
    outDir: resolve(webRoot, '../_site'),
    emptyOutDir: true,
    target: 'es2022',
  },
})
