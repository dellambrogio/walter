import { useEffect, useRef, useState } from 'react'
import { fetchPhotos, type Photo } from './api'

type Props = { stageId: string; onHover: (photo: Photo | null) => void }
type State = { id: string; photos: Photo[] | null; error: boolean }

/** Openly licensed photos along the stage (Wikimedia Commons), start to end, with credits. */
export function PhotoStrip({ stageId, onHover }: Props) {
  const [state, setState] = useState<State | null>(null)
  const [open, setOpen] = useState<number | null>(null)
  const strip = useRef<HTMLOListElement>(null)

  useEffect(() => {
    const controller = new AbortController()
    fetchPhotos(stageId, controller.signal)
      .then((photos) => setState({ id: stageId, photos, error: false }))
      .catch((e: Error) => e.name !== 'AbortError' && setState({ id: stageId, photos: null, error: true }))
    return () => controller.abort()
  }, [stageId])

  const current = state?.id === stageId ? state : null
  const photos = current?.photos ?? []
  const scroll = (direction: number) =>
    strip.current?.scrollBy({ left: direction * strip.current.clientWidth * 0.8, behavior: 'smooth' })

  if (current && !current.error && photos.length === 0) return null // nothing near this trail
  return (
    <section className="photos" aria-label="Photos along the stage">
      {!current && <p className="muted photos-note">Looking for photos…</p>}
      {current?.error && <p className="muted photos-note">Photos unavailable (Wikimedia Commons not reachable).</p>}
      {photos.length > 0 && (
        <>
          <button className="photos-nav prev" onClick={() => scroll(-1)} aria-label="Previous photos">
            ‹
          </button>
          <ol ref={strip} onMouseLeave={() => onHover(null)}>
            {photos.map((p, i) => (
              <li key={p.page}>
                <button
                  onClick={() => setOpen(i)}
                  onMouseEnter={() => onHover(p)}
                  onFocus={() => onHover(p)}
                  title={`${p.title} · ${p.author}`}
                >
                  <img src={p.thumb} alt={p.description || p.title} loading="lazy" />
                </button>
              </li>
            ))}
          </ol>
          <button className="photos-nav next" onClick={() => scroll(1)} aria-label="Next photos">
            ›
          </button>
          <p className="photos-credit">Photos: Wikimedia Commons contributors (click for credits)</p>
        </>
      )}
      {open !== null && photos[open] && (
        <Lightbox photos={photos} index={open} onIndex={setOpen} onClose={() => setOpen(null)} />
      )}
    </section>
  )
}

function Lightbox({ photos, index, onIndex, onClose }: {
  photos: Photo[]
  index: number
  onIndex: (i: number) => void
  onClose: () => void
}) {
  const photo = photos[index]
  const go = (step: number) => onIndex((index + step + photos.length) % photos.length)

  useEffect(() => {
    // Capture phase, so Escape closes the photo and not the whole stage panel
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      else if (e.key === 'ArrowLeft') go(-1)
      else if (e.key === 'ArrowRight') go(1)
      else return
      e.stopImmediatePropagation()
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  })

  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label={photo.title} onClick={onClose}>
      <figure onClick={(e) => e.stopPropagation()}>
        <img src={photo.large} alt={photo.description || photo.title} />
        <figcaption>
          <strong>{photo.title}</strong>
          {photo.description && <span>{photo.description}</span>}
          <span className="muted">
            {photo.author} ·{' '}
            {photo.licence_url ? (
              <a href={photo.licence_url} target="_blank" rel="noreferrer">
                {photo.licence}
              </a>
            ) : (
              photo.licence
            )}{' '}
            ·{' '}
            <a href={photo.page} target="_blank" rel="noreferrer">
              Wikimedia Commons ↗
            </a>{' '}
            · {index + 1} / {photos.length}
          </span>
        </figcaption>
      </figure>
      <button className="lightbox-nav prev" onClick={(e) => (e.stopPropagation(), go(-1))} aria-label="Previous photo">
        ‹
      </button>
      <button className="lightbox-nav next" onClick={(e) => (e.stopPropagation(), go(1))} aria-label="Next photo">
        ›
      </button>
      <button className="lightbox-close" onClick={onClose} aria-label="Close photo">
        ×
      </button>
    </div>
  )
}
