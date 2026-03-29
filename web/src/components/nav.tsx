"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ActivityIndicator } from "@/components/activity-indicator";

const links = [
  { href: "/", label: "Dashboard" },
  { href: "/drafts", label: "Drafts" },
  { href: "/chat", label: "Chat" },
  { href: "/system", label: "System" },
  { href: "/settings", label: "Settings" },
];

export function Nav() {
  const pathname = usePathname();

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
                  className={`rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    active
                      ? "bg-accent text-accent-foreground"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
          </div>
        </div>
      </div>
    </nav>
  );
}
