/** @type {import('next').NextConfig} */
const nextConfig = {
  // Emit a self-contained server build for small production containers.
  output: 'standalone',
  // A production build must not replace CSS/chunks served by a running dev server.
  distDir: process.env.NODE_ENV === 'development' ? '.next-dev' : '.next',
};

export default nextConfig;
