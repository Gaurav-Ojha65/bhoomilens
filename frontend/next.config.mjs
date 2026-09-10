/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  webpack: (config) => {
    // react-pdf needs this for the worker script
    config.resolve.alias.canvas = false;
    return config;
  },
};
export default nextConfig;
