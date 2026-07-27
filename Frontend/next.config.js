/** @type {import('next').NextConfig} */
const nextConfig = {
  // output: 'standalone' removed as it breaks next start in standard mode
  // Disable x-powered-by header for security
  poweredByHeader: false,
}

module.exports = nextConfig
