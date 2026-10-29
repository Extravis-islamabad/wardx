import { Alert, Spin } from 'antd';
import * as AsciinemaPlayer from 'asciinema-player';
import 'asciinema-player/dist/bundle/asciinema-player.css';
import { useEffect, useRef } from 'react';
import { useSessionRecording } from '@/features/sessions/hooks';
import { errorMessage } from '@/utils/notifyApiError';

/** Plays a session recording; the cast is fetched with the user's token, never by URL. */
export function RecordingPlayer({ sessionId, onVerified }: { sessionId: string; onVerified?: (ok: boolean) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const recording = useSessionRecording(sessionId);
  const data = recording.data;

  useEffect(() => {
    if (!data || !ref.current) return;
    onVerified?.(data.verified);
    const player = AsciinemaPlayer.create({ data: data.text }, ref.current, {
      fit: 'width',
      idleTimeLimit: 2,
      theme: 'asciinema',
      terminalFontSize: '13px',
    });
    return () => player?.dispose();
    // onVerified is a notification; re-running on its identity would rebuild the player.
  }, [data]);

  return (
    <>
      {recording.isLoading && <Spin />}
      {recording.isError && <Alert type="error" showIcon title={errorMessage(recording.error)} />}
      {data?.incomplete && (
        <Alert
          type="warning"
          showIcon
          className="mb-2"
          title="Incomplete recording"
          description="The gateway node holding this session was lost. The replay ends at the last chunk that reached storage; this is not the full session."
        />
      )}
      <div ref={ref} />
    </>
  );
}

export default RecordingPlayer;
