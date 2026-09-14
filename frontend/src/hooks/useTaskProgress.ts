import { useEffect, useRef, useState } from 'react';
import type { ProgressMessage } from '../types';
import { taskProgressUrl } from '../api';

export function useTaskProgress(taskId: string | null): ProgressMessage | null {
  const [message, setMessage] = useState<ProgressMessage | null>(null);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!taskId) {
      setMessage(null);
      return;
    }
    let disposed = false;
    let socket: WebSocket | null = null;

    const connect = () => {
      if (disposed) return;
      socket = new WebSocket(taskProgressUrl(taskId));
      socketRef.current = socket;
      socket.onmessage = (event) => {
        try {
          setMessage(JSON.parse(event.data) as ProgressMessage);
        } catch {
          /* ignore malformed frames */
        }
      };
      socket.onclose = () => {
        if (!disposed) {
          setTimeout(connect, 1500);
        }
      };
    };

    connect();
    return () => {
      disposed = true;
      socket?.close();
    };
  }, [taskId]);

  return message;
}
