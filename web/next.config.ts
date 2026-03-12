import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `http://127.0.0.1:${process.env.NEXT_PUBLIC_API_PORT || '8741'}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
