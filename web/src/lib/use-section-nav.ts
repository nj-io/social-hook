"use client";

import { RefObject, useCallback, useEffect, useRef, useState } from "react";

interface UseSectionNavOptions {
  sections: { id: string }[];
  defaultSection: string;
  scrollContainerRef: RefObject<HTMLElement | null>;
  paramName?: string;
  rootMargin?: string;
  scrollSettleMs?: number;
}

interface UseSectionNavReturn {
  activeSection: string;
  scrollToSection: (id: string) => void;
}

/**
 * Reusable hook for pages with scrollable sections and URL sync.
 *
 * - Reads initial section from URL query param (?section=X)
 * - pushState on explicit navigation (sidebar click)
 * - replaceState on scroll-spy (user scrolling)
 * - popstate listener for browser back/forward
 */
export function useSectionNav({
  sections,
  defaultSection,
  scrollContainerRef,
  paramName = "section",
  rootMargin = "0px 0px -60% 0px",
  scrollSettleMs = 600,
}: UseSectionNavOptions): UseSectionNavReturn {
  const scrollingToRef = useRef(false);

  // Read initial section from URL
  const getSectionFromUrl = useCallback(() => {
    if (typeof window === "undefined") return defaultSection;
    const params = new URLSearchParams(window.location.search);
    return params.get(paramName) || defaultSection;
  }, [defaultSection, paramName]);

  const [activeSection, setActiveSection] = useState(getSectionFromUrl);

  // Scroll to a section element within the container
  const doScroll = useCallback(
    (id: string) => {
      const el = document.getElementById(id);
      const container = scrollContainerRef.current;
      if (!el || !container) return;
      scrollingToRef.current = true;
      const top = el.offsetTop - container.offsetTop;
      container.scrollTo({ top, behavior: "smooth" });
      setTimeout(() => {
        scrollingToRef.current = false;
      }, scrollSettleMs);
    },
    [scrollContainerRef, scrollSettleMs],
  );

  // Explicit navigation: push history entry + scroll
  const scrollToSection = useCallback(
    (id: string) => {
      setActiveSection(id);
      const url = new URL(window.location.href);
      url.searchParams.set(paramName, id);
      window.history.pushState(null, "", url.toString());
      doScroll(id);
    },
    [paramName, doScroll],
  );

  // On mount: if URL has a section param, scroll to it
  useEffect(() => {
    const initial = getSectionFromUrl();
    if (initial !== defaultSection) {
      // Small delay to ensure DOM is ready
      requestAnimationFrame(() => doScroll(initial));
    }
  }, [getSectionFromUrl, defaultSection, doScroll]);

  // Back/forward support
  useEffect(() => {
    function onPopState() {
      const params = new URLSearchParams(window.location.search);
      const section = params.get(paramName) || defaultSection;
      setActiveSection(section);
      doScroll(section);
    }
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [paramName, defaultSection, doScroll]);

  // Scroll-spy: IntersectionObserver updates activeSection + replaceState
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const sectionIds = sections.map((s) => s.id);
    const observer = new IntersectionObserver(
      (entries) => {
        if (scrollingToRef.current) return;
        const visible: { id: string; top: number }[] = [];
        for (const entry of entries) {
          if (entry.isIntersecting) {
            visible.push({ id: entry.target.id, top: entry.boundingClientRect.top });
          }
        }
        if (visible.length > 0) {
          visible.sort((a, b) => a.top - b.top);
          const topId = visible[0].id;
          if (sectionIds.includes(topId)) {
            setActiveSection(topId);
            // replaceState so scroll-spy doesn't clutter history
            const url = new URL(window.location.href);
            url.searchParams.set(paramName, topId);
            window.history.replaceState(null, "", url.toString());
          }
        }
      },
      { root: container, rootMargin, threshold: 0 },
    );

    for (const id of sectionIds) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    }

    return () => observer.disconnect();
  }, [sections, scrollContainerRef, paramName, rootMargin]);

  return { activeSection, scrollToSection };
}
