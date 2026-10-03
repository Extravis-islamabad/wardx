import { Alert, Spin } from 'antd';
import * as AsciinemaPlayer from 'asciinema-player';
import 'asciinema-player/dist/bundle/asciinema-player.css';
import { useEffect, useRef, useState } from 'react';
import { errorMessage } from '@/lib/apiClient';
import { sessionsApi } from '@/services/api';

/** Plays a session recording; the cast is fetched with the user's token, never by URL. */
export function RecordingPlayer({ sessionId, onVerified }: { sessionId: string; onVerified?: (ok: boolean) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let player: { dispose(): void } | null = null;
    let cancelled = false;
    setLoading(true);
    setError(null);
    sessionsApi
      .recording(sessionId)
      .then(({ text, verified }) => {
        if (cancelled || !ref.current) return;
        onVerified?.(verified);
        player = AsciinemaPlayer.create({ data: text }, ref.current, {
          fit: 'width',
          idleTimeLimit: 2,
          theme: 'asciinema',
          terminalFontSize: '13px',
        });
      })
      .catch((e) => !cancelled && setError(errorMessage(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
      player?.dispose();
    };
    // onVerified is a notification; re-running on its identity would refetch.
  }, [sessionId]);

  return (
    <>
      {loading && <Spin />}
      {error && <Alert type="error" showIcon title={error} />}
      <div ref={ref} />
    </>
  );
}
