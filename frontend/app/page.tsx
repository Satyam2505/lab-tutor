"use client";

import { Shell } from "@/components/Shell";
import { ChatWorkspace } from "@/components/ChatWorkspace";

export default function HomePage() {
  return (
    <Shell>
      {(me) => <ChatWorkspace me={me} />}
    </Shell>
  );
}
