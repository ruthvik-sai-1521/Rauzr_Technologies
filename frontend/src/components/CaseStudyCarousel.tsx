import { useEffect, useRef, useState } from "react";
import { gsap } from "gsap";
import WorkflowPreview, { type ScreenKey } from "./WorkflowPreview";

const CASES: { title: string; detail: string; screen: ScreenKey }[] = [
  { title: "Submission intake", detail: "Standardize incoming dossiers before review.", screen: "submission-intake" },
  { title: "Batch release audit", detail: "Check yield, impurity, and deviation data.", screen: "batch-release" },
  { title: "CoA / KSM matching", detail: "Confirm every starting material has a matching CoA.", screen: "coa-matching" },
  { title: "Nitrosamine screening", detail: "Flag levels above the acceptable intake limit.", screen: "nitrosamine-screening" },
];

export default function CaseStudyCarousel() {
  const [active, setActive] = useState(0);
  const panel = useRef<HTMLDivElement>(null);
  const tabs = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced || !panel.current) return;
    gsap.fromTo(panel.current, { opacity: 0.35, y: 10 }, { opacity: 1, y: 0, duration: 0.45, ease: "power2.out" });
    const activeTab = tabs.current?.children[active] as HTMLElement | undefined;
    if (activeTab) gsap.to(activeTab, { color: "#F6F4EF", duration: 0.25 });
  }, [active]);

  const current = CASES[active];

  return (
    <section className="bg-ink text-paper">
      <div className="container-page py-20 md:py-28">
        <div className="grid gap-12 lg:grid-cols-[0.8fr_1.2fr] lg:items-end">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-teal-light">Inside the workspace</p>
            <h2 className="mt-4 max-w-md text-3xl font-medium md:text-4xl">One review surface for the work that slows teams down.</h2>
            <p className="mt-5 max-w-md text-sm leading-relaxed text-paper/65">These panels show the actual Rauzr Technologies workspace. Run the bundled sample to move from source files to a scored report.</p>
            <div ref={tabs} className="mt-9 grid gap-2" role="tablist" aria-label="Workspace workflows">
              {CASES.map((item, index) => (
                <button
                  key={item.title}
                  type="button"
                  role="tab"
                  aria-selected={active === index}
                  onClick={() => setActive(index)}
                  className={`border-l-2 px-4 py-3 text-left text-sm transition-colors ${active === index ? "border-teal-light text-paper" : "border-paper/15 text-paper/45 hover:text-paper/80"}`}
                >
                  {item.title}
                </button>
              ))}
            </div>
          </div>
          <div ref={panel} role="tabpanel" aria-label={current.title} className="overflow-hidden rounded-sm border border-paper/15 bg-ink-700 p-3 shadow-2xl">
            <WorkflowPreview screen={current.screen} />
            <div className="flex items-center justify-between gap-4 border-t border-paper/10 px-2 pb-1 pt-4">
              <div>
                <p className="font-mono text-xs text-teal-light">workspace / pipeline run</p>
                <p className="mt-1 text-sm text-paper/75">{current.detail}</p>
              </div>
              <span className="rounded-full border border-teal-light/40 px-2 py-1 font-mono text-[10px] text-teal-light">DEMO</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
