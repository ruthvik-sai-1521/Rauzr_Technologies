/**
 * Four distinct, hand-built SVG "product panel" mockups -- one per
 * workflow case. Replaces the previous <img src="/media/product/*.png">
 * approach, which shipped five byte-identical screenshots (all captured
 * from the same page, one still carrying the pre-rename "Veritant" wordmark)
 * cropped to mostly show whitespace. See CHANGELOG / README for the writeup.
 *
 * Building these as SVG rather than screenshots means there's no asset to
 * go stale, no risk of a missing/duplicate file, and no re-branding cost
 * the next time the product name changes.
 */
type ScreenKey = "submission-intake" | "batch-release" | "coa-matching" | "nitrosamine-screening";

const PALETTE = {
  paper: "#F6F4EF",
  ink: "#0F1B2B",
  line: "#DAD5C8",
  teal: "#1C6E62",
  tealLight: "#3AA391",
  amber: "#C98A1D",
  slate: "#8892A0",
};

function Chrome({ title }: { title: string }) {
  return (
    <g>
      <rect width="640" height="40" fill={PALETTE.ink} />
      <circle cx="20" cy="20" r="5" fill={PALETTE.tealLight} />
      <text x="38" y="25" fontFamily="IBM Plex Mono, monospace" fontSize="12" fill={PALETTE.paper} opacity="0.7">
        {title}
      </text>
    </g>
  );
}

function Row({ y, label, value, ok }: { y: number; label: string; value: string; ok: boolean }) {
  return (
    <g>
      <rect x="24" y={y} width="592" height="46" rx="4" fill="#FFFFFF" stroke={PALETTE.line} />
      <circle cx="44" cy={y + 23} r="5" fill={ok ? PALETTE.teal : PALETTE.amber} />
      <text x="60" y={y + 20} fontFamily="IBM Plex Sans, sans-serif" fontSize="12" fill={PALETTE.ink}>
        {label}
      </text>
      <text x="60" y={y + 36} fontFamily="IBM Plex Mono, monospace" fontSize="11" fill={PALETTE.slate}>
        {value}
      </text>
      <text
        x="596"
        y={y + 28}
        textAnchor="end"
        fontFamily="IBM Plex Mono, monospace"
        fontSize="11"
        fill={ok ? PALETTE.teal : PALETTE.amber}
      >
        {ok ? "PASS" : "REVIEW"}
      </text>
    </g>
  );
}

const SCREENS: Record<ScreenKey, { title: string; rows: { label: string; value: string; ok: boolean }[] }> = {
  "submission-intake": {
    title: "workspace / submission intake",
    rows: [
      { label: "Nomenclature (INN / IUPAC)", value: "Detected in dossier text", ok: true },
      { label: "Dossier format", value: "ICH CTD Module 3.2.S", ok: true },
      { label: "QA package attached", value: "site_qa_package.pdf", ok: true },
    ],
  },
  "batch-release": {
    title: "workspace / batch release audit",
    rows: [
      { label: "Batch yield", value: "96.4% -- within 85-102% range", ok: true },
      { label: "Open deviations", value: "0 linked to this batch", ok: true },
      { label: "Nitrosamine level", value: "0.8 ppm -- within limit", ok: true },
    ],
  },
  "coa-matching": {
    title: "workspace / CoA & KSM matching",
    rows: [
      { label: "Certificate of Analysis", value: "Present in dossier", ok: true },
      { label: "Key starting materials", value: "3 of 3 matched to a CoA", ok: true },
      { label: "Unmatched KSM references", value: "None found", ok: true },
    ],
  },
  "nitrosamine-screening": {
    title: "workspace / nitrosamine screening",
    rows: [
      { label: "Nitrosamine impurity", value: "1.8 ppm -- exceeds 1.5 ppm limit", ok: false },
      { label: "Acceptable intake limit", value: "1.5 ppm (rule R-002)", ok: true },
      { label: "Recommended action", value: "Route to reviewer before release", ok: false },
    ],
  },
};

export default function WorkflowPreview({ screen }: { screen: ScreenKey }) {
  const config = SCREENS[screen];
  return (
    <svg viewBox="0 0 640 260" className="aspect-[16/10] w-full rounded-sm" role="img" aria-label={`${config.title} preview`}>
      <rect width="640" height="260" fill={PALETTE.paper} />
      <Chrome title={config.title} />
      {config.rows.map((row, i) => (
        <Row key={row.label} y={60 + i * 58} label={row.label} value={row.value} ok={row.ok} />
      ))}
    </svg>
  );
}

export type { ScreenKey };
