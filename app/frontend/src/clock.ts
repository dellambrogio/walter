// Times of day for the trip planner, as minutes since midnight of the planned day

/** "2026-10-31T08:10:00+01:00" -> minutes since midnight of `day` (the API sends Swiss local time); after midnight runs past 24:00 */
export function minutesOf(iso: string, day: string): number {
  const minutes = Number(iso.slice(11, 13)) * 60 + Number(iso.slice(14, 16))
  return iso.slice(0, 10) === day ? minutes : minutes + 1440
}

export const hhmm = (minutes: number) =>
  `${String(Math.floor(minutes / 60) % 24).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`
