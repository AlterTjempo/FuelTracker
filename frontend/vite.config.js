import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

export default defineConfig({
    plugins: [svelte()],
    server: {
        host: '0.0.0.0',
        port: 5173,
        strictPort: true,
        hmr: process.env.VITE_HMR_HOST ? { 
            host: process.env.VITE_HMR_HOST,
            protocol : process.env.VITE_HMR_PROTOCOL || 'ws',
            port : process.env.VITE_HMR_PORT ? parseInt(process.env.VITE_HMR_PORT) : 5173
        } : undefined,

        allowedHosts: [
            'tjempo.nl', 
            'www.tjempo.nl', 
            '0.0.0.0', // IPv4 wildcard
            '::', // IPv6 wildcard
            'localhost',
        ],
        watch: {
            usePolling: true
        },
        proxy: {
            '/api': {
                target: 'http://backend:8000',
                changeOrigin: true,
                rewrite: (path) => path
            }
        }
    }
})
