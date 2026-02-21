"use client";

import { ChatPanel } from "@/components/chat-panel";

export default function ChatPage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Chat</h1>
        <p className="text-muted-foreground">Interact with the bot via commands and messages.</p>
      </div>
      <div className="h-[calc(100vh-220px)] rounded-lg border border-border">
        <ChatPanel />
      </div>
    </div>
  );
}
