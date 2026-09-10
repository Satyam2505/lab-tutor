/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // In development the browser talks to Next on :3000 and the API on
  // :8000. In the container stack Caddy serves both from one origin, so
  // this rewrite is a no-op there and the client code never needs to know
  // which environment it is in -- it always calls same-origin /api/*.
  async rewrites() {
    const backend = process.env.BACKEND_INTERNAL_URL;
    if (!backend) return [];
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
