import React, { useCallback } from "react";

const CX = 70, CY = 70, HAND_R = 40, TICK_OUTER = 58;

function hourToAngle(h) {
  return (h / 24) * 2 * Math.PI - Math.PI / 2;
}

function angleToHour(angle) {
  let a = angle + Math.PI / 2;
  if (a < 0) a += 2 * Math.PI;
  if (a >= 2 * Math.PI) a -= 2 * Math.PI;
  return Math.round((a / (2 * Math.PI)) * 24) % 24;
}

export default function ClockKnob({ value, onChange }) {
  const hour = value ?? 0;
  const handAngle = hourToAngle(hour);
  const handX = CX + Math.cos(handAngle) * HAND_R;
  const handY = CY + Math.sin(handAngle) * HAND_R;

  const handleInteraction = useCallback((e) => {
    const svg = e.currentTarget.closest("svg");
    const rect = svg.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    const x = clientX - rect.left - CX;
    const y = clientY - rect.top - CY;
    onChange(angleToHour(Math.atan2(y, x)));
  }, [onChange]);

  const ticks = Array.from({ length: 24 }, (_, i) => {
    const a = hourToAngle(i);
    const isMajor = i % 6 === 0;
    const inner = TICK_OUTER - (isMajor ? 9 : 5);
    return {
      i, isMajor,
      x1: CX + Math.cos(a) * inner, y1: CY + Math.sin(a) * inner,
      x2: CX + Math.cos(a) * TICK_OUTER, y2: CY + Math.sin(a) * TICK_OUTER,
      lx: CX + Math.cos(a) * (inner - 11), ly: CY + Math.sin(a) * (inner - 11),
    };
  });

  return (
    <svg
      width={140} height={140}
      style={{ cursor: "pointer", userSelect: "none", flexShrink: 0 }}
      onClick={handleInteraction}
      onMouseMove={(e) => e.buttons === 1 && handleInteraction(e)}
      onTouchMove={(e) => { e.preventDefault(); handleInteraction(e); }}
    >
      {/* Face */}
      <circle cx={CX} cy={CY} r={62} fill="rgba(255,255,255,0.04)" stroke="var(--glass-border)" strokeWidth={1} />

      {/* Ticks */}
      {ticks.map(({ i, isMajor, x1, y1, x2, y2, lx, ly }) => (
        <React.Fragment key={i}>
          <line x1={x1} y1={y1} x2={x2} y2={y2}
            stroke={i === hour ? "var(--accent)" : "rgba(255,255,255,0.25)"}
            strokeWidth={isMajor ? 2 : 1} />
          {isMajor && (
            <text x={lx} y={ly} textAnchor="middle" dominantBaseline="middle"
              fill={i === hour ? "var(--accent)" : "var(--text-secondary)"} fontSize={9}>{i}</text>
          )}
        </React.Fragment>
      ))}

      {/* Hand */}
      <line x1={CX} y1={CY} x2={handX} y2={handY}
        stroke="var(--accent)" strokeWidth={2} strokeLinecap="round" />
      <circle cx={CX} cy={CY} r={3} fill="var(--accent)" />
      <circle cx={handX} cy={handY} r={5} fill="var(--accent)"
        style={{ filter: "drop-shadow(0 0 4px var(--accent))" }} />

      {/* Center label */}
      <text x={CX} y={CY + 16} textAnchor="middle" fill="white" fontSize={15} fontWeight="bold">
        {String(hour).padStart(2, "0")}:00
      </text>
    </svg>
  );
}
