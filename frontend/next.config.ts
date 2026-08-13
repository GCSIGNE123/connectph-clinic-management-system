import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  eslint: {
    dirs: ["src"],
  },
};

export default nextConfig;
