"use client";

import { Shell } from "@/components/Shell";
import { ChatWorkspace } from "@/components/ChatWorkspace";

export default function AdminPage() {
  return (
    <Shell requireRole="admin">
      {(me) => <ChatWorkspace me={me} />}
    </Shell>
  );
}
