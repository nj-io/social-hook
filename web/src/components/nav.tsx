"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ActivityIndicator } from "@/components/activity-indicator";
import { fetchAdvisoryCount } from "@/lib/api";
import { useDataEvents } from "@/lib/use-data-events";

const links = [
  { href: "/", label: "Dashboard" },
  { href: "/drafts", label: "Drafts" },
  { href: "/advisory", label: "Advisory" },
  { href: "/chat", label: "Chat" },
  { href: "/system", label: "System" },
  { href: "/settings", label: "Settings" },
];

function useAdvisoryCount(): number {
  const [count, setCount] = useState(0);

  const load = useCallback(() => {
    fetchAdvisoryCount({ status: "pending" })
      .then((d) => setCount(d.count ?? 0))
      .catch(() => setCount(0));
  }, []);

  useEffect(() => { load(); }, [load]);
  useDataEvents(["advisory"], load);

  return count;
}

export function Nav() {
  const pathname = usePathname();
  const advisoryCount = useAdvisoryCount();

  return (
    <nav className="relative border-b border-border bg-background sticky top-0 z-50">
      <ActivityIndicator />
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-14 items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-lg font-semibold tracking-tight">{process.env.NEXT_PUBLIC_PROJECT_NAME || "Social Hook"}</span>
          </div>
          <div className="flex items-center gap-1">
            {links.map((link) => {
              const active =
                link.href === "/"
                  ? pathname === "/"
                  : pathname.startsWith(link.href);
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`relative rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    active
                      ? "bg-accent text-accent-foreground"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  }`}
                >
                  {link.label}
                  {link.href === "/advisory" && advisoryCount > 0 && (
                    <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
                      {advisoryCount > 99 ? "99+" : advisoryCount}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>
        </div>
      </div>
    </nav>
  );
}
