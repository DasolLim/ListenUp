import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /**
   * The tool consolidation (five surfaces → two + a dictionary) moved every
   * route. These are permanent redirects rather than deletions so bookmarks,
   * the browser history of existing users, and any link already shared keep
   * working — an accessibility tool is exactly the kind of thing someone pins
   * to a home screen, and a 404 at the moment they need captions is the worst
   * possible time to be right about URL hygiene.
   */
  async redirects() {
    return [
      // Captions: the General/Enhanced pair collapsed into one surface.
      { source: "/voice-to-text", destination: "/captions", permanent: true },
      { source: "/voice-to-text/general", destination: "/captions", permanent: true },
      { source: "/voice-to-text/enhanced", destination: "/captions", permanent: true },
      // Translate: one surface, fast result first and nuance async.
      { source: "/translate/general", destination: "/translate", permanent: true },
      { source: "/translate/enhanced", destination: "/translate", permanent: true },
      // Renamed for what it does rather than who it is for.
      { source: "/translate/genz", destination: "/explain", permanent: true },
    ];
  },
};

export default nextConfig;
