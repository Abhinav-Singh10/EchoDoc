import { useEffect, useState } from 'react'
import type { ServerEvent } from './gen/collab/system/v1/system_pb'
import { systemClient } from './rpc'

function EventStream() {
  const [watching, setWatching] = useState(false)
  const [events, setEvents] = useState<ServerEvent[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    if (!watching) return

    const controller = new AbortController()

    async function readEvents() {
      try {
        const stream = systemClient.watchEvents(
          {},
          { signal: controller.signal },
        )

        for await (const event of stream) {
          if (controller.signal.aborted) break

          setEvents(previous => [...previous, event].slice(-20))
        }
      } catch {
        if (!controller.signal.aborted) {
          setError('Stream failed. Check Python and Envoy, then restart.')
        }
      } finally {
        if (!controller.signal.aborted) {
          setWatching(false)
        }
      }
    }

    function leavePage() {
      controller.abort()
      setWatching(false)
    }

    readEvents()

    // Calling leavePage if pagehide occurs
    window.addEventListener('pagehide', leavePage)

    return () => {
      controller.abort()
      window.removeEventListener('pagehide', leavePage)
    }
  }, [watching])

  function start() {
    setEvents([])
    setError('')
    setWatching(true)
  }

  return (
    <section>
      <h2>Server events</h2>

      <button onClick={start} disabled={watching}>
        Start
      </button>
      <button onClick={() => setWatching(false)} disabled={!watching}>
        Stop
      </button>

      <p>
        {watching
          ? events.length === 0 ? 'Connecting…' : 'Receiving events'
          : 'Stopped'}
      </p>

      {error && <p role="alert">{error}</p>}

      <p>Showing {events.length} recent events, up to 20.</p>

      <ul>
        {events.map(event => (
          <li key={event.sequence.toString()}>
            Event {event.sequence.toString()} — {event.processInstanceId}
          </li>
        ))}
      </ul>
    </section>
  )
}

export default EventStream