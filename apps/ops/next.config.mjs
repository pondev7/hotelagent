/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Standalone output keeps the production image small on a single small VM.
  output: "standalone",
};

export default nextConfig;
