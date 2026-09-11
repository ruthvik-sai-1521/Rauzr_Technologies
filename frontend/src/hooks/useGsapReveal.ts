import { useEffect, useRef } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

// This runs once per page load, not per hook call. Root cause of the
// "content stuck invisible" bug: this app loads two custom Google Fonts
// via a <link> tag. ScrollTrigger calculates every trigger's pixel
// position from the DOM layout *at the moment it's created*. If that
// happens before the fonts finish loading (near-certain on a fast
// connection, since the fonts request is async), the fallback font's
// layout is used -- often shorter -- and every trigger position below
// the swap point is calculated wrong. Because each reveal uses
// `once: true`, a trigger that never gets a chance to re-fire simply
// never plays, leaving the element at its `opacity: 0` starting state
// forever. Refreshing after fonts (and after full page load, to catch
// images) recalculates every registered trigger against the final layout.
let refreshScheduled = false;
function scheduleGlobalRefresh() {
  if (refreshScheduled) return;
  refreshScheduled = true;
  const refresh = () => ScrollTrigger.refresh();
  if ("fonts" in document) {
    document.fonts.ready.then(refresh).catch(() => {});
  }
  window.addEventListener("load", refresh, { once: true });
}

interface RevealOptions {
  /** Stagger children matching this selector instead of animating the container as one block. */
  childSelector?: string;
  /** Pixels to travel on the way in. */
  y?: number;
  duration?: number;
  stagger?: number;
  /** 0-1, how far into the viewport the element must be before animating. */
  start?: string;
}

/**
 * Fades + slides an element (or its staggered children) in once, the first
 * time it scrolls into view. Respects prefers-reduced-motion by setting the
 * final state immediately with no animation, matching the convention
 * established by useCountUp for the rest of this codebase.
 *
 * Defense in depth against the font-load timing issue described above: a
 * one-shot safety-net timer forces the final visible state regardless of
 * whether ScrollTrigger ever fired, so a mistimed or missed trigger can
 * never leave real content permanently invisible.
 */
export function useGsapReveal<T extends HTMLElement>(options: RevealOptions = {}) {
  const ref = useRef<T | null>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    const { childSelector, y = 28, duration = 0.7, stagger = 0.08, start = "top 85%" } = options;
    const targets = childSelector ? node.querySelectorAll(childSelector) : node;
    const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (prefersReduced) {
      gsap.set(targets, { opacity: 1, y: 0 });
      return;
    }

    scheduleGlobalRefresh();

    const ctx = gsap.context(() => {
      const tween = gsap.fromTo(
        targets,
        { opacity: 0, y },
        {
          opacity: 1,
          y: 0,
          duration,
          stagger,
          ease: "power3.out",
          scrollTrigger: {
            trigger: node,
            start,
            once: true,
          },
        }
      );

      // Safety net: whatever the cause, nothing on this page should be
      // able to stay invisible past a couple of seconds after mount.
      const safety = window.setTimeout(() => {
        if (tween.progress() === 0) tween.progress(1);
      }, 2500);
      tween.eventCallback("onComplete", () => window.clearTimeout(safety));
    }, node);

    return () => ctx.revert();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return ref;
}
