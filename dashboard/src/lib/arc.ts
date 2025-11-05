export function polarToXY(cx: number, cy: number, radius: number, angleDeg: number): [number, number] {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return [cx + radius * Math.cos(rad), cy + radius * Math.sin(rad)];
}

export function arcPath(cx: number, cy: number, radius: number, startAngle: number, endAngle: number): string {
  const [x0, y0] = polarToXY(cx, cy, radius, startAngle);
  const [x1, y1] = polarToXY(cx, cy, radius, endAngle);
  const delta = Math.abs((((endAngle - startAngle) % 360) + 360) % 360);
  const largeArc = delta > 180 ? 1 : 0;
  const sweep = 1;
  return `M ${x0} ${y0} A ${radius} ${radius} 0 ${largeArc} ${sweep} ${x1} ${y1}`;
}

export function donutSegmentPath(
  cx: number,
  cy: number,
  innerRadius: number,
  outerRadius: number,
  startAngle: number,
  endAngle: number,
  gapDeg = 0,
): string {
  const start = startAngle + gapDeg;
  const end = endAngle - gapDeg;
  const [xOuterStart, yOuterStart] = polarToXY(cx, cy, outerRadius, start);
  const [xInnerEnd, yInnerEnd] = polarToXY(cx, cy, innerRadius, end);
  const outerArc = arcPath(cx, cy, outerRadius, start, end);
  const innerArc = arcPath(cx, cy, innerRadius, end, start);
  return `${outerArc} L ${xInnerEnd} ${yInnerEnd} ${innerArc} Z`;
}
